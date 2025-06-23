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
    if 1 <= utc_hour < 8: return "Asian Session"
    elif 8 <= utc_hour < 16: return "London Session"
    elif 16 <= utc_hour < 23: return "New York Session"
    else: return "After Hours"

def check_pin_bar(candle, direction):
    candle_range = candle.get('high', 0) - candle.get('low', 0)
    if candle_range == 0: return False
    body = abs(candle.get('open', 0) - candle.get('close', 0))
    upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
    lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
    is_pin_bar_body = body < candle_range / 3
    if direction == 'Buy': return is_pin_bar_body and lower_wick > body * 2
    elif direction == 'Sell': return is_pin_bar_body and upper_wick > body * 2
    return False

class MasterMonitor:
    def __init__(self, key_levels, symbol, daily_trend, position_manager, state_manager):
        self.key_levels = key_levels; self.symbol = symbol; self.daily_trend = daily_trend
        self.position_manager = position_manager; self.state_manager = state_manager
        self.candles_1m = deque(maxlen=100) # افزایش تاریخچه برای چارت بهتر
        self.candles_5m = deque(maxlen=60)
        self.active_levels = {}; self.alert_cooldowns = defaultdict(lambda: None)
        self.level_test_counts = defaultdict(int); self.ws = None; self.wst = None
        self.current_5m_buffer = []

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('e') == 'kline' and data['k']['x']: self.process_candle(data['k'])
        except (json.JSONDecodeError, KeyError) as e: print(f"[{self.symbol}] Error processing message: {e}")

    def on_error(self, ws, error): print(f"[{self.symbol}] WebSocket Error: {error}")
    def on_close(self, ws, close_status_code, close_msg): print(f"[{self.symbol}] WebSocket Connection Closed.")

    def process_candle(self, kline):
        candle = {'open_time': datetime.fromtimestamp(int(kline['t'])/1000, tz=timezone.utc), 'open': float(kline['o']), 'high': float(kline['h']), 'low': float(kline['l']), 'close': float(kline['c']), 'volume': float(kline['v'])}
        self.state_manager.update_symbol_state(self.symbol, 'last_price', candle['close'])
        self.candles_1m.append(candle)
        self.state_manager.update_symbol_state(self.symbol, 'klines_1m', list(self.candles_1m))
        self._check_level_proximity(candle)
        self.current_5m_buffer.append(candle)
        if (candle['open_time'].minute + 1) % 5 == 0 and candle['open_time'].second >= 58:
            candle_5m = self._aggregate_candles(self.current_5m_buffer)
            self.current_5m_buffer = []
            if candle_5m: self.candles_5m.append(candle_5m); self._evaluate_level_interaction(candle_5m)

    def _check_level_proximity(self, candle, proximity_percent=0.2):
        for level_data in self.key_levels:
            level_price = level_data['level']
            if candle['low'] <= level_price <= candle['high']:
                if self.active_levels.get(level_price) != "Touched":
                    self.position_manager.send_info_alert(f"🎯 **برخورد**: قیمت {self.symbol} سطح **{level_data['level_type']}** را لمس کرد.")
                    self.active_levels[level_price] = "Touched"
                    # --- [ویژگی جدید] --- آپدیت شمارنده تست در حافظه اشتراکی
                    self.level_test_counts[level_price] += 1
                    self.state_manager.update_symbol_state(self.symbol, 'level_test_counts', dict(self.level_test_counts))


    def _aggregate_candles(self, candles):
        if not candles: return None
        return {'open_time': candles[-1]['open_time'], 'high': max(c['high'] for c in candles), 'low': min(c['low'] for c in candles), 'open': candles[0]['open'], 'close': candles[-1]['close'], 'volume': sum(c['volume'] for c in candles)}

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

    def create_signal_proposal(self, level_data, direction, confirmation_candle):
        utc_now = datetime.now(timezone.utc)
        test_count = self.level_test_counts[level_data['level']]
        session = get_trading_session(utc_now.hour)
        reasons = [f"✅ پین‌بار ۵ دقیقه‌ای در جهت روند در سطح {level_data['level_type']} دیده شد.", f"✅ روند کلی روز: {self.daily_trend}", f"✅ تست شماره {test_count} از این سطح."]
        stop_loss = confirmation_candle['low'] if direction == 'Buy' else confirmation_candle['high']
        signal_package = {"symbol": self.symbol, "direction": direction, "level_data": level_data, "reasons": reasons, "session": session, "timestamp": utc_now, "stop_loss_suggestion": stop_loss}
        if hasattr(self.position_manager, 'on_new_proposal'): self.position_manager.on_new_proposal(signal_package)



    def run(self):
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m'
        self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
        self.wst = threading.Thread(target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
        self.wst.start()
        print(f'[MasterMonitor] Started for {self.symbol}.')

    def stop(self):
        if self.ws: self.ws.close()