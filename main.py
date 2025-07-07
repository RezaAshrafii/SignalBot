import os, time, threading, pytz
from datetime import datetime, timedelta, timezone
import pandas as pd
from dotenv import load_dotenv
from flask import Flask

from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from position_manager import PositionManager 
from trend_analyzer import generate_master_trend_report
from setup_manager import SetupManager
from interactive_bot import InteractiveBot



active_monitors = {}



def shutdown_all_monitors():
    print("Shutting down all active symbol monitors...")
    for monitor in active_monitors.values():
        if hasattr(monitor, 'stop'):
            monitor.stop()
    active_monitors.clear()

def perform_daily_reinitialization(symbols, state_manager, position_manager, setup_manager):
    shutdown_all_monitors()
    ny_timezone = pytz.timezone("America/New_York")
    analysis_end_time_ny = datetime.now(ny_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"\n===== STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} =====")
    
    start_of_ny_day_utc = analysis_end_time_ny.astimezone(timezone.utc)
    
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        try:
            analysis_start_time_utc = datetime.now(timezone.utc) - timedelta(days=10)
            df_full_history = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, datetime.now(timezone.utc))
            
            if df_full_history.empty:
                print(f"Could not fetch data for {symbol}. Skipping.")
                continue
            
            # --- [تغییر] اطمینان از اینکه ستون open_time همیشه از نوع datetime است ---
            if not pd.api.types.is_datetime64_any_dtype(df_full_history['open_time']):
                 df_full_history['open_time'] = pd.to_datetime(df_full_history['open_time'], unit='ms', utc=True)

            df_historical = df_full_history[df_full_history['open_time'] < start_of_ny_day_utc].copy()
            df_intraday = df_full_history[df_full_history['open_time'] >= start_of_ny_day_utc].copy()
            
            if df_historical.empty or df_intraday.empty:
                print(f"❌ Not enough data to split for {symbol}. Historical: {len(df_historical)}, Intraday: {len(df_intraday)}")
                continue

            # --- این بخش از قبل صحیح بود و بدون تغییر باقی می‌ماند ---
            htf_trend, trend_report = generate_master_trend_report(symbol, state_manager, df_historical, df_intraday)
            state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
            state_manager.update_symbol_state(symbol, 'trend_report', trend_report)
            state_manager.update_symbol_state(symbol, 'klines_1m', df_intraday) # ذخیره کندل‌های روز برای چارت
            print(f"  -> {symbol} Composite HTF Trend: {htf_trend}")

            # --- [تغییر] ستون open_time از قبل به datetime تبدیل شده است ---
            df_full_history['ny_date'] = df_full_history['open_time'].dt.tz_convert('America/New_York').dt.date
            untouched_levels = find_untouched_levels(df_full_history, date_col='ny_date')
            state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
            print(f"  -> Found {len(untouched_levels)} untouched levels.")
            
            master_monitor = MasterMonitor(
                symbol=symbol,
                key_levels=untouched_levels,
                daily_trend=htf_trend,
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
    
    state_manager = StateManager(APP_CONFIG['symbols'])
    setup_manager = SetupManager(state_manager=state_manager)
    
    # --- [تغییر] ساختاردهی مجدد و تمیزتر برای حل مشکل وابستگی چرخه‌ای ---
    position_manager = PositionManager(
        state_manager=state_manager,
        bot_token=APP_CONFIG['bot_token'],
        chat_ids=APP_CONFIG['chat_ids'],
        risk_config=APP_CONFIG['risk_config'],
        active_monitors=active_monitors
    )
    position_manager.run_updater()
    
    # --- [تغییر] یک بار ساختن آبجکت ربات با تمام نیازمندی‌ها ---
    interactive_bot = InteractiveBot(
        token=APP_CONFIG['bot_token'],
        state_manager=state_manager,
        position_manager=position_manager,
        setup_manager=setup_manager,
        # --- [تغییر] ارسال تابع اصلی تحلیل به ربات برای اجرای دستور /reinit ---
        reinit_func=lambda: perform_daily_reinitialization(APP_CONFIG['symbols'], state_manager, position_manager, setup_manager)
    )

    # --- [تغییر] اجرای ربات تلگرام در یک ترد جداگانه ---
    threading.Thread(target=interactive_bot.run, daemon=True, name="InteractiveBotThread").start()
    
    # --- [تغییر] حلقه اصلی برنامه برای مدیریت تحلیل روزانه ---
    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    first_run = True
    
    while True:
        try:
            now_ny = datetime.now(ny_timezone)
            if last_check_date_ny != now_ny.date():
                if not first_run:
                    print(f"\n☀️ New day detected ({now_ny.date()}). Re-initializing...")
                
                last_check_date_ny = now_ny.date()
                perform_daily_reinitialization(APP_CONFIG['symbols'], state_manager, position_manager, setup_manager)
                notify_startup(APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['symbols'])
                print(f"\n✅ All systems re-initialized for NY trading day: {last_check_date_ny}.")
                first_run = False
                
            time.sleep(60)
        except KeyboardInterrupt:
            print('\nBot logic loop stopped by user.'); shutdown_all_monitors(); break
        except Exception as e:
            print(f"An error occurred in main loop: {e}"); import traceback; traceback.print_exc(); time.sleep(60)


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