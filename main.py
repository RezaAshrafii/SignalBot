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
    
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        try:
            analysis_start_time_utc = datetime.now(timezone.utc) - timedelta(days=10)
            df_full_history = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, datetime.now(timezone.utc))
            if df_full_history.empty:
                print(f"Could not fetch data for {symbol}. Skipping.")
                continue

            df_historical = df_full_history[df_full_history['open_time'] < analysis_end_time_ny.astimezone(timezone.utc)].copy()
            df_intraday = df_full_history[df_full_history['open_time'] >= analysis_end_time_ny.astimezone(timezone.utc)].copy()
            
            htf_trend, trend_report = generate_master_trend_report(symbol, state_manager, df_historical, df_intraday)
            state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
            state_manager.update_symbol_state(symbol, 'trend_report', trend_report)
            print(f"  -> {symbol} Composite HTF Trend: {htf_trend}")

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
    
    # ترتیب صحیح ساخت آبجکت‌ها برای حل وابستگی چرخه‌ای
    state_manager = StateManager(APP_CONFIG['symbols'])
    setup_manager = SetupManager(state_manager=state_manager)
    
    # ۱. ابتدا ربات تلگرام ساخته می‌شود (بدون مدیر پوزیشن)
    interactive_bot = InteractiveBot(APP_CONFIG['bot_token'], state_manager)
    
    # ۲. سپس مدیر پوزیشن با تمام وابستگی‌ها ساخته می‌شود
    position_manager = PositionManager(state_manager, APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['risk_config'], active_monitors)
    
    # ۳. حالا مدیر پوزیشن به ربات تلگرام متصل می‌شود
    interactive_bot.set_position_manager(position_manager)
    
    if hasattr(position_manager, 'set_application_and_loop') and hasattr(interactive_bot, 'get_event_loop'):
        position_manager.set_application_and_loop(interactive_bot.application, interactive_bot.get_event_loop())

    # ۳. حالا مدیر پوزیشن به ربات تلگرام متصل می‌شود
    interactive_bot.set_position_manager(position_manager)
    
    if hasattr(position_manager, 'set_application_and_loop') and hasattr(interactive_bot, 'get_event_loop'):
        position_manager.set_application_and_loop(interactive_bot.application, interactive_bot.get_event_loop())

    interactive_bot.run()
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