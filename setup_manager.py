# setup_manager.py

import traceback

# ۱. ایمپورت کردن تمام کلاس‌های ستاپ فعال از پوشه setups
from setups.key_level_trend_setup import KeyLevelTrendSetup
from setups.ichimoku_setup import IchimokuSetup
from setups.liq_sweep_setup import LiqSweepSetup
from setups.pinbar_setup import PinbarSetup # <<< ایمپورت کردن ستاپ جدید پین‌بار

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
            # اولویت با ستاپ‌های سریع‌تر و کوتاه‌مدت‌تر است
            PinbarSetup(self.state_manager),
            LiqSweepSetup(self.state_manager),
            
            # سپس ستاپ‌های دیگر
            KeyLevelTrendSetup(self.state_manager),
            IchimokuSetup(self.state_manager),
        ]
        
        # چاپ نام ستاپ‌های فعال برای اطلاع در هنگام شروع ربات
        active_setup_names = [s.name for s in self.setups]
        print(f"SetupManager initialized successfully with setups: {active_setup_names}")

    def check_all_setups(self, **kwargs):
        """
        تمام ستاپ‌های موجود در لیست self.setups را به ترتیب اجرا می‌کند.
        
        از kwargs (keyword arguments) استفاده می‌کند تا هر ستاپ بتواند داده‌های
        مورد نیاز خود (مثل kline_history, levels, daily_trend و غیره) را از
        پکیج ورودی بردارد بدون اینکه به بقیه ستاپ‌ها آسیب بزند.

        Returns:
            یک دیکشنری سیگنال در صورت یافتن موقعیت، در غیر این صورت None.
        """
        # به ترتیب لیست، هر ستاپ را بررسی کن
        for setup in self.setups:
            try:
                # متد check مربوط به هر ستاپ را با تمام داده‌های موجود فراخوانی کن
                signal = setup.check(**kwargs)
                
                # اگر ستاپ یک سیگنال معتبر برگرداند (یعنی None نباشد)
                if signal:
                    # سیگنال را برای اطمینان از فرمت صحیح، به متد کمکی بفرست
                    # و آن را به عنوان خروجی برگردان. حلقه متوقف می‌شود.
                    return self._format_signal(signal, setup.name)
            
            except Exception as e:
                # در صورت بروز خطا در هر یک از ستاپ‌ها، آن را چاپ کن تا بتوان دیباگ کرد
                # این کار از کرش کردن کل ربات به خاطر خطای یک ستاپ جلوگیری می‌کند.
                symbol = kwargs.get('symbol', 'N/A')
                print(f"---! ERROR in setup '{setup.name}' for symbol '{symbol}' !---")
                print(f"Error details: {e}")
                traceback.print_exc() # چاپ کامل خطا برای تحلیل دقیق‌تر
        
        # اگر حلقه تمام شد و هیچ ستاپی سیگنال معتبری برنگرداند، None را برگردان
        return None

    def _format_signal(self, signal: dict, setup_name: str) -> dict:
        """
        یک متد کمکی برای اطمینان از اینکه هر سیگنال خروجی، حاوی نام ستاپی
        که آن را تولید کرده است، باشد. این کار برای تحلیل و گزارش‌گیری مفید است.
        """
        # اگر کلید 'setup' در دیکشنری سیگنال وجود نداشت یا خالی بود،
        # نام کلاس ستاپ را به عنوان مقدار پیش‌فرض در آن قرار بده.
        if 'setup' not in signal or not signal.get('setup'):
            signal['setup'] = setup_name
        
        return signal