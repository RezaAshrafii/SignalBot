# main.py
import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import threading
import pytz # برای مدیریت منطقه زمانی نیویورک

# وارد کردن تمام ماژول‌های پروژه
from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from interactive_bot import InteractiveBot
# PriceUpdater دیگر لازم نیست، DataStreamManager جایگزین آن می‌شود
# from price_updater import PriceUpdater 
from position_manager import PositionManager
# DataStreamManager در نسخه‌های بعدی که ستاپ‌های لحظه‌ای را اضافه کنیم، استفاده خواهد شد
# from data_stream_manager import DataStreamManager 
from position_manager import PositionManager

active_monitors = {}

def determine_composite_trend(df):
    """روند را با منطق نهایی امتیازدهی و دلتا مشخص می‌کند."""
    print("Analyzing daily data to determine composite trend...")
    daily_data = df.groupby(pd.Grouper(key='open_time', freq='D')).agg(high=('high', 'max'), low=('low', 'min'), taker_buy_volume=('taker_buy_base_asset_volume', 'sum'), total_volume=('volume', 'sum')).dropna()
    if len(daily_data) < 3: return "INSUFFICIENT_DATA"
    
    last_3_days = daily_data.tail(3)
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
    
    print(f"  -> Price Action Trend (3-day Net Score): {price_trend} (Score: {trend_score})")
    print(f"  -> Last Day's Delta Trend: {cvd_trend} (Delta Value: {last_day_delta:,.0f})")
    
    if price_trend == "UP" and cvd_trend == "UP": return "STRONG_UP"
    elif price_trend == "DOWN" and cvd_trend == "DOWN": return "STRONG_DOWN"
    elif price_trend == "UP": return "UP_WEAK"
    elif price_trend == "DOWN": return "DOWN_WEAK"
    else: return "SIDEWAYS"

def shutdown_all_monitors():
    """تمام مانیتورهای فعال را متوقف می‌کند."""
    print("Shutting down all active symbol monitors...")
    for symbol, monitor in active_monitors.items():
        if hasattr(monitor, 'stop'): # برای سازگاری با نسخه‌های آینده
            monitor.stop()
    active_monitors.clear()
    time.sleep(2)

def perform_daily_reinitialization(symbols, bot_token, chat_ids, state_manager, position_manager, analysis_end_time_ny):
    """
    چرخه کامل تحلیل و راه‌اندازی را برای شروع هر روز معاملاتی جدید اجرا می‌کند.
    """
    shutdown_all_monitors()
    print(f"\n===== 🗽 STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} 🗽 =====")
    analysis_end_time_utc = analysis_end_time_ny.astimezone(timezone.utc)
    # دریافت ۱۰ روز داده برای تحلیل روند و سطوح
    analysis_start_time_utc = analysis_end_time_utc - timedelta(days=10)
    now_utc = datetime.now(timezone.utc)
    
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        df_for_analysis = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, now_utc)
        if df_for_analysis.empty:
            print(f"Could not fetch data for {symbol}. Skipping this symbol.")
            continue

        trend_df = df_for_analysis[df_for_analysis['open_time'] < analysis_end_time_utc].copy()
        htf_trend = determine_composite_trend(trend_df)
        state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
        print(f"  -> {symbol} Composite HTF Trend: {htf_trend}")

        df_for_analysis['ny_date'] = df_for_analysis['open_time'].dt.tz_convert('America/New_York').dt.date
        untouched_levels = find_untouched_levels(df_for_analysis, date_col='ny_date')
        state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
        print(f"  -> Found {len(untouched_levels)} untouched levels.")

        # ساخت و اجرای مانیتور مرکزی برای این ارز
        master_monitor = MasterMonitor(
            key_levels=untouched_levels,
            symbol=symbol,
            daily_trend=htf_trend,
            position_manager=position_manager
        )
        active_monitors[symbol] = master_monitor
        master_monitor.run()

# main.py

if __name__ == "__main__":
    load_dotenv() # بارگذاری متغیرها از فایل .env

    # --- ۱. تنظیمات اصلی ---
    SYMBOLS_TO_MONITOR = ['BTCUSDT', 'ETHUSDT']

    # --- خواندن توکن و آیدی از متغیرهای محیطی ---
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_IDS_STR = os.getenv("CHAT_IDS")

    if not BOT_TOKEN or not CHAT_IDS_STR:
        print("خطا: متغیرهای BOT_TOKEN و CHAT_IDS در فایل .env تعریف نشده‌اند.")
        exit()

    CHAT_IDS = CHAT_IDS_STR.split(',') # برای پشتیبانی از چندین آیدی در آینده

    RISK_CONFIG = {
        "RISK_PER_TRADE_PERCENT": 1.0,
        "DAILY_DRAWDOWN_LIMIT_PERCENT": 3.0,
        "RR_RATIOS": [1, 2, 3]
    }

    # --- ۲. راه‌اندازی سیستم‌های مرکزی ---
    print("Initializing core systems...")
    state_manager = StateManager(SYMBOLS_TO_MONITOR)
    interactive_bot = InteractiveBot(BOT_TOKEN, state_manager, PositionManager)
    interactive_bot.run()
    # در این نسخه پیشرفته، دیکشنری مانیتورهای فعال را به مدیر پوزیشن پاس می‌دهیم
    position_manager = PositionManager(state_manager, BOT_TOKEN, CHAT_IDS, RISK_CONFIG, active_monitors)

    # --- ۳. حلقه اصلی برنامه برای مدیریت ریست روزانه ---
    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    
    try:
        while True:
            now_ny = datetime.now(ny_timezone)
            if last_check_date_ny != now_ny.date():
                last_check_date_ny = now_ny.date()
                ny_midnight_today = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                
                # اجرای فرآیند راه‌اندازی مجدد روزانه
                perform_daily_reinitialization(
                    SYMBOLS_TO_MONITOR, BOT_TOKEN, CHAT_IDS, 
                    state_manager, position_manager, 
                    ny_midnight_today
                )
                
                notify_startup(BOT_TOKEN, CHAT_IDS, SYMBOLS_TO_MONITOR)
                print(f"\n✅ All systems re-initialized for NY trading day: {last_check_date_ny}.")
                print("Bot is running. Waiting for the next day...")
            
            time.sleep(60) # هر ۶۰ ثانیه تاریخ را بررسی کن
            
    except KeyboardInterrupt:
        print('\nBot stopped by user.')
        shutdown_all_monitors()