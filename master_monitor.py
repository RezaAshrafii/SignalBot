# master_monitor.py (نسخه نهایی یکپارچه با SetupManager)

import json
import threading
import websocket
import ssl
import time
from collections import deque
from datetime import datetime, timezone
import pandas as pd
from indicators import calculate_atr

def get_trading_session(utc_hour):
    if 1 <= utc_hour < 8: return "Asian Session"
    elif 8 <= utc_hour < 16: return "London Session"
    elif 16 <= utc_hour < 23: return "New York Session"
    else: return "After Hours"

def check_pin_bar(candle, direction):
    candle_range = candle.get('high', 0) - candle.get('low', 0)
    if candle_range == 0: return False
    body = abs(candle.get('open', 0) - candle.get('close', 0))
    if body == 0: body = candle_range / 1000 # برای جلوگیری از تقسیم بر صفر
    upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
    lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
    is_pin_bar_body = body < candle_range / 3
    if direction == 'Buy': return is_pin_bar_body and lower_wick > body * 2
    elif direction == 'Sell': return is_pin_bar_body and upper_wick > body * 2
    return False

class MasterMonitor:
    def __init__(self, symbol, key_levels, daily_trend, setup_manager, position_manager, state_manager):
        self.symbol = symbol
        self.key_levels = key_levels
        self.daily_trend = daily_trend
        self.setup_manager = setup_manager
        self.position_manager = position_manager
        self.state_manager = state_manager
        self.candles_1m = deque(maxlen=300) # تاریخچه برای تحلیل‌های ستاپ
        self.current_5m_buffer = []
        self.ws = None
        self.wst = None
        self.stop_requested = threading.Event()

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('e') == 'kline' and data['k']['x']:
                self.process_candle(data['k'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[{self.symbol}] Error processing message: {e}")

    def on_error(self, ws, error):
        print(f"[{self.symbol}] WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[{self.symbol}] WebSocket Connection Closed.")

    def _run_forever(self):
        """حلقه‌ای که اتصال وب‌ساکت را پایدار نگه می‌دارد."""
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m'
        while not self.stop_requested.is_set():
            print(f"[{self.symbol}] Connecting to WebSocket...")
            self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
            self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})
            if not self.stop_requested.is_set():
                print(f"[{self.symbol}] WebSocket disconnected. Retrying in 10 seconds...")
                time.sleep(10)

    def process_candle(self, kline_data):
        kline_1m = {'open_time': datetime.fromtimestamp(int(kline_data['t']) / 1000, tz=timezone.utc), 'open': float(kline_data['o']), 'high': float(kline_data['h']), 'low': float(kline_data['l']), 'close': float(kline_data['c']), 'volume': float(kline_data['v'])}
        self.candles_1m.append(kline_1m)
        self.current_5m_buffer.append(kline_1m)
        self.state_manager.update_symbol_state(self.symbol, 'last_price', kline_1m['close'])
        
        kline_5m = None
        if (kline_1m['open_time'].minute + 1) % 5 == 0 and kline_1m['open_time'].second >= 58:
            kline_5m = self._aggregate_candles(self.current_5m_buffer)
            self.current_5m_buffer = []

        # --- [اصلاح اصلی] --- ساخت پکیج داده صحیح
        # استخراج سطوح PDH/PDL و پروفایل حجمی از لیست key_levels
        levels_dict = {}
        for lvl in self.key_levels:
            # فرض می‌کنیم تاریخ سطوح در 'date' ذخیره شده و به فرمت YYYY-MM-DD است
            # و ما فقط به سطوح روز گذشته نیاز داریم. این منطق می‌تواند بهبود یابد.
            levels_dict[lvl['level_type'].lower()] = lvl['level']
        
        # ساخت پکیج داده کامل
        kwargs = {
            'symbol': self.symbol,
            'price_data': pd.DataFrame(list(self.candles_1m)),
            'levels': levels_dict,  # <-- ارسال دیکشنری صحیح از سطوح
            'key_levels': self.key_levels,
            'kline_1m': kline_1m,
            'kline_5m': kline_5m,
            'kline_history': self.candles_1m,
            'daily_trend': self.daily_trend,
        }
        
        signal_package = self.setup_manager.check_all_setups(**kwargs)
        
        if signal_package:
            signal_package['symbol'] = self.symbol
            signal_package['timestamp'] = datetime.now(timezone.utc)
            if hasattr(self.position_manager, 'on_new_proposal'):
                self.position_manager.on_new_proposal(signal_package)

    def _aggregate_candles(self, candles):
        if not candles: return None
        return {'open_time': candles[-1]['open_time'], 'high': max(c['high'] for c in candles),
                'low': min(c['low'] for c in candles), 'open': candles[0]['open'],
                'close': candles[-1]['close'], 'volume': sum(c['volume'] for c in candles)}

    def _check_level_proximity(self, candle):
        for level_data in self.key_levels:
            level_price = level_data['level']
            if candle['low'] <= level_price <= candle['high']:
                if self.active_levels.get(level_price) != "Touched":
                    self.position_manager.send_info_alert(f"🎯 **برخورد**: قیمت {self.symbol} سطح **{level_data['level_type']}** را لمس کرد.")
                    self.active_levels[level_price] = "Touched"
                    self.level_test_counts[level_price] += 1
                    self.state_manager.update_symbol_state(self.symbol, 'level_test_counts', dict(self.level_test_counts))

    def _aggregate_candles(self, candles):
        if not candles: return None
        return {'open_time': candles[-1]['open_time'], 'high': max(c['high'] for c in candles), 'low': min(c['low'] for c in candles), 'open': candles[0]['open'], 'close': candles[-1]['close'], 'volume': sum(c['volume'] for c in candles)}

    def _evaluate_level_interaction(self, candle_5m):
        trend = self.state_manager.get_symbol_state(self.symbol, 'htf_trend', 'SIDEWAYS')
        for level_price, status in list(self.active_levels.items()):
            if status != "Touched": continue
            level_data = next((l for l in self.key_levels if l['level'] == level_price), None)
            if not level_data: continue
            
            trade_direction = None
            if "UP" in trend:
                if level_data['level_type'] in ['PDL', 'VAL', 'POC'] or 'low' in level_data['level_type'].lower(): trade_direction = 'Buy'
            elif "DOWN" in trend:
                if level_data['level_type'] in ['PDH', 'VAH', 'POC'] or 'high' in level_data['level_type'].lower(): trade_direction = 'Sell'
            
            if not trade_direction: continue
            
            if check_pin_bar(candle_5m, trade_direction):
            # ۱. ارسال هشدار اولیه مبنی بر مشاهده پین‌بار
                self.position_manager.send_info_alert(
                    f"📍 **تاییدیه پین‌بار**: یک پین‌بار {trade_direction} در سطح {level_data['level_type']} برای {self.symbol} مشاهده شد."
                )
            
            # ۲. ساخت و ارسال پیشنهاد سیگنال کامل
            self.create_signal_proposal(level_data, trade_direction, candle_5m)
            del self.active_levels[level_price]

    def create_signal_proposal(self, level_data, direction, confirmation_candle):
        """یک پکیج سیگنال کامل و بی‌نقص ایجاد می‌کند."""
        utc_now = datetime.now(timezone.utc)
        test_count = self.level_test_counts[level_data['level']]
        session = get_trading_session(utc_now.hour)
        
        # --- منطق جدید برای تاییدیه ورود و محاسبه SL/TP ---
        df_1m = pd.DataFrame(list(self.candles_1m))
        atr_1m = calculate_atr(df_1m, period=14)
        if atr_1m == 0: return # اگر نوسان صفر بود، سیگنال نده
        
        entry_price = confirmation_candle['high'] + (atr_1m * 0.25) if direction == 'Buy' else confirmation_candle['low'] - (atr_1m * 0.25)
        stop_loss = confirmation_candle['low'] - (atr_1m * 0.2) if direction == 'Buy' else confirmation_candle['high'] + (atr_1m * 0.2)
        
        reasons = [
            f"✅ پین‌بار ۵ دقیقه‌ای در سطح **{level_data['level_type']}**",
            f"✅ همسو با روند روز: **{self.state_manager.get_symbol_state(self.symbol, 'htf_trend')}**",
            f"✅ تست شماره **{test_count}** از این سطح",
            f"✅ ورود با تاییدیه شکست نوسان (ATR)"
        ]
        
        signal_package = {
            "symbol": self.symbol, "direction": direction,
            "entry_price": entry_price, "stop_loss": stop_loss,
            "reasons": reasons, "session": session, "timestamp": utc_now
        }
        
        if hasattr(self.position_manager, 'on_new_proposal'):
            self.position_manager.on_new_proposal(signal_package)


    def run(self):
        """کانکشن وب‌ساکت را در یک ترد جداگانه اجرا می‌کند."""
        self.stop_requested.clear()
        self.wst = threading.Thread(target=self._run_forever, daemon=True)
        self.wst.start()
        print(f'[MasterMonitor] WebSocket started for {self.symbol}.')

    def stop(self):
        """وب‌ساکت را متوقف می‌کند."""
        print(f"Stopping monitor for {self.symbol}...")
        self.stop_requested.set()
        if self.ws:
            self.ws.close()