# state_manager.py
import threading

class StateManager:
    def __init__(self, symbols):
        self._state = {symbol: {} for symbol in symbols}
        # --- [بخش جدید] --- برای نگهداری تنظیمات کلی مانند حالت سکوت
        self._global_state = {
            'silent_mode': False 
        }
        self._lock = threading.Lock()

    def update_symbol_state(self, symbol, key, value):
        """یک مقدار خاص را در وضعیت یک نماد به‌روزرسانی می‌کند."""
        with self._lock:
            if symbol in self._state:
                self._state[symbol][key] = value

    def get_symbol_state(self, symbol, key):
        """یک مقدار خاص را از وضعیت یک نماد بازیابی می‌کند."""
        with self._lock:
            return self._state.get(symbol, {}).get(key)

    def get_full_state(self):
        """یک کپی از کل وضعیت تمام نمادها را برمی‌گرداند."""
        with self.lock:
            return self._state.copy()
            
    def get_all_symbols(self):
        """لیست تمام نمادهای تحت نظر را برمی‌گرداند."""
        with self._lock:
            return list(self._state.keys())

    def get_symbol_snapshot(self, symbol):
        """یک کپی از وضعیت کامل یک نماد خاص را برمی‌گرداند."""
        with self._lock:
            return self._state.get(symbol, {}).copy()

    # --- [توابع جدید] --- برای مدیریت حالت سکوت
    def toggle_silent_mode(self):
        """وضعیت حالت سکوت را تغییر می‌دهد (روشن به خاموش و بالعکس)."""
        with self._lock:
            self._global_state['silent_mode'] = not self._global_state['silent_mode']
            print(f"[StateManager] Silent mode toggled to: {self._global_state['silent_mode']}")
            return self._global_state['silent_mode']

    def is_silent_mode_active(self):
        """وضعیت فعلی حالت سکوت را برمی‌گرداند."""
        with self._lock:
            return self._global_state['silent_mode']