# master_monitor.py (نسخه پایدار با اتصال مجدد خودکار)

import json
import threading
import websocket
import ssl
import time
from collections import deque
from datetime import datetime, timezone
import pandas as pd

class MasterMonitor:
    def __init__(self, symbol, key_levels, daily_trend, setup_manager, position_manager, state_manager):
        self.symbol = symbol
        self.key_levels = key_levels
        self.daily_trend = daily_trend
        self.setup_manager = setup_manager
        self.position_manager = position_manager
        self.state_manager = state_manager
        self.candles_1m = deque(maxlen=300)
        self.current_5m_buffer = []
        self.ws = None
        self.wst = None
        self.stop_requested = threading.Event() # برای توقف ترد

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
        print(f"[{self.symbol}] WebSocket Connection Closed. Attempting to reconnect...")

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
        kline_1m = {
            'open_time': datetime.fromtimestamp(int(kline_data['t']) / 1000, tz=timezone.utc),
            'open': float(kline_data['o']), 'high': float(kline_data['h']),
            'low': float(kline_data['l']), 'close': float(kline_data['c']),
            'volume': float(kline_data['v'])
        }
        self.candles_1m.append(kline_1m)
        self.current_5m_buffer.append(kline_1m)
        
        kline_5m = None
        if (kline_1m['open_time'].minute + 1) % 5 == 0 and kline_1m['open_time'].second >= 58:
            kline_5m = self._aggregate_candles(self.current_5m_buffer)
            self.current_5m_buffer = []

        # --- [بخش اصلاح شده برای حل خطای دوم] ---
        # ساخت دیتافریم کامل از تاریخچه کندل‌ها برای ستاپ‌هایی که به آن نیاز دارند
        price_data_df = pd.DataFrame(list(self.candles_1m))

        # ساخت پکیج داده کامل با تمام کلیدهای مورد نیاز همه ستاپ‌ها
        kwargs = {
            'symbol': self.symbol,
            'price_data': price_data_df,      # دیتافریم کامل برای تحلیل
            'levels': self.key_levels,         # نام 'levels' همان چیزی است که ستاپ انتظار دارد
            'key_levels': self.key_levels,     # برای سازگاری با ستاپ پین‌بار
            'kline_1m': kline_1m,            # کندل ۱ دقیقه فعلی
            'kline_5m': kline_5m,            # کندل ۵ دقیقه (اگر تشکیل شده باشد)
            'kline_history': self.candles_1m,  # تاریخچه کندل‌ها به صورت deque
            'daily_trend': self.daily_trend,   # جهت کلی روند روز
        }
        # --- پایان بخش اصلاح شده ---
        
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