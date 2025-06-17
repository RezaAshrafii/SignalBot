# main.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import asyncio
import pytz
import os
from dotenv import load_dotenv

from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from interactive_bot import InteractiveBot
from position_manager import PositionManager

active_monitors = {}

def determine_composite_trend(df):
    """روند را با منطق نهایی امتیازدهی و دلتا مشخص می‌کند."""
    print("Analyzing daily data to determine composite trend...")
    if df.empty or len(df.groupby(pd.Grouper(key='open_time', freq='D'))) < 3: return "INSUFFICIENT_DATA"
    daily_data = df.groupby(pd.Grouper(key='open_time', freq='D')).agg(high=('high', 'max'), low=('low', 'min'), taker_buy_volume=('taker_buy_base_asset_volume', 'sum'), total_volume=('volume', 'sum')).dropna()
    last_3_days = daily_data.tail(3)
    if len(last_3_days) < 2: return "INSUFFICIENT_DATA"
    highs, lows = last_3_days['high'].tolist(), last_3_days['low'].tolist()
    trend_score = 0
    for i in range(1, len(highs)):
        if highs[i] > highs[i-1]: trend_score += 1
        if lows[i] > lows[i-1]: trend_score += 1
        if highs[i] < highs[i-1]: trend_score -= 1
        if lows[i] < lows[i-1]: trend_score -= 1
    price_trend = "SIDEWAYS"
    if trend_score > 0: price_trend = "UP"
    elif trend_score < 0: price_trend = "DOWN"
    daily_data['delta'] = 2 * daily_data['taker_buy_volume'] - daily_data['total_volume']
    last_day_delta = daily_data['delta'].iloc[-1]
    cvd_trend = "SIDEWAYS"
    if last_day_delta > 0: cvd_trend = "UP"
    elif last_day_delta < 0: cvd_trend = "DOWN"
    if price_trend == "UP" and cvd_trend == "UP": return "STRONG_UP"
    elif price_trend == "DOWN" and cvd_trend == "DOWN": return "STRONG_DOWN"
    elif price_trend == "UP": return "UP_WEAK"
    elif price_trend == "DOWN": return "DOWN_WEAK"
    else: return "SIDEWAYS"

def shutdown_all_monitors():
    """تمام مانیتورهای فعال را متوقف می‌کند."""
    print("Shutting down all active symbol monitors...")
    for monitor in active_monitors.values():
        if hasattr(monitor, 'stop'): monitor.stop()
    active_monitors.clear()

def perform_daily_reinitialization(symbols, state_manager, position_manager, analysis_end_time_ny):
    """چرخه کامل تحلیل و راه‌اندازی برای شروع هر روز معاملاتی جدید."""
    shutdown_all_monitors()
    print(f"\n===== 🗽 STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} 🗽 =====")
    analysis_end_time_utc = analysis_end_time_ny.astimezone(timezone.utc)
    analysis_start_time_utc = analysis_end_time_utc - timedelta(days=10)
    now_utc = datetime.now(timezone.utc)
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        df_for_analysis = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, now_utc)
        if df_for_analysis.empty: print(f"Could not fetch data for {symbol}. Skipping."); continue
        trend_df = df_for_analysis[df_for_analysis['open_time'] < analysis_end_time_utc].copy()
        htf_trend = determine_composite_trend(trend_df)
        state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
        print(f"  -> {symbol} Composite HTF Trend: {htf_trend}")
        df_for_analysis['ny_date'] = df_for_analysis['open_time'].dt.tz_convert('America/New_York').dt.date
        untouched_levels = find_untouched_levels(df_for_analysis, date_col='ny_date')
        state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
        print(f"  -> Found {len(untouched_levels)} untouched levels.")
        master_monitor = MasterMonitor(key_levels=untouched_levels, symbol=symbol, daily_trend=htf_trend, position_manager=position_manager, state_manager=state_manager)
        active_monitors[symbol] = master_monitor
        master_monitor.run()

async def daily_reset_task(app_config, state_manager, position_manager):
    """حلقه ناهمزمان برای مدیریت ریست روزانه برنامه."""
    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    while True:
        now_ny = datetime.now(ny_timezone)
        if last_check_date_ny != now_ny.date():
            if last_check_date_ny is not None: print(f"\n☀️ New day detected ({now_ny.date()}). Re-initializing...")
            last_check_date_ny = now_ny.date()
            ny_midnight_today = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
            perform_daily_reinitialization(app_config['symbols'], state_manager, position_manager, ny_midnight_today)
            notify_startup(app_config['bot_token'], app_config['chat_ids'], app_config['symbols'])
            print(f"\n✅ All systems re-initialized for NY trading day: {last_check_date_ny}.")
            print("Bot is running. Waiting for the next day...")
        await asyncio.sleep(60)

async def main():
    """تابع اصلی ناهمزمان که هر دو بخش ربات را اجرا می‌کند."""
    load_dotenv()
    APP_CONFIG = {
        "symbols": ['BTCUSDT', 'ETHUSDT'],
        "bot_token": os.getenv("BOT_TOKEN"),
        "chat_ids": os.getenv("CHAT_IDS", "").split(','),
        "risk_config": {"RISK_PER_TRADE_PERCENT": 1.0, "DAILY_DRAWDOWN_LIMIT_PERCENT": 3.0, "RR_RATIOS": [1, 2, 3]}
    }
    if not APP_CONFIG["bot_token"] or not APP_CONFIG["chat_ids"][0]: print("خطا: BOT_TOKEN و CHAT_IDS تعریف نشده‌اند."); return

    print("Initializing core systems...")
    state_manager = StateManager(APP_CONFIG['symbols'])
    # --- [اصلاح شد] --- فراخوانی صحیح PositionManager با تمام پارامترها
    position_manager = PositionManager(state_manager, APP_CONFIG['bot_token'], APP_CONFIG['chat_ids'], APP_CONFIG['risk_config'], active_monitors)
    interactive_bot = InteractiveBot(APP_CONFIG['bot_token'], state_manager, position_manager)

    # دو وظیفه اصلی برنامه
    telegram_task = interactive_bot.application.run_polling()
    main_logic_task = daily_reset_task(APP_CONFIG, state_manager, position_manager)

    print("Running Telegram bot and main logic concurrently...")
    await asyncio.gather(telegram_task, main_logic_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nBot stopped by user.')
        shutdown_all_monitors()