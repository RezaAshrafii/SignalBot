# state_manager.py
import threading
import pandas as pd
from datetime import datetime, timezone

class StateManager:
    """
    این کلاس به عنوان یک مدیر وضعیت مرکزی و thread-safe عمل می‌کند.
    تمام اطلاعات مربوط به هر نماد و تنظیمات کلی برنامه در اینجا ذخیره می‌شود.
    """
    def __init__(self, symbols):
        if isinstance(symbols, str):
            symbols = [symbols]
            
        # این دیکشنری وضعیت هر نماد را نگهداری می‌کند
        self._state = {symbol: {} for symbol in symbols}
        
        # این دیکشنری وضعیت کلی و تنظیمات برنامه را نگهداری می‌کند
        self._global_state = {
            'silent_mode': False
        }
        
        # یک قفل برای جلوگیری از تداخل در دسترسی‌های همزمان از ترد‌های مختلف
        self._lock = threading.Lock()

    def update_symbol_state(self, symbol, key, value):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن آپدیت می‌کند."""
        with self._lock:
            if symbol not in self._state:
                self._state[symbol] = {}
            self._state[symbol][key] = value

    def get_symbol_state(self, symbol, key, default=None):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن می‌خواند."""
        with self._lock:
            return self._state.get(symbol, {}).get(key, default)

    def get_all_symbols(self):
        """لیست تمام نمادهای تحت نظر را برمی‌گرداند."""
        with self._lock:
            return list(self._state.keys())

    def get_symbol_snapshot(self, symbol):
        """یک کپی از وضعیت کامل یک نماد خاص را برمی‌گرداند."""
        with self._lock:
            return self._state.get(symbol, {}).copy()

    def toggle_silent_mode(self):
        """وضعیت حالت سکوت را تغییر می‌دهد (روشن به خاموش و بالعکس)."""
        with self._lock:
            self._global_state['silent_mode'] = not self._global_state.get('silent_mode', False)
            print(f"[StateManager] Silent mode toggled to: {self._global_state['silent_mode']}")
            return self._global_state['silent_mode']

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
