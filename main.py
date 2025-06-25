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
    report_lines = ["**تحلیل روند:**\n"]
    if historical_df.empty or len(historical_df.groupby(pd.Grouper(key='open_time', freq='D'))) < 3:
        return "INSUFFICIENT_DATA", "داده تاریخی کافی (حداقل ۳ روز) وجود ندارد."
    
    daily_data = historical_df.groupby(pd.Grouper(key='open_time', freq='D')).agg(
        open=('open', 'first'), high=('high', 'max'),
        low=('low', 'min'), close=('close', 'last'),
        taker_buy_volume=('taker_buy_base_asset_volume', 'sum'),
        total_volume=('volume', 'sum')
    ).dropna()

    last_3_days = daily_data.tail(3)
    if len(last_3_days) < 3: return "INSUFFICIENT_DATA", "داده کافی برای مقایسه سه روز اخیر وجود ندارد."

    day_1, day_2, day_3 = last_3_days.iloc[0], last_3_days.iloc[1], last_3_days.iloc[2]
    
    pa_score = 0
    # --- [اصلاح شد] --- منطق امتیازدهی پرایس اکشن برای تحلیل دقیق ساختار
    def get_pa_score(current, prev):
        score = 0
        if current['high'] > prev['high']: score += 1
        if current['low'] > prev['low']: score += 1
        if current['high'] < prev['high']: score -= 1
        if current['low'] < prev['low']: score -= 1
        return score

    pa_score_link1 = get_pa_score(day_2, day_1)
    pa_score_link2 = get_pa_score(day_3, day_2)
    pa_score = pa_score_link1 + pa_score_link2
    report_lines.append(f"- **پرایس اکشن (ساختار ۳ روز گذشته)**: امتیاز: `{pa_score}`")

    cvd_score = 0
    if not intraday_df.empty:
        delta = 2 * intraday_df['taker_buy_base_asset_volume'].sum() - intraday_df['volume'].sum()
        if delta > 0: cvd_score = 1
        elif delta < 0: cvd_score = -1
        delta_narrative = f"دلتا تجمعی **امروز** {'مثبت' if cvd_score > 0 else 'منفی' if cvd_score < 0 else 'خنثی'} است (`{delta:,.0f}`)."
    else: delta_narrative = "داده‌ای برای تحلیل CVD امروز موجود نیست."
    report_lines.append(f"- **جریان سفارشات (CVD امروز)**: {delta_narrative} (امتیاز: `{cvd_score}`)")
    
    total_score = pa_score + cvd_score
    final_trend = "SIDEWAYS"
    if total_score >= 3: final_trend = "BULLISH"
    elif total_score > 0: final_trend = "BULLISH"
    elif total_score <= -3: final_trend = "BEARISH"
    elif total_score < 0: final_trend = "BEARISH"
    
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score}`، روند امروز **{final_trend}** ارزیابی می‌شود.")
    return final_trend, "\n".join(report_lines)

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
    
    # --- [اصلاح شد] --- ترتیب صحیح و هماهنگ ساخت آبجکت‌ها
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