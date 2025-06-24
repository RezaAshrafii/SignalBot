# setups/base_setup.py

class BaseSetup:
    def __init__(self, state_manager, config=None):
        self.name = "BaseSetup"
        self.config = config or {}
        self.state_manager = state_manager

    def check(self, **kwargs):
        raise NotImplementedError("متد check باید در کلاس فرزند پیاده‌سازی شود.")