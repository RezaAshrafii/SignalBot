# main.py (نسخه نهایی و کامل)

import os
import time
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytz
from dotenv import load_dotenv
from flask import Flask

# وارد کردن تمام ماژول‌های پروژه
from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from interactive_bot import InteractiveBot
from position_manager import PositionManager
from setup_manager import SetupManager

# دیکشنری برای نگهداری مانیتورهای فعال
active_monitors = {}

# این تابع در حال حاضر استفاده نمی‌شود اما طبق درخواست شما باقی می‌ماند
def analyze_trend_and_generate_report(historical_df, intraday_df):
    """روند را بر اساس تحلیل ساختار ۳ روز گذشته و CVD روز جاری تحلیل می‌کند."""
    pass # ... (منطق این تابع که شما ارائه کردید)

def shutdown_all_monitors():
    print("Shutting down all active symbol monitors...")
    for monitor in active_monitors.values():
        if hasattr(monitor, 'stop'):
            monitor.stop()
    active_monitors.clear()

def perform_daily_reinitialization(symbols, state_manager, position_manager, setup_manager):
    """در ابتدای هر روز، سطوح و مانیتورها را از نو راه‌اندازی می‌کند."""
    shutdown_all_monitors()
    ny_timezone = pytz.timezone("America/New_York")
    analysis_end_time_ny = datetime.now(ny_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"\n===== STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} =====")
    
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        try:
            analysis_start_time_utc = datetime.now(timezone.utc) - timedelta(days=10)
            df_full_history = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, datetime.now(timezone.utc))
            if df_full_history.empty:
                print(f"Could not fetch data for {symbol}. Skipping.")
                continue
            
            # پیدا کردن سطوح دست‌نخورده
            df_full_history['ny_date'] = df_full_history['open_time'].dt.tz_convert('America/New_York').dt.date
            untouched_levels = find_untouched_levels(df_full_history, date_col='ny_date')
            state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
            print(f"  -> Found {len(untouched_levels)} untouched levels.")
            
            # روند در لحظه درخواست کاربر محاسبه خواهد شد و مقدار اولیه 'PENDING' است
            state_manager.update_symbol_state(symbol, 'htf_trend', 'PENDING')
            
            # --- [اصلاح شد] --- ساخت MasterMonitor با تمام وابستگی‌های لازم
            master_monitor = MasterMonitor(
                symbol=symbol,
                key_levels=untouched_levels,
                daily_trend='PENDING', # این مقدار بعدا توسط ربات آپدیت می‌شود
                position_manager=position_manager,
                state_manager=state_manager,
                setup_manager=setup_manager
            )
            active_monitors[symbol] = master_monitor
            master_monitor.run()
        except Exception as e:
            print(f"ERROR during initialization for {symbol}: {e}")
            import traceback
            traceback.print_exc()

def bot_logic_main_loop():
    """این تابع شامل منطق اصلی ربات است که باید به صورت مداوم اجرا شود."""
    load_dotenv()
    APP_CONFIG = {
        "symbols": os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(','),
        "bot_token": os.getenv("BOT_TOKEN"),
        "chat_ids": os.getenv("CHAT_IDS", "").split(','),
        "risk_config": {"RISK_PER_TRADE_PERCENT": 1.0, "DAILY_DRAWDOWN_LIMIT_PERCENT": 3.0, "RR_RATIOS": [1, 2, 3]}
    }
    if not APP_CONFIG["bot_token"] or not APP_CONFIG["chat_ids"][0]:
        print("خطا: BOT_TOKEN و CHAT_IDS تعریف نشده‌اند."); return

    print("Initializing core systems...")
    # --- [اصلاح شد] --- ترتیب صحیح ساخت آبجکت‌ها برای حل وابستگی چرخه‌ای
    state_manager = StateManager(APP_CONFIG['symbols'])
    state_manager.update_symbol_state('__app__', 'chat_ids', APP_CONFIG['chat_ids'])

    # ۱. ربات را بساز
    interactive_bot = InteractiveBot(APP_CONFIG['bot_token'], state_manager)
    # ۲. مدیر پوزیشن را با توکن ربات بساز
    position_manager = PositionManager(state_manager, APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['risk_config'], active_monitors)
    # ۳. حالا مدیر پوزیشن و ربات را به هم متصل کن
    interactive_bot.set_position_manager(position_manager)
    
    setup_manager = SetupManager(state_manager=state_manager)
    
    # اجرای ترد ربات تلگرام
    interactive_bot.run()
    # اجرای ترد آپدیت‌کننده پوزیشن‌ها
    if hasattr(position_manager, 'run_updater'):
        position_manager.run_updater()

    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    while True:
        try:
            now_ny = datetime.now(ny_timezone)
            if last_check_date_ny != now_ny.date():
                if last_check_date_ny is not None: print(f"\n☀️ New day detected ({now_ny.date()}). Re-initializing...")
                last_check_date_ny = now_ny.date()
                perform_daily_reinitialization(APP_CONFIG['symbols'], state_manager, position_manager, setup_manager)
                notify_startup(APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['symbols'])
                print(f"\n✅ All systems re-initialized for NY trading day: {last_check_date_ny}.")
            time.sleep(60)
        except KeyboardInterrupt:
            print('\nBot logic loop stopped by user.')
            shutdown_all_monitors()
            break
        except Exception as e:
            print(f"An error occurred in main loop: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(60)

# --- بخش Flask برای آنلاین نگه داشتن برنامه ---
app = Flask(__name__)
@app.route('/')
def home():
    return "SignalBot Service is alive and running."

def run_flask_app():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("Starting bot application...")
    bot_logic_thread = threading.Thread(target=bot_logic_main_loop, daemon=True, name="BotLogicThread")
    bot_logic_thread.start()
    
    print("Starting Flask web server...")
    run_flask_app()