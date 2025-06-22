# master_monitor.py
import json
import threading
import websocket
import ssl
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta
import pandas as pd
import setup_checkers
from fvg_logic import FvgLogic

# --- توابع کمکی برای استراتژی‌ها ---

def get_trading_session(utc_hour):
    """نام سشن معاملاتی را بر اساس ساعت UTC برمی‌گرداند."""
    if 1 <= utc_hour < 8: return "Asian Session"
    elif 8 <= utc_hour < 16: return "London Session"
    elif 16 <= utc_hour < 23: return "New York Session"
    else: return "After Hours"

def check_pin_bar(candle, direction):
    """بررسی می‌کند که آیا یک کندل، شرایط پین‌بار در جهت مشخص را دارد یا خیر."""
    candle_range = candle.get('high', 0) - candle.get('low', 0)
    if candle_range == 0: return False
    body = abs(candle.get('open', 0) - candle.get('close', 0))
    upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
    lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
    is_pin_bar_body = body < candle_range / 3
    if direction == 'Buy': return is_pin_bar_body and lower_wick > body * 2
    elif direction == 'Sell': return is_pin_bar_body and upper_wick > body * 2
    return False

def find_ltf_entry_and_sl(one_minute_candles, direction, lookback_minutes=15):
    """در تایم فریم ۱ دقیقه به دنبال نقطه ورود دقیق و حد ضرر می‌گردد."""
    if len(one_minute_candles) < 2: return None
    entry_df = pd.DataFrame(list(one_minute_candles)[-lookback_minutes:])
    if entry_df.empty: return None
    if direction == 'Buy':
        swing_low = entry_df['low'].min()
        stop_loss = swing_low * 0.9995
        for i in range(1, len(entry_df)):
            if entry_df['close'].iloc[i] > entry_df['high'].iloc[i-1]:
                return {'entry_time': entry_df['open_time'].iloc[i].to_pydatetime(), 'entry_price': entry_df['close'].iloc[i], 'stop_loss': stop_loss}
    if direction == 'Sell':
        swing_high = entry_df['high'].max()
        stop_loss = swing_high * 1.0005
        for i in range(1, len(entry_df)):
            if entry_df['close'].iloc[i] < entry_df['low'].iloc[i-1]:
                return {'entry_time': entry_df['open_time'].iloc[i].to_pydatetime(), 'entry_price': entry_df['close'].iloc[i], 'stop_loss': stop_loss}
    return None

