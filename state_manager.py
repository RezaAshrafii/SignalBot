# state_manager.py
import threading

class StateManager:
    def __init__(self, symbols):
        self._state = {symbol: {} for symbol in symbols}
        self._lock = threading.Lock()

    def update_symbol_state(self, symbol, key, value):
        with self._lock:
            if symbol in self._state:
                self._state[symbol][key] = value

    def get_symbol_state(self, symbol, key):
        with self._lock:
            return self._state.get(symbol, {}).get(key)

    def get_full_state(self):
        with self._lock:
            return self._state.copy()
            
    # --- [توابع جدید برای هماهنگی] ---
    def get_all_symbols(self):
        with self._lock:
            return list(self._state.keys())

    def get_symbol_snapshot(self, symbol):
        with self._lock:
            return self._state.get(symbol, {}).copy()