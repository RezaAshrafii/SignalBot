import threading
import pandas as pd
from datetime import datetime, timezone
from collections import defaultdict

class StateManager:
    def __init__(self, symbols):
        self._locks = defaultdict(threading.Lock)
        # وضعیت کلی ربات که بین تمام ماژول‌ها مشترک است
        self._shared_state = {symbol: {} for symbol in symbols}
        # --- [تغییر] اضافه کردن وضعیت برای معامله خودکار ---
        self._shared_state['__app__'] = {
            'is_silent': False,
            'is_autotrade_enabled': False  # وضعیت پیش‌فرض برای ترید خودکار
        }
    def update_symbol_state(self, symbol, key, value):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن آپدیت می‌کند."""
        with self._locks[symbol]:
            if symbol not in self._shared_state: self._shared_state[symbol] = {}
            self._shared_state[symbol][key] = value

    def get_symbol_state(self, symbol, key, default=None):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن می‌خواند."""
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).get(key, default)

    # --- [بخش اضافه شده برای رفع خطا و هماهنگی کامل] ---
    def toggle_autotrade(self):
        """وضعیت معامله خودکار را تغییر می‌دهد و وضعیت جدید را برمی‌گرداند."""
        with self._locks['__app__']:
            current_status = self._shared_state['__app__'].get('is_autotrade_enabled', False)
            new_status = not current_status
            self._shared_state['__app__']['is_autotrade_enabled'] = new_status
            print(f"[StateManager] Auto-Trade status toggled to: {new_status}")
            return new_status

    # --- [تابع جدید] ---
    def is_autotrade_enabled(self):
        """وضعیت فعلی معامله خودکار را برمی‌گرداند."""
        with self._locks['__app__']:
            return self._shared_state['__app__'].get('is_autotrade_enabled', False)

    def get_symbol_snapshot(self, symbol):
        """یک کپی از وضعیت کامل یک نماد خاص را برمی‌گرداند."""
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).copy()

    def get_all_symbols(self):
        with self._locks['__global__']:
            return [s for s in self._shared_state.keys() if s != '__app__']

    def get_symbol_snapshot(self, symbol):
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).copy()
    
    # تابع get_full_symbol_state که باعث خطا شده بود، اکنون با نام صحیح get_symbol_snapshot جایگزین شده
    # اما برای سازگاری، یک کپی از آن با نام قدیمی نیز نگه می‌داریم.
    def get_full_symbol_state(self, symbol):
        return self.get_symbol_snapshot(symbol)

    def toggle_silent_mode(self):
        """وضعیت حالت سکوت را تغییر می‌دهد."""
        with self._locks['__app__']:
            is_silent = not self._shared_state['__app__'].get('is_silent', False)
            self._shared_state['__app__']['is_silent'] = is_silent
            print(f"[StateManager] Silent mode toggled to: {is_silent}")
            return is_silent
    
    def is_silent_mode_active(self):
        """وضعیت فعلی حالت سکوت را برمی‌گرداند."""
        with self._locks['__app__']:
            return self._shared_state['__app__'].get('is_silent', False)

    def get_level_alert_time(self, symbol, level_id):
        """زمان آخرین هشدار برای یک سطح خاص را دریافت می‌کند."""
        with self._locks[symbol]:
            return self.get_symbol_state(symbol, f"cooldown_{level_id}", 0)
    
    def update_level_alert_time(self, symbol, level_id):
        """زمان آخرین هشدار برای یک سطح را به‌روز می‌کند."""
        import time
        with self._locks[symbol]:
            self.update_symbol_state(symbol, f"cooldown_{level_id}", time.time())
    # ==============================================================================
    # +++ توابع کمکی جدید برای سازگاری با بک‌تست و auto_trade.py +++
    # ==============================================================================
    
    def add_candle(self, new_candle: dict):
        """
        یک کندل جدید را به داده‌های تاریخی اولین ارز در لیست اضافه می‌کند.
        این تابع برای سادگی در حالت بک‌تست تک-ارزی طراحی شده است.
        """
        if not self.symbols:
            return
            
        # اولین ارز را به عنوان ارز پیش‌فرض برای بک‌تست در نظر می‌گیریم
        target_symbol = self.symbols[0]
        
        # ساخت دیتافریم از کندل جدید و تنظیم ایندکس زمانی
        new_df = pd.DataFrame([new_candle])
        if 'timestamp' in new_df.columns:
            new_df['timestamp'] = pd.to_datetime(new_df['timestamp'])
            new_df.set_index('timestamp', inplace=True)
        
        # الحاق دیتافریم جدید به داده‌های تاریخی
        historical_data = self.states[target_symbol]['historical_data']
        self.states[target_symbol]['historical_data'] = pd.concat([historical_data, new_df])

        # به‌روزرسانی آخرین قیمت
        self.update_symbol_state(target_symbol, 'last_price', new_candle['close'])

    def get_candles(self) -> pd.DataFrame:
        """داده‌های تاریخی اولین ارز را برمی‌گرداند."""
        if not self.symbols:
            return pd.DataFrame()
        target_symbol = self.symbols[0]
        return self.states.get(target_symbol, {}).get('historical_data', pd.DataFrame())

    def get_current_price(self) -> float:
        """آخرین قیمت اولین ارز را برمی‌گرداند."""
        candles = self.get_candles()
        if not candles.empty:
            return candles.iloc[-1]['close']
        return 0.0

    def get_current_time(self):
        """آخرین زمان اولین ارز را برمی‌گرداند."""
        candles = self.get_candles()
        if not candles.empty:
            return candles.index[-1]
        return None