class MasterMonitor:
    def __init__(self, key_levels, symbol, daily_trend, position_manager, state_manager):
        self.key_levels = key_levels
        self.symbol = symbol
        self.daily_trend = daily_trend
        self.position_manager = position_manager
        self.state_manager = state_manager
        self.candles_1m = deque(maxlen=60)
        self.candles_5m = deque(maxlen=60)
        self.candles_30m = deque(maxlen=60)
        self.current_5m_buffer, self.current_30m_buffer = [], []
        self.active_levels = {}
        self.alert_cooldowns = defaultdict(lambda: None)
        self.level_test_counts = defaultdict(int)
        self.fvg_handler_5m = FvgLogic()
        self.fvg_handler_30m = FvgLogic()
        self.ws = None
        self.wst = None

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('e') == 'kline' and data['k']['x']:
                self.process_candle(data['k'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[{self.symbol}] Error processing message: {e}")

    def on_error(self, ws, error): print(f"[{self.symbol}] WebSocket Error: {error}")
    def on_close(self, ws, close_status_code, close_msg): print(f"[{self.symbol}] WebSocket Connection Closed.")

    def process_candle(self, kline):
        candle = {'open_time': datetime.fromtimestamp(int(kline['t'])/1000, tz=timezone.utc), 'open': float(kline['o']), 'high': float(kline['h']), 'low': float(kline['l']), 'close': float(kline['c']), 'volume': float(kline['v']), 'taker_buy_base_asset_volume': float(kline['q'])}
        self.state_manager.update_symbol_state(self.symbol, 'last_price', candle['close'])
        self.state_manager.update_symbol_state(self.symbol, 'klines_1m', list(self.candles_1m))
        
        self.candles_1m.append(candle)
        self.current_5m_buffer.append(candle)
        self.current_30m_buffer.append(candle)
        
        self._check_level_proximity(candle)
        
        dt_object = candle['open_time']
        if (dt_object.minute + 1) % 5 == 0 and dt_object.second >= 58:
            candle_5m = self._aggregate_candles(self.current_5m_buffer)
            self.current_5m_buffer = []
            if candle_5m:
                self.candles_5m.append(candle_5m)
                self._check_all_setups(candle_5m, '5m')         # بررسی ستاپ‌های قدیمی
                self._evaluate_level_interaction(candle_5m) # بررسی استراتژی جدید

        if (dt_object.minute + 1) % 30 == 0 and dt_object.second >= 58:
            candle_30m = self._aggregate_candles(self.current_30m_buffer)
            self.current_30m_buffer = []
            if candle_30m:
                self.candles_30m.append(candle_30m)
                self._check_all_setups(candle_30m, '30m')

    def _check_level_proximity(self, candle):
        for level_data in self.key_levels:
            level_price = level_data['level']
            if candle['low'] <= level_price <= candle['high']:
                if self.active_levels.get(level_price) != "Touched":
                    self.position_manager.send_info_alert(f"🎯 **برخورد**: قیمت {self.symbol} سطح **{level_data['level_type']}** را لمس کرد.")
                    self.active_levels[level_price] = "Touched"
                    self.level_test_counts[level_price] += 1
            elif abs(candle['close'] - level_price) / level_price * 100 <= 0.2:
                if not self.active_levels.get(level_price):
                    if not self.state_manager.is_silent_mode_active():
                        self.position_manager.send_info_alert(f"⏳ **توجه**: قیمت {self.symbol} به سطح **{level_data['level_type']}** نزدیک شده است.")
                    self.active_levels[level_price] = "Approaching"

    def _aggregate_candles(self, candles):
        if not candles: return None
        return {'open_time': candles[-1]['open_time'], 'high': max(c['high'] for c in candles), 'low': min(c['low'] for c in candles), 'open': candles[0]['open'], 'close': candles[-1]['close'], 'volume': sum(c['volume'] for c in candles), 'taker_buy_base_asset_volume': sum(c['taker_buy_base_asset_volume'] for c in candles)}

    # --- تابع مربوط به ستاپ‌های قدیمی (حذف نشده) ---
    def _check_all_setups(self, candle, timeframe):
        avg_volume = sum(c['volume'] for c in self.candles_1m) / len(self.candles_1m) if self.candles_1m else 0
        for level_price in list(self.active_levels.keys()):
            level_data = next((l for l in self.key_levels if l['level'] == level_price), None)
            if not level_data or not (candle['low'] <= level_price <= candle['high']): continue
            
            alerts = [setup_checkers.check_absorption(candle, avg_volume, level_data), setup_checkers.check_long_tail(candle, level_data)]
            if timeframe == '5m': alerts.append(self.fvg_handler_5m.check_setups(candle, self.key_levels))
            if timeframe == '30m': alerts.append(self.fvg_handler_30m.check_setups(candle, self.key_levels))
            
            for alert in alerts:
                if alert: self._filter_and_process_signal(alert, candle['open_time'], timeframe)

    # --- تابع مربوط به ستاپ‌های قدیمی (حذف نشده) ---
    def _filter_and_process_signal(self, alert_msg, htf_time, timeframe):
        now = datetime.now(timezone.utc)
        alert_key = f"{alert_msg.split('(')[0]}_{htf_time.strftime('%Y%m%d%H')}"
        if self.alert_cooldowns.get(alert_key) and (now - self.alert_cooldowns[alert_key] < timedelta(hours=1)): return

        is_buy = "BULLISH" in alert_msg.upper()
        is_sell = "BEARISH" in alert_msg.upper()
        if (is_buy and "UP" in self.daily_trend) or (is_sell and "DOWN" in self.daily_trend) or "SIDEWAYS" in self.daily_trend:
            direction = 'Buy' if is_buy else 'Sell'
            entry_details = find_ltf_entry_and_sl(self.candles_1m, direction)
            if entry_details:
                signal_package = {'symbol': self.symbol, 'direction': direction, 'setup_type': alert_msg, 'timeframe': timeframe, 'htf_time': htf_time, **entry_details}
                if hasattr(self.position_manager, 'on_new_signal'):
                    self.position_manager.on_new_signal(signal_package)
                self.alert_cooldowns[alert_key] = now

    # --- تابع مربوط به استراتژی جدید (اضافه شده) ---
    def _evaluate_level_interaction(self, candle_5m):
        for level_price, status in list(self.active_levels.items()):
            if status != "Touched": continue
            level_data = next((l for l in self.key_levels if l['level'] == level_price), None)
            if not level_data: continue
            trade_direction = None
            if "UP" in self.daily_trend and level_data['level_type'] in ['PDL', 'VAL', 'POC']: trade_direction = 'Buy'
            elif "DOWN" in self.daily_trend and level_data['level_type'] in ['PDH', 'VAH', 'POC']: trade_direction = 'Sell'
            if not trade_direction: continue
            if check_pin_bar(candle_5m, trade_direction):
                self.create_signal_proposal(level_data, trade_direction, candle_5m)
                del self.active_levels[level_price]

    # --- تابع مربوط به استراتژی جدید (اضافه شده) ---
    def create_signal_proposal(self, level_data, direction, confirmation_candle):
        utc_now = datetime.now(timezone.utc)
        test_count = self.level_test_counts[level_data['level']]
        session = get_trading_session(utc_now.hour)
        reasons = [f"✅ پین‌بار ۵ دقیقه‌ای در جهت روند در سطح {level_data['level_type']} دیده شد.", f"✅ روند کلی روز: {self.daily_trend}", f"✅ تست شماره {test_count} از این سطح."]
        stop_loss = confirmation_candle['low'] if direction == 'Buy' else confirmation_candle['high']
        signal_package = {"symbol": self.symbol, "direction": direction, "level_data": level_data, "reasons": reasons, "session": session, "timestamp": utc_now, "stop_loss_suggestion": stop_loss}
        if hasattr(self.position_manager, 'on_new_proposal'):
            self.position_manager.on_new_proposal(signal_package)

    def run(self):
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m'
        self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
        self.wst = threading.Thread(target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
        self.wst.start()
        print(f'[MasterMonitor] Started for {self.symbol}.')

    def stop(self):
        if self.ws: self.ws.close()