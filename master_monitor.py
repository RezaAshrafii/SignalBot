# master_monitor.py
import json, threading, websocket, ssl
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta
import pandas as pd
import setup_checkers
from fvg_logic import FvgLogic

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
    def __init__(self, key_levels, symbol, daily_trend, position_manager):
        self.key_levels = key_levels
        self.symbol = symbol
        self.daily_trend = daily_trend
        self.position_manager = position_manager
        
        self.candles_1m = deque(maxlen=60)
        self.candles_5m = deque(maxlen=5)
        self.candles_30m = deque(maxlen=5)
        
        self.current_5m_buffer, self.current_30m_buffer = [], []
        self.active_levels = {}
        self.alert_cooldowns = defaultdict(lambda: None)
        
        self.fvg_handler_5m = FvgLogic()
        self.fvg_handler_30m = FvgLogic()
        
        self.ws = None # برای نگهداری نمونه وب‌ساکت
        self.wst = None # برای نگهداری ترد وب‌ساکت

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if 'k' in data and data['k']['x']: self.process_candle(data['k'])
        except Exception: pass

    def on_error(self, ws, error):
        print(f"[MasterMonitor][{self.symbol}] WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[MasterMonitor][{self.symbol}] WebSocket Connection Closed.")

    def process_candle(self, kline):
        candle = {'open_time': datetime.fromtimestamp(int(kline['t'])/1000, tz=timezone.utc), 'open': float(kline['o']), 'high': float(kline['h']), 'low': float(kline['l']), 'close': float(kline['c']), 'volume': float(kline['v']), 'taker_buy_base_asset_volume': float(kline['q'])}
        self.candles_1m.append(candle)
        now = datetime.now(timezone.utc)
        self.current_5m_buffer.append(candle)
        self.current_30m_buffer.append(candle)

        for level_data in self.key_levels:
            level_price = level_data['level']
            if self._is_near_level(candle, level_data):
                if level_price not in self.active_levels:
                    self.position_manager.send_info_alert(f"**توجه:** قیمت `{self.symbol}` به سطح کلیدی `{level_data['level_type']}` در `{level_price:,.2f}` رسید. نظارت فعال ۳ ساعته آغاز شد.")
                    self.active_levels[level_price] = {'timestamp': now, 'touch_count': 1}
        
        dt_object = candle['open_time']
        if (dt_object.minute + 1) % 5 == 0 and dt_object.second >= 58:
            candle_5m = self._aggregate_candles(self.current_5m_buffer)
            if candle_5m: self.candles_5m.append(candle_5m); self._check_all_setups(candle_5m, '5m')
            self.current_5m_buffer = []
        if (dt_object.minute + 1) % 30 == 0 and dt_object.second >= 58:
            candle_30m = self._aggregate_candles(self.current_30m_buffer)
            if candle_30m: self.candles_30m.append(candle_30m); self._check_all_setups(candle_30m, '30m')
            self.current_30m_buffer = []

        expired = [lvl for lvl, data in self.active_levels.items() if now - data['timestamp'] > timedelta(hours=3)]
        for lvl in expired:
            if lvl in self.active_levels:
                del self.active_levels[lvl]

    def _check_all_setups(self, candle, timeframe):
        avg_volume = sum(c['volume'] for c in self.candles_1m) / len(self.candles_1m) if self.candles_1m else 0
        for level_price in list(self.active_levels.keys()):
            level_data = next((l for l in self.key_levels if l['level'] == level_price), None)
            if not level_data or not self._is_near_level(candle, level_data): continue
            
            alerts = [
                setup_checkers.check_absorption(candle, avg_volume, level_data),
                setup_checkers.check_long_tail(candle, level_data)
            ]
            if timeframe == '5m': alerts.append(self.fvg_handler_5m.check_setups(candle, self.key_levels))
            if timeframe == '30m': alerts.append(self.fvg_handler_30m.check_setups(candle, self.key_levels))
            
            for alert in alerts:
                if alert: self._filter_and_process_signal(alert, candle['open_time'], timeframe)

    def _filter_and_process_signal(self, alert_msg, htf_time, timeframe):
        now = datetime.now(timezone.utc);
        alert_key = f"{alert_msg.split('(')[0]}_{htf_time.strftime('%Y%m%d%H')}"
        if self.alert_cooldowns.get(alert_key) and (now - self.alert_cooldowns[alert_key] < timedelta(hours=1)): return

        is_buy, is_sell = "خرید" in alert_msg, "فروش" in alert_msg
        trend_is_up, trend_is_down, trend_is_sideways = "UP" in self.daily_trend, "DOWN" in self.daily_trend, "SIDEWAYS" in self.daily_trend
        
        if (is_buy and trend_is_up) or (is_sell and trend_is_down) or trend_is_sideways:
            direction = 'Buy' if is_buy else 'Sell'
            entry_details = find_ltf_entry_and_sl(self.candles_1m, direction)
            if entry_details:
                signal_package = { 'symbol': self.symbol, 'direction': direction, 'setup_type': alert_msg, 'timeframe': timeframe, 'htf_time': htf_time, **entry_details }
                self.position_manager.on_new_signal(signal_package)
                self.alert_cooldowns[alert_key] = now

    def _is_near_level(self, candle, level_data, proximity_percent=0.002):
        return (candle['low'] - (level_data['level'] * proximity_percent)) <= level_data['level'] <= (candle['high'] + (level_data['level'] * proximity_percent))

    def _aggregate_candles(self, candles):
        if not candles: return None
        return {'open_time': candles[-1]['open_time'], 'high': max(c['high'] for c in candles), 'low': min(c['low'] for c in candles),'open': candles[0]['open'], 'close': candles[-1]['close'], 'volume': sum(c['volume'] for c in candles), 'taker_buy_base_asset_volume': sum(c['taker_buy_base_asset_volume'] for c in candles)}

    def run(self):
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m'
        self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
        self.wst = threading.Thread(target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
        self.wst.start()
        print(f'[MasterMonitor] Started for {self.symbol}.')

    def stop(self):
        if self.ws:
            self.ws.close()
            print(f"[MasterMonitor] Stopped for {self.symbol}.")