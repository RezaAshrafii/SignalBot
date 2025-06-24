# state_manager.py (نسخه نهایی، کامل و ایمن)

from collections import defaultdict
import threading

class StateManager:
    def __init__(self, symbols):
        self._locks = defaultdict(threading.Lock)
        # وضعیت کلی ربات که بین تمام ماژول‌ها مشترک است
        self._shared_state = {symbol: {} for symbol in symbols}
        # یک کلید سراسری برای تنظیمات کلی برنامه
        self._shared_state['__app__'] = {}

    def update_symbol_state(self, symbol, key, value):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن آپدیت می‌کند."""
        with self._locks[symbol]:
            if symbol not in self._shared_state: self._shared_state[symbol] = {}
            self._shared_state[symbol][key] = value

    def get_symbol_state(self, symbol, key, default=None):
        """وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن می‌خواند."""
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).get(key, default)

    def get_full_symbol_state(self, symbol):
        """تمام اطلاعات وضعیت یک نماد را به صورت ایمن برمی‌گرداند."""
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).copy()

    def get_all_symbols(self):
        """لیستی از تمام نمادهای فعال را برمی‌گرداند."""
        with self._locks['__global__']:
            # کلیدهای __app__ را از لیست نمادها حذف می‌کنیم
            return [s for s in self._shared_state.keys() if s != '__app__']

    def add_pending_proposal(self, symbol, proposal_id, proposal_data):
        """یک سیگنال پیشنهادی جدید را برای تایید کاربر اضافه می‌کند."""
        key = "pending_proposals"
        with self._locks[symbol]:
            if key not in self._shared_state.get(symbol, {}):
                self._shared_state[symbol][key] = {}
            self._shared_state[symbol][key][proposal_id] = proposal_data

    def get_pending_proposal(self, symbol, proposal_id):
        """یک پیشنهاد در انتظار را با ID آن بازیابی می‌کند."""
        key = "pending_proposals"
        with self._locks[symbol]:
            return self._shared_state.get(symbol, {}).get(key, {}).get(proposal_id)

    def remove_pending_proposal(self, symbol, proposal_id):
        """یک پیشنهاد را پس از تایید یا رد، حذف می‌کند."""
        key = "pending_proposals"
        with self._locks[symbol]:
            if key in self._shared_state.get(symbol, {}) and proposal_id in self._shared_state[symbol][key]:
                del self._shared_state[symbol][key][proposal_id]

    def update_level_alert_time(self, symbol, level_id):
        import time
        key = f"level_alert_{level_id}"
        self.update_symbol_state(symbol, key, time.time())

    def get_level_alert_time(self, symbol, level_id):
        key = f"level_alert_{level_id}"
        return self.get_symbol_state(symbol, key, 0)