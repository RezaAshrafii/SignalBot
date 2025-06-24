# vp_values_trend.py
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import argparse
import os
import pytz

from fetch_futures_binance import fetch_futures_klines
from volume_profile import calc_daily_volume_profile

def analyze_trend_and_report(historical_df, intraday_df=None):
    """
    روند را بر اساس تحلیل ساختار ۳ روز گذشته و (به صورت اختیاری) CVD روز جاری تحلیل می‌کند.
    """
    report_lines = ["**تحلیل روند:**\n"]
    if historical_df.empty or len(historical_df.groupby('ny_date')) < 3:
        return "INSUFFICIENT_DATA", "داده تاریخی کافی (حداقل ۳ روز) وجود ندارد."
    
    daily_data = historical_df.groupby('ny_date').agg(high=('high', 'max'), low=('low', 'min')).dropna()
    last_3_days = daily_data.tail(3)
    if len(last_3_days) < 3: return "INSUFFICIENT_DATA", "داده کافی برای مقایسه سه روز اخیر وجود ندارد."

    day_1, day_2, day_3 = last_3_days.iloc[0], last_3_days.iloc[1], last_3_days.iloc[2]
    report_lines.append("- **پرایس اکشن (ساختار ۳ روز گذشته):**")
    pa_score = 0
    
    # مقایسه پریروز با روز قبل‌تر
    score1_narrative = "خنثی"
    if day_2['high'] > day_1['high'] and day_2['low'] > day_1['low']: pa_score += 1; score1_narrative = "صعودی (HH & HL)"
    elif day_2['high'] < day_1['high'] and day_2['low'] < day_1['low']: pa_score -= 1; score1_narrative = "نزولی (LL & LH)"
    report_lines.append(f"  - پریروز نسبت به روز قبل: {score1_narrative} (امتیاز: {pa_score})")

    # مقایسه دیروز با پریروز
    score2_narrative = "خنثی"
    if day_3['high'] > day_2['high'] and day_3['low'] > day_2['low']: pa_score += 1; score2_narrative = "صعودی (HH & HL)"
    elif day_3['high'] < day_2['high'] and day_3['low'] < day_2['low']: pa_score -= 1; score2_narrative = "نزولی (LL & LH)"
    report_lines.append(f"  - دیروز نسبت به پریروز: {score2_narrative} (امتیاز کل PA: {pa_score})")
     
    pa_score = 0
    # مقایسه پریروز با روز قبل‌تر
    if day_2['high'] > day_1['high'] and day_2['low'] > day_1['low']: pa_score += 1
    elif day_2['high'] < day_1['high'] and day_2['low'] < day_1['low']: pa_score -= 1
    # مقایسه دیروز با پریروز
    if day_3['high'] > day_2['high'] and day_3['low'] > day_2['low']: pa_score += 1
    elif day_3['high'] < day_2['high'] and day_3['low'] < day_2['low']: pa_score -= 1
        
    report_lines.append(f"- **پرایس اکشن (ساختار ۳ روز گذشته)**: امتیاز: `{pa_score}`")

    total_score = pa_score
    # تحلیل CVD فقط در صورتی که داده‌های روز جاری ارائه شده باشد
    if intraday_df is not None:
        cvd_score = 0
        if not intraday_df.empty:
            taker_buy = intraday_df['taker_buy_base_asset_volume'].sum()
            total_vol = intraday_df['volume'].sum()
            current_delta = 2 * taker_buy - total_vol
            if current_delta > 0: cvd_score = 1
            elif current_delta < 0: cvd_score = -1
            delta_narrative = f"دلتا تجمعی **امروز** {'مثبت' if cvd_score > 0 else 'منفی' if cvd_score < 0 else 'خنثی'} است (`{current_delta:,.0f}`)."
        else:
            delta_narrative = "داده‌ای برای تحلیل CVD امروز موجود نیست."
        report_lines.append(f"- **جریان سفارشات (CVD امروز)**: {delta_narrative} (امتیاز: `{cvd_score}`)")
        total_score += cvd_score
    
    final_trend = "SIDEWAYS"
    if total_score >= 2: final_trend = "STRONG_UP"
    elif total_score > 0: final_trend = "UP_WEAK"
    elif total_score <= -2: final_trend = "STRONG_DOWN"
    elif total_score < 0: final_trend = "DOWN_WEAK"
    
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score}`، روند **{final_trend}** ارزیابی می‌شود.")
    return "\n".join(report_lines)

def display_analysis(symbol, source_file=None, analysis_date_str=None):
    """
    داده‌ها را دریافت، مقادیر کلیدی را محاسبه و روند را تحلیل و چاپ می‌کند.
    """
    print(f"\n{'='*20} Analyzing Data for {symbol} {'='*20}")
    ny_timezone = pytz.timezone("America/New_York")

    if source_file:
        print(f"Loading data from local file: {source_file}")
        if not os.path.exists(source_file): print(f"Error: File not found at {source_file}"); return
        df = pd.read_csv(source_file, parse_dates=['open_time'])
        df['open_time'] = df['open_time'].dt.tz_localize('UTC')
    else:
        print("Fetching live data from Binance...")
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=15)
        df = fetch_futures_klines(symbol, '1m', start_time, end_time)

    if df.empty: print("No data available to analyze."); return
        
    df['ny_date'] = df['open_time'].dt.tz_convert(ny_timezone).dt.date
    
    # --- [ویژگی جدید] --- منطق بک‌تست تاریخی
    if analysis_date_str:
        target_date = datetime.strptime(analysis_date_str, '%Y-%m-%d').date()
        print(f"\n--- Running Historical Analysis for Date: {target_date} ---")
        # داده‌های تاریخی، تمام روزهای کامل قبل از تاریخ هدف هستند
        historical_df = df[df['ny_date'] < target_date].copy()
        # در این حالت، داده روز جاری نداریم چون فقط به گذشته نگاه می‌کنیم
        intraday_df = None
    else:
        today_ny_date = datetime.now(ny_timezone).date()
        historical_df = df[df['ny_date'] < today_ny_date].copy()
        intraday_df = df[df['ny_date'] == today_ny_date].copy()

    if historical_df.empty: print("Not enough historical data to analyze."); return
        
    daily_groups = historical_df.groupby('ny_date')
    last_4_days_dates = sorted(daily_groups.groups.keys())[-4:]
    
    print("\n--- Key Volume Profile & Price Levels (Last 4 Completed Days) ---")
    all_daily_stats = []
    for trade_date in last_4_days_dates:
        daily_df = daily_groups.get_group(trade_date)
        all_daily_stats.append({
            "Date": trade_date.strftime('%Y-%m-%d'),
            "High": daily_df['high'].max(), "Low": daily_df['low'].min(),
            **calc_daily_volume_profile(daily_df)
        })
        
    stats_df = pd.DataFrame(all_daily_stats).set_index('Date')
    print(stats_df.to_string(formatters={col: '{:,.2f}'.format for col in stats_df.columns}))
    
    print("\n--- Price Action & CVD Trend Analysis ---")
    trend_report = analyze_trend_and_report(historical_df=historical_df, intraday_df=intraday_df)
    print(trend_report)
    print('='*60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze volume profile and price action trend for a given symbol.")
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help="The trading symbol to analyze (e.g., BTCUSDT).")
    parser.add_argument('--file', type=str, help="Optional path to a local CSV data file.")
    # --- [ویژگی جدید] --- پارامتر جدید برای بک‌تست تاریخی
    parser.add_argument('--date', type=str, help="Optional: Analyze trend for a specific past date (YYYY-MM-DD).")
    
    args = parser.parse_args()
    display_analysis(args.symbol, args.file, args.date)