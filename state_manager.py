# state_manager.py

import pandas as pd
from datetime import datetime, timezone

class StateManager:
    def __init__(self, symbols, data_fetcher=None):
        # اگر ورودی یک رشته بود، آن را به لیست تبدیل کن (برای سازگاری با بک‌تست)
        if isinstance(symbols, str):
            symbols = [symbols]
            
        self.symbols = symbols
        self.data_fetcher = data_fetcher
        self.states = {symbol: {
            'last_price': None,
            'last_update_time': None,
            'historical_data': pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        } for symbol in symbols}

    def update_symbol_state(self, symbol, key, value):
        if symbol in self.states:
            self.states[symbol][key] = value
            self.states[symbol]['last_update_time'] = datetime.now(timezone.utc)

    def get_symbol_state(self, symbol, key):
        return self.states.get(symbol, {}).get(key, None)

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
