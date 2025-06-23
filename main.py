# main.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import asyncio
import pytz
import os
from dotenv import load_dotenv
import threading
from flask import Flask

# وارد کردن تمام ماژول‌های پروژه
from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from interactive_bot import InteractiveBot
from position_manager import PositionManager

active_monitors = {}

# تمام توابع شما (analyze_trend, shutdown_all_monitors, ...) در اینجا قرار می‌گیرند
# و هیچکدام حذف نشده‌اند.
def analyze_trend_and_generate_report(historical_df, intraday_df):
    report_lines = ["**تحلیل روند:**\n"]
    if historical_df.empty or len(historical_df.groupby(pd.Grouper(key='open_time', freq='D'))) < 2:
        return "INSUFFICIENT_DATA", "داده تاریخی کافی برای تحلیل پرایس اکشن (حداقل ۲ روز) وجود ندارد."
    daily_data = historical_df.groupby(pd.Grouper(key='open_time', freq='D')).agg(high=('high', 'max'), low=('low', 'min')).dropna()
    last_2_days = daily_data.tail(2)
    if len(last_2_days) < 2: return "INSUFFICIENT_DATA", "داده کافی برای مقایسه دو روز اخیر وجود ندارد."
    yesterday, day_before = last_2_days.iloc[-1], last_2_days.iloc[-2]
    pa_narrative, trend_score = "دیروز قیمت در محدوده داخلی پریروز نوسان کرد (Inside Day).", 0
    if yesterday['high'] > day_before['high'] and yesterday['low'] > day_before['low']:
        pa_narrative, trend_score = "دیروز سقف و کف بالاتر (HH & HL) نسبت به پریروز ثبت شد.", 2
    elif yesterday['high'] < day_before['high'] and yesterday['low'] < day_before['low']:
        pa_narrative, trend_score = "دیروز سقف و کف پایین‌تر (LH & LL) نسبت به پریروز ثبت شد.", -2
    report_lines.append(f"- **پرایس اکشن (گذشته)**: {pa_narrative}")
    price_trend = "UP" if trend_score > 0 else "DOWN" if trend_score < 0 else "SIDEWAYS"
    if intraday_df.empty: cvd_trend, delta_narrative = "SIDEWAYS", "هنوز داده کافی برای تحلیل CVD امروز وجود ندارد."
    else:
        intraday_taker_buy = intraday_df['taker_buy_base_asset_volume'].sum()
        intraday_total_volume = intraday_df['volume'].sum()
        current_delta = 2 * intraday_taker_buy - intraday_total_volume
        cvd_trend = "UP" if current_delta > 0 else "DOWN" if current_delta < 0 else "SIDEWAYS"
        delta_narrative = f"دلتا تجمعی **امروز** {'مثبت' if cvd_trend == 'UP' else 'منفی'} است ({current_delta:,.0f})."
    report_lines.append(f"- **جریان سفارشات (CVD امروز)**: {delta_narrative}")
    final_trend = "SIDEWAYS"
    if price_trend == "UP" and cvd_trend == "UP": final_trend = "STRONG_UP"
    elif price_trend == "DOWN" and cvd_trend == "DOWN": final_trend = "STRONG_DOWN"
    elif price_trend == "UP": final_trend = "UP_WEAK"
    elif price_trend == "DOWN": final_trend = "DOWN_WEAK"
    elif price_trend == "SIDEWAYS":
        if cvd_trend == "UP": final_trend = "UP_WEAK"
        elif cvd_trend == "DOWN": final_trend = "DOWN_WEAK"
    report_lines.append(f"\n**نتیجه‌گیری**: روند کلی **{final_trend}** ارزیابی می‌شود.")
    return final_trend, "\n".join(report_lines)

def shutdown_all_monitors():
    print("Shutting down all active symbol monitors...")
    for monitor in active_monitors.values():
        if hasattr(monitor, 'stop'): monitor.stop()
    active_monitors.clear()

