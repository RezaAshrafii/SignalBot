# state_manager.py (نسخه ایمن در برابر تردها)

from collections import defaultdict
import threading

class StateManager:
    def __init__(self, symbols):
        # یک قفل برای هر نماد، جهت جلوگیری از تداخل تردها
        self._locks = defaultdict(threading.Lock)
        # وضعیت کلی ربات که بین تمام ماژول‌ها مشترک است
        self._shared_state = defaultdict(dict)

    def update_symbol_state(self, symbol, key, value):
        """
        وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن آپدیت می‌کند.
        """
        with self._locks[symbol]:
            self._shared_state[symbol][key] = value

    def get_symbol_state(self, symbol, key, default=None):
        """
        وضعیت یک پارامتر خاص را برای یک نماد به صورت ایمن می‌خواند.
        """
        with self._locks[symbol]:
            return self._shared_state[symbol].get(key, default)

    def get_full_symbol_state(self, symbol):
        """
        تمام اطلاعات وضعیت یک نماد را به صورت ایمن برمی‌گرداند.
        """
        with self._locks[symbol]:
            # یک کپی از دیکشنری را برمی‌گردانیم تا از تغییرات ناخواسته جلوگیری شود
            return self._shared_state[symbol].copy()

    def update_level_alert_time(self, symbol, level_id):
        """
        زمان آخرین الرت برای یک سطح خاص را به صورت ایمن ثبت می‌کند.
        """
        import time
        key = f"level_alert_{level_id}"
        self.update_symbol_state(symbol, key, time.time())

    def get_level_alert_time(self, symbol, level_id):
        """
        زمان آخرین الرت برای یک سطح خاص را به صورت ایمن می‌خواند.
        """
        key = f"level_alert_{level_id}"
        return self.get_symbol_state(symbol, key, 0)