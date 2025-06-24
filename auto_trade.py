# auto_trade.py

import pandas as pd
from state_manager import StateManager
from position_manager import PositionManager
from performance_reporter import generate_performance_report
from alert import BOT_TOKEN, CHAT_IDS, send_bulk_telegram_alert
from setups.liq_sweep_setup import LiqSweepSetup
from setups.ichimoku_setup import IchimokuSetup
# --- [حذف شد] --- استراتژی پین‌بار به طور کامل حذف شد
# from setups.pinbar_setup import PinbarSetup

class AutoTrader:
    def __init__(self, symbol: str):
        self.symbol = symbol
        print("در حال مقداردهی اولیه مدیران...")
        self.state_manager = StateManager(symbol)
        
        risk_config = {
            "RISK_PER_TRADE": 1.0,
            "DAILY_DRAWDOWN_LIMIT_PERCENT": 5.0
        }
        active_monitors = {}

        self.position_manager = PositionManager(
            state_manager=self.state_manager,
            bot_token=BOT_TOKEN,
            chat_ids=CHAT_IDS,
            risk_config=risk_config,
            active_monitors=active_monitors
        )
        
        print("در حال شناسایی و ساخت استراتژی‌های مورد نیاز...")
        # --- [حذف شد] --- مقداردهی اولیه پین‌بار حذف شد
        self.liq_sweep_setup = LiqSweepSetup(self.state_manager, risk_config)
        self.ichimoku_setup = IchimokuSetup(self.state_manager, risk_config)
        print("کلاس AutoTrader با موفقیت آماده به کار شد.")

    def process_new_candle(self, new_candle: dict):
        self.state_manager.add_candle(new_candle)
        self.position_manager._check_and_update_live_positions()
        
        if self.symbol in self.position_manager.active_positions:
            return

        # --- [اصلاح شد] --- منطق به بررسی سیگنال‌های انفرادی تغییر کرد
        liq_package = self.liq_sweep_setup.check_setup(self.symbol)
        ichi_package = self.ichimoku_setup.check_setup(self.symbol)
        
        current_price = self.state_manager.get_current_price()
        if not current_price: return

        # ابتدا سیگنال Liq Sweep را بررسی می‌کنیم
        if liq_package:
            direction = liq_package.get('type')
            sl = liq_package.get('stop_loss')
            tp = liq_package.get('take_profit')
            setup_name = "LiqSweep" # نام استراتژی به تنهایی استفاده می‌شود
            
            if direction and sl and tp:
                print(f"سیگنال یافت شد: {setup_name} ({direction})")
                self.position_manager.open_position_auto(
                    symbol=self.symbol, direction=direction, entry_price=current_price,
                    sl=sl, tp=tp, setup_name=setup_name
                )
                return # بعد از یافتن سیگنال، از تابع خارج می‌شویم

        # اگر سیگنال Liq نبود، Ichimoku را بررسی می‌کنیم
        if ichi_package:
            direction = ichi_package.get('type')
            sl = ichi_package.get('stop_loss')
            tp = ichi_package.get('take_profit')
            setup_name = "Ichimoku"

            if direction and sl and tp:
                print(f"سیگنال یافت شد: {setup_name} ({direction})")
                self.position_manager.open_position_auto(
                    symbol=self.symbol, direction=direction, entry_price=current_price,
                    sl=sl, tp=tp, setup_name=setup_name
                )
                return

# --- بخش اصلی اجرای بک‌تست (بدون تغییر) ---
if __name__ == '__main__':
    SYMBOL_TO_TEST = 'BTCUSDT'
    DATA_FILE_PATH = f'data/{SYMBOL_TO_TEST}_1m.csv'
    INITIAL_CAPITAL = 10000.0

    my_bot = AutoTrader(symbol=SYMBOL_TO_TEST)

    try:
        df = pd.read_csv(DATA_FILE_PATH, index_col=0, parse_dates=True)
    except FileNotFoundError:
        print(f"خطا: فایل داده در مسیر '{DATA_FILE_PATH}' یافت نشد.")
        exit()
    except Exception as e:
        print(f"خطا در خواندن فایل CSV: {e}")
        exit()

    print(f"\nشروع بک‌تست روی فایل {DATA_FILE_PATH}...")
    for index, row in df.iterrows():
        new_candle_data = {'open': row['open'], 'high': row['high'], 'low': row['low'], 'close': row['close'], 'volume': row['volume'], 'timestamp': index}
        my_bot.process_new_candle(new_candle_data)
    
    my_bot.position_manager.close_all_positions()
    print("بک‌تست به پایان رسید.")

    print("\nدر حال تولید گزارش عملکرد...")
    closed_trades = my_bot.position_manager.closed_trades
    final_report = generate_performance_report(closed_trades, initial_capital=INITIAL_CAPITAL)
    
    print(final_report)
    print("در حال ارسال گزارش نهایی به تلگرام...")
    send_bulk_telegram_alert(final_report, my_bot.position_manager.bot_token, my_bot.position_manager.chat_ids)
    print("گزارش با موفقیت به تلگرام ارسال شد.")
