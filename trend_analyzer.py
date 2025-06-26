# posmanagerfunc/trend_analyzer.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from fetch_futures_binance import fetch_futures_klines
from volume_profile import calc_daily_volume_profile

def analyze_trend_and_generate_report(historical_df, intraday_df):
    """
    روند را بر اساس تحلیل ساختار ۳ روز گذشته و CVD روز جاری تحلیل کرده و گزارش می‌دهد.
    """
    report_lines = ["**تحلیل روند:**\n"]
    if historical_df.empty or len(historical_df.groupby(pd.Grouper(key='open_time', freq='D'))) < 3:
        return "INSUFFICIENT_DATA", "داده تاریخی کافی (حداقل ۳ روز) وجود ندارد."
    
    daily_data = historical_df.groupby(pd.Grouper(key='open_time', freq='D')).agg(
        high=('high', 'max'), 
        low=('low', 'min'),
        taker_buy_volume=('taker_buy_base_asset_volume', 'sum'),
        total_volume=('volume', 'sum')
    ).dropna()
    
    last_3_days = daily_data.tail(3)
    if len(last_3_days) < 3:
        return "INSUFFICIENT_DATA", "داده کافی برای مقایسه سه روز اخیر وجود ندارد."

    day_1, day_2, day_3 = last_3_days.iloc[0], last_3_days.iloc[1], last_3_days.iloc[2]
    
    pa_score = 0
    # مقایسه پریروز با روز قبل‌تر
    if day_2['high'] > day_1['high'] and day_2['low'] > day_1['low']: pa_score += 1
    elif day_2['high'] < day_1['high'] and day_2['low'] < day_1['low']: pa_score -= 1
    # مقایسه دیروز با پریروز
    if day_3['high'] > day_2['high'] and day_3['low'] > day_2['low']: pa_score += 1
    elif day_3['high'] < day_2['high'] and day_3['low'] < day_2['low']: pa_score -= 1
        
    report_lines.append(f"- **پرایس اکشن (ساختار ۳ روز گذشته)**: امتیاز: `{pa_score}`")
    
    cvd_score = 0
    if not intraday_df.empty:
        intraday_taker_buy = intraday_df['taker_buy_base_asset_volume'].sum()
        intraday_total_volume = intraday_df['volume'].sum()
        current_delta = 2 * intraday_taker_buy - intraday_total_volume
        if current_delta > 0: cvd_score = 1
        elif current_delta < 0: cvd_score = -1
        delta_narrative = f"دلتا تجمعی **امروز** {'مثبت' if cvd_score > 0 else 'منفی' if cvd_score < 0 else 'خنثی'} است (`{current_delta:,.0f}`)."
    else:
        delta_narrative = "داده‌ای برای تحلیل CVD امروز موجود نیست."
    report_lines.append(f"- **جریان سفارشات (CVD امروز)**: {delta_narrative} (امتیاز: `{cvd_score}`)")
    
    total_score = pa_score + cvd_score
    final_trend = "SIDEWAYS"
    if total_score >= 2: final_trend = "STRONG_UP"
    elif total_score > 0: final_trend = "UP_WEAK"
    elif total_score <= -2: final_trend = "STRONG_DOWN"
    elif total_score < 0: final_trend = "DOWN_WEAK"
    
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score}`، روند امروز **{final_trend}** ارزیابی می‌شود.")
    return final_trend, "\n".join(report_lines)