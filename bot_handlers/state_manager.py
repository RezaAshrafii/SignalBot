# state_manager.py
import threading

class StateManager:
    """
    این کلاس به عنوان یک مدیر وضعیت مرکزی و thread-safe عمل می‌کند.
    تمام اطلاعات مربوط به هر نماد معاملاتی (symbol) مانند قیمت لحظه‌ای،
    روند تایم فریم بالا (HTF)، و سطوح کلیدی در اینجا ذخیره و مدیریت می‌شود.
    """
    def __init__(self, symbols):
        """
        ساختار اولیه وضعیت را برای تمام نمادهای مشخص شده ایجاد می‌کند.
        """
        self._state = {symbol: {} for symbol in symbols}
        self._lock = threading.Lock()  # قفل برای جلوگیری از تداخل در دسترسی‌های همزمان (race condition)

    def update_symbol_state(self, symbol, key, value):
        """
        یک مقدار خاص را در وضعیت یک نماد به‌روزرسانی می‌کند.
        
        Args:
            symbol (str): نماد معاملاتی (مانند 'BTCUSDT').
            key (str): کلید داده (مانند 'last_price' یا 'htf_trend').
            value (any): مقدار جدید برای ذخیره‌سازی.
        """
        with self._lock:
            if symbol in self._state:
                self._state[symbol][key] = value

    def get_symbol_state(self, symbol, key):
        """
        یک مقدار خاص را از وضعیت یک نماد بازیابی می‌کند.
        
        Args:
            symbol (str): نماد معاملاتی.
            key (str): کلید داده مورد نظر.
            
        Returns:
            مقدار ذخیره شده یا None اگر وجود نداشته باشد.
        """
        with self._lock:
            return self._state.get(symbol, {}).get(key)

    def get_full_state(self):
        """
        یک کپی از کل وضعیت تمام نمادها را برمی‌گرداند.
        این متد برای نمایش اطلاعات در ربات تلگرام استفاده می‌شود.
        
        Returns:
            dict: کپی از دیکشنری وضعیت.
        """
        with self._lock:
            return self._state.copy()