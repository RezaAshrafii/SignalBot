# master_monitor.py

import json
import threading
import websocket
import ssl
from collections import deque
from datetime import datetime, timezone

class MasterMonitor:
    def __init__(self, symbol, key_levels, daily_trend, setup_manager, position_manager, state_manager):
        # --- وابستگی‌ها و متغیرهای اصلی ---
        self.symbol = symbol
        self.key_levels = key_levels
        self.daily_trend = daily_trend # روند کلی روز که از بیرون به آن داده می‌شود
        
        # --- ماژول‌های خارجی ---
        self.setup_manager = setup_manager
        self.position_manager = position_manager
        self.state_manager = state_manager
        
        # --- بافرهای داده ---
        self.candles_1m = deque(maxlen=300) # تاریخچه کافی برای همه ستاپ‌ها
        self.current_5m_buffer = [] # برای ساخت کندل‌های ۵ دقیقه
        
        # --- مدیریت WebSocket ---
        self.ws = None
        self.wst = None

    def on_message(self, ws, message):
        """این متد با هر پیام جدید از وب‌ساکت فراخوانی می‌شود."""
        try:
            data = json.loads(message)
            # ما فقط به کندل‌های بسته شده علاقه داریم
            if data.get('e') == 'kline' and data['k']['x']:
                self.process_candle(data['k'])
        except (json.JSONDecodeError, KeyError) as e:
            print(f"[{self.symbol}] Error processing message: {e}")

    def on_error(self, ws, error):
        print(f"[{self.symbol}] WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"[{self.symbol}] WebSocket Connection Closed.")

    def process_candle(self, kline_data):
        """
        قلب تپنده مانیتور؛ داده‌ها را پردازش و برای تحلیل ارسال می‌کند.
        """
        # ۱. ساخت کندل ۱ دقیقه‌ای استاندارد
        kline_1m = {
            'open_time': datetime.fromtimestamp(int(kline_data['t']) / 1000, tz=timezone.utc),
            'open': float(kline_data['o']),
            'high': float(kline_data['h']),
            'low': float(kline_data['l']),
            'close': float(kline_data['c']),
            'volume': float(kline_data['v'])
        }
        self.candles_1m.append(kline_1m)
        self.current_5m_buffer.append(kline_1m)
        
        # ۲. ساخت کندل ۵ دقیقه‌ای در زمان مناسب
        kline_5m = None
        # اگر در ثانیه‌های پایانی یک کندل ۵ دقیقه‌ای هستیم
        if (kline_1m['open_time'].minute + 1) % 5 == 0 and kline_1m['open_time'].second >= 58:
            kline_5m = self._aggregate_candles(self.current_5m_buffer)
            self.current_5m_buffer = []

        # ۳. آماده‌سازی پکیج داده برای ارسال به مدیر ستاپ‌ها
        kwargs = {
            'symbol': self.symbol,
            'kline_1m': kline_1m,          # کندل ۱ دقیقه فعلی
            'kline_5m': kline_5m,          # کندل ۵ دقیقه (اگر تشکیل شده باشد، در غیر این صورت None)
            'kline_history': self.candles_1m, # کل تاریخچه کندل‌های ۱ دقیقه
            'key_levels': self.key_levels,   # لیست تمام سطوح کلیدی
            'daily_trend': self.daily_trend, # جهت کلی روند روز
        }
        
        # ۴. ارسال داده‌ها به SetupManager برای بررسی تمام استراتژی‌ها
        signal_package = self.setup_manager.check_all_setups(**kwargs)
        
        # ۵. اگر سیگنالی پیدا شد، آن را به مدیر پوزیشن ارسال کن
        if signal_package:
            # افزودن اطلاعات تکمیلی به پکیج سیگنال
            signal_package['symbol'] = self.symbol
            signal_package['timestamp'] = datetime.now(timezone.utc)
            
            # ارسال به PositionManager برای مدیریت و ارسال به تلگرام
            if hasattr(self.position_manager, 'on_new_proposal'):
                self.position_manager.on_new_proposal(signal_package)

    def _aggregate_candles(self, candles):
        """چند کندل ۱ دقیقه را به یک کندل ۵ دقیقه تبدیل می‌کند."""
        if not candles: return None
        return {
            'open_time': candles[-1]['open_time'],
            'high': max(c['high'] for c in candles),
            'low': min(c['low'] for c in candles),
            'open': candles[0]['open'],
            'close': candles[-1]['close'],
            'volume': sum(c['volume'] for c in candles)
        }

    def run(self):
        """کانکشن وب‌ساکت را در یک ترد جداگانه اجرا می‌کند."""
        ws_url = f'wss://fstream.binance.com/ws/{self.symbol.lower()}@kline_1m'
        self.ws = websocket.WebSocketApp(ws_url, on_message=self.on_message, on_error=self.on_error, on_close=self.on_close)
        self.wst = threading.Thread(target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}), daemon=True)
        self.wst.start()
        print(f'[MasterMonitor] WebSocket started for {self.symbol}.')

    def stop(self):
        """وب‌ساکت را متوقف می‌کند."""
        if self.ws:
            self.ws.close()