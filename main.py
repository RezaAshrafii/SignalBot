# main.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import time
import threading
import pytz  # کتابخانه جدید برای مدیریت منطقه زمانی

from alert import notify_startup
from fetch_futures_binance import fetch_futures_klines
from untouched_levels import find_untouched_levels
from master_monitor import MasterMonitor
from state_manager import StateManager
from interactive_bot import InteractiveBot
from price_updater import PriceUpdater
from position_manager import PositionManager

# دیکشنری برای نگهداری مانیتورهای فعال برای هر ارز
active_monitors = {}

def determine_composite_trend(df):
    """روند را با منطق نهایی امتیازدهی و دلتا مشخص می‌کند."""
    print("Analyzing daily data to determine composite trend...")
    # توجه: این تابع داده‌هایی دریافت می‌کند که از قبل بر اساس زمان نیویورک فیلتر شده‌اند.
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
        monitor.stop()
    active_monitors.clear()
    time.sleep(5)

def perform_daily_reinitialization(symbols, bot_token, chat_ids, state_manager, position_manager, analysis_end_time_ny):
    """
    فرآیند کامل تحلیل روزانه را بر اساس زمان نیویورک برای تمام ارزها اجرا می‌کند.
    """
    shutdown_all_monitors()
    print(f"\n===== 🗽 STARTING NY-BASED DAILY INITIALIZATION FOR {analysis_end_time_ny.date()} 🗽 =====")

    # زمان پایان تحلیل (بامداد نیویورک) را به UTC تبدیل می‌کنیم چون API بایننس با UTC کار می‌کند
    analysis_end_time_utc = analysis_end_time_ny.astimezone(timezone.utc)
    
    days_to_fetch = 10
    analysis_start_time_utc = analysis_end_time_utc - timedelta(days=days_to_fetch)
    
    # برای بررسی سطوح لمس شده، دیتا را تا لحظه حال دریافت می‌کنیم
    now_utc = datetime.now(timezone.utc)
    
    for symbol in symbols:
        print(f"\n----- Initializing for {symbol} -----")
        
        # دریافت داده‌های کندل با زمان UTC
        df_for_analysis = fetch_futures_klines(symbol, '1m', analysis_start_time_utc, now_utc)
        
        if df_for_analysis.empty:
            print(f"Could not fetch data for {symbol}. Skipping this symbol.")
            continue

        # تعیین روند بر اساس داده‌های *قبل* از شروع روز معاملاتی نیویورک
        trend_df = df_for_analysis[df_for_analysis['open_time'] < analysis_end_time_utc].copy()
        htf_trend = determine_composite_trend(trend_df)
        state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
        print(f"  -> {symbol} Composite HTF Trend (based on data before NY day start): {htf_trend}")

        # **مهم**: تبدیل زمان UTC به زمان نیویورک برای تمام داده‌ها
        # این روش بسیار دقیق‌تر از کم کردن یک عدد ثابت است و ساعت تابستانی را در نظر می‌گیرد.
        df_for_analysis['ny_datetime'] = df_for_analysis['open_time'].dt.tz_convert('America/New_York')
        df_for_analysis['ny_date'] = df_for_analysis['ny_datetime'].dt.date
        
        untouched_levels = find_untouched_levels(df_for_analysis, date_col='ny_date')
        state_manager.update_symbol_state(symbol, 'untouched_levels', untouched_levels)
        print(f"  -> Found {len(untouched_levels)} untouched levels for {symbol}.")
        if untouched_levels:
            print("--- Monitoring The Following Key Levels (NY Time Based) ---")
            for lvl in untouched_levels[:5]:
                print(f"  - {lvl['level_type']} ({lvl['date']}) at {lvl['level']:,.2f}")
            if len(untouched_levels) > 5:
                print(f"  ... and {len(untouched_levels) - 5} more levels.")

        # اجرای مانیتور مرکزی برای این ارز
        master_monitor = MasterMonitor(
            key_levels=untouched_levels, symbol=symbol,
            daily_trend=htf_trend, position_manager=position_manager
        )
        master_monitor.run()
        active_monitors[symbol] = master_monitor

if __name__ == "__main__":
    # --- ۱. تنظیمات اصلی ---
    SYMBOLS_TO_MONITOR = ['BTCUSDT', 'ETHUSDT']
    BOT_TOKEN = "8118371101:AAFDuMwXDhDzicSY4vQU-pOpv-BdD_3SJko"
    CHAT_IDS = ["6697060159"]
    
    RISK_CONFIG = { "RISK_PER_TRADE_PERCENT": 1.0, "DAILY_DRAWDOWN_LIMIT_PERCENT": 3.0, "RR_RATIOS": [1, 2, 3] }

    # --- ۲. راه‌اندازی سیستم‌های مرکزی ---
    print("Initializing core systems...")
    state_manager = StateManager(SYMBOLS_TO_MONITOR)
    position_manager = PositionManager(state_manager, BOT_TOKEN, CHAT_IDS, RISK_CONFIG)
    
    interactive_bot = InteractiveBot(BOT_TOKEN, state_manager, position_manager)
    interactive_bot.run()

    for symbol in SYMBOLS_TO_MONITOR:
        price_updater = PriceUpdater(symbol, state_manager)
        price_updater.run()

    # --- ۳. حلقه اصلی برنامه برای مدیریت راه‌اندازی مجدد روزانه بر اساس زمان نیویورک ---
    ny_timezone = pytz.timezone("America/New_York")
    last_check_date_ny = None
    
    try:
        while True:
            # زمان فعلی را در منطقه زمانی نیویورک دریافت می‌کنیم
            now_ny = datetime.now(ny_timezone)
            current_date_ny = now_ny.date()
            
            if last_check_date_ny != current_date_ny:
                # تاریخ در نیویورک تغییر کرده است، فرآیند را مجددا اجرا کن
                last_check_date_ny = current_date_ny
                
                # زمان دقیق شروع روز معاملاتی نیویورک (بامداد)
                ny_midnight_today = now_ny.replace(hour=0, minute=0, second=0, microsecond=0)
                
                perform_daily_reinitialization(
                    SYMBOLS_TO_MONITOR, BOT_TOKEN, CHAT_IDS, 
                    state_manager, position_manager, 
                    ny_midnight_today
                )
                
                notify_startup(BOT_TOKEN, CHAT_IDS, SYMBOLS_TO_MONITOR)
                print(f"\n✅ All systems re-initialized for NY trading day: {current_date_ny}. Waiting for new day...")

            time.sleep(60)
            
    except KeyboardInterrupt:
        print('\nBot stopped by user.')
        shutdown_all_monitors()