def perform_daily_reinitialization(symbols, state_manager, position_manager):
    shutdown_all_monitors()
    ny_timezone = pytz.timezone("America/New_York")
    analysis_end_time_ny = datetime.now(ny_timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    print(f"\n===== STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} =====")
    analysis_end_time_utc = analysis_end_time_ny.astimezone(timezone.utc)
    analysis_start_time_utc = analysis_end_time_utc - timedelta(days=10)
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        df_full_history = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, datetime.now(timezone.utc))
        if df_full_history.empty: print(f"Could not fetch data for {symbol}. Skipping."); continue
        df_historical = df_full_history[df_full_history['open_time'] < analysis_end_time_utc].copy()
        df_intraday = df_full_history[df_full_history['open_time'] >= analysis_end_time_utc].copy()
        htf_trend, trend_report = analyze_trend_and_generate_report(df_historical, df_intraday)
        state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
        state_manager.update_symbol_state(symbol, 'trend_report', trend_report)
        print(f"  -> {symbol} Composite HTF Trend: {htf_trend}")
        df_full_history['ny_date'] = df_full_history['open_time'].dt.tz_convert('America/New_York').dt.date
        untouched_levels = find_untouched_levels(df_full_history, date_col='ny_date')
        state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
        print(f"  -> Found {len(untouched_levels)} untouched levels.")
        master_monitor = MasterMonitor(key_levels=untouched_levels, symbol=symbol, daily_trend=htf_trend, position_manager=position_manager, state_manager=state_manager)
        active_monitors[symbol] = master_monitor
        master_monitor.run()

def bot_logic_main_loop():
    """این تابع شامل منطق اصلی ربات است که باید به صورت مداوم اجرا شود."""
    load_dotenv()
    APP_CONFIG = {
        "symbols": ['BTCUSDT', 'ETHUSDT'],
        "bot_token": os.getenv("BOT_TOKEN"),
        "chat_ids": os.getenv("CHAT_IDS", "").split(','),
        "risk_config": {"RISK_PER_TRADE_PERCENT": 1.0, "DAILY_DRAWDOWN_LIMIT_PERCENT": 3.0, "RR_RATIOS": [1, 2, 3]}
    }
    if not APP_CONFIG["bot_token"] or not APP_CONFIG["chat_ids"][0]:
        print("خطا: BOT_TOKEN و CHAT_IDS تعریف نشده‌اند."); return

    print("Initializing core systems...")
    state_manager = StateManager(APP_CONFIG['symbols'])
    position_manager = PositionManager(state_manager, APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['risk_config'], active_monitors)
    interactive_bot = InteractiveBot(APP_CONFIG['bot_token'], state_manager, position_manager)
    position_manager.run_updater()
    interactive_bot.run() # این متد ترد خودش را برای ربات تلگرام اجرا می‌کند

    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    while True:
        now_ny = datetime.now(ny_timezone)
        if last_check_date_ny != now_ny.date():
            if last_check_date_ny is not None: print(f"\n☀️ New day detected ({now_ny.date()}). Re-initializing...")
            last_check_date_ny = now_ny.date()
            perform_daily_reinitialization(APP_CONFIG['symbols'], state_manager, position_manager)
            notify_startup(APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['symbols'])
            print(f"\n✅ All systems re-initialized for NY trading day: {last_check_date_ny}.")
        time.sleep(60)

# --- وب سرور ساختگی Flask ---
app = Flask(__name__)
@app.route('/')
def home():
    return "SignalBot Service is alive and running."

def run_flask_app():
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # ۱. منطق اصلی ربات را در یک ترد پس‌زمینه اجرا می‌کنیم
    print("Starting main bot logic in a background thread...")
    bot_logic_thread = threading.Thread(target=bot_logic_main_loop, daemon=True)
    bot_logic_thread.start()
    
    # ۲. وب سرور Flask را در ترد اصلی اجرا می‌کنیم تا Railway را راضی نگه دارد
    print("Starting Flask dummy server in the main thread...")
    run_flask_app()