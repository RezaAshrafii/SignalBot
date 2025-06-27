# setup_manager.py

import traceback

# ۱. ایمپورت کردن تمام کلاس‌های ستاپ فعال از پوشه setups
from setups.key_level_trend_setup import KeyLevelTrendSetup
from setups.ichimoku_setup import IchimokuSetup
from setups.liq_sweep_setup import LiqSweepSetup
from setups.pinbar_setup import PinbarSetup # <<< ایمپورت کردن ستاپ جدید پین‌بار
from setups.smart_money_setup import SmartMoneySetup



class SetupManager:
    """
    این کلاس تمام ستاپ‌های معاملاتی تعریف‌شده را مدیریت و اجرا می‌کند.
    این کلاس به عنوان یک نقطه ورودی واحد برای بررسی تمام استراتژی‌ها عمل می‌کند.
    """

    def __init__(self, state_manager):
        """
        در هنگام ساخته شدن، یک نمونه از هر کلاس ستاپ فعال را ایجاد کرده
        و در یک لیست برای بررسی‌های بعدی نگهداری می‌کند.
        """
        self.state_manager = state_manager
        
        # لیستی از تمام ستاپ‌های فعال ربات شما
        # برای غیرفعال کردن یک ستاپ، کافیست آن را از این لیست کامنت کنید.
        self.setups = [
            SmartMoneySetup(self.state_manager),
            
            # PinbarSetup(self.state_manager),
            # LiqSweepSetup(self.state_manager),
            # KeyLevelTrendSetup(self.state_manager),
            # IchimokuSetup(self.state_manager), # اگر این فایل را دارید، آن را هم کامنت کنید
        ]
        
        # چاپ نام ستاپ‌های فعال برای اطلاع در هنگام شروع ربات
        active_setup_names = [s.name for s in self.setups]
        print(f"SetupManager initialized successfully with setups: {active_setup_names}")

    def check_all_setups(self, **kwargs):
        """
        تمام ستاپ‌های موجود در لیست self.setups را به ترتیب اجرا می‌کند.
        """
        for setup in self.setups:
            try:
                signal = setup.check(**kwargs)
                if signal:
                    return self._format_signal(signal, setup.name)
            
            except Exception as e:
                symbol = kwargs.get('symbol', 'N/A')
                print(f"---! ERROR in setup '{setup.name}' for symbol '{symbol}' !---")
                print(f"Error details: {e}")
                traceback.print_exc()
        
        return None

    def _format_signal(self, signal: dict, setup_name: str) -> dict:
        """
        یک متد کمکی برای اطمینان از اینکه هر سیگنال خروجی، حاوی نام ستاپی
        که آن را تولید کرده است، باشد.
        """
        if 'setup' not in signal or not signal.get('setup'):
            signal['setup'] = setup_name
        
        # اطمینان از اینکه همه کلیدهای اصلی در سیگنال وجود دارند
        required_keys = ['direction', 'entry_price', 'stop_loss']
        if not all(key in signal for key in required_keys):
             print(f"[WARNING] Signal from {setup_name} is missing required keys!")
             return None # سیگنال ناقص را رد کن

        return signal