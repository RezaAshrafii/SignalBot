# posmanagerfunc/state_manager.py
import threading

class StateManager:
    def __init__(self, symbols):
        self._state = {symbol: {} for symbol in symbols}
        # --- [ویژگی جدید] --- برای نگهداری تنظیمات کلی مانند حالت سکوت
        
        self._global_state = {
            'silent_mode': False 
        }
        self._lock = threading.Lock()

    def update_symbol_state(self, symbol, key, value):
        with self._lock:
            if symbol in self._state: self._state[symbol][key] = value

    def get_symbol_state(self, symbol, key):
        with self._lock: return self._state.get(symbol, {}).get(key)

    def get_full_state(self):
        with self._lock: return self._state.copy()
            
    def get_all_symbols(self):
        with self._lock: return list(self._state.keys())

    def get_symbol_snapshot(self, symbol):
        with self._lock: return self._state.get(symbol, {}).copy()

    # --- [ویژگی جدید] --- توابع مدیریت حالت سکوت
    def toggle_silent_mode(self):
        """وضعیت حالت سکوت را تغییر می‌دهد (روشن به خاموش و بالعکس)."""
        with self._lock:
            self._global_state['silent_mode'] = not self._global_state['silent_mode']
            return self._global_state['silent_mode']

    def is_silent_mode_active(self):
        """وضعیت فعلی حالت سکوت را برمی‌گرداند."""
        with self._lock:
            return self._global_state['silent_mode']