# posmanagerfunc/trend_analyzer.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from fetch_futures_binance import fetch_futures_klines
from volume_profile import calc_daily_volume_profile

# --- توابع جدید برای محاسبه دستی اندیکاتورها ---

def get_ichimoku(df, tenkan=9, kijun=26, senkou=52):
    """محاسبه دستی خطوط ایچیموکو"""
    # Tenkan-sen (Conversion Line)
    high_9 = df['high'].rolling(window=tenkan).max()
    low_9 = df['low'].rolling(window=tenkan).min()
    df['tenkan_sen'] = (high_9 + low_9) / 2

    # Kijun-sen (Base Line)
    high_26 = df['high'].rolling(window=kijun).max()
    low_26 = df['low'].rolling(window=kijun).min()
    df['kijun_sen'] = (high_26 + low_26) / 2

    # Senkou Span A (Leading Span A)
    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(kijun)

    # Senkou Span B (Leading Span B)
    high_52 = df['high'].rolling(window=senkou).max()
    low_52 = df['low'].rolling(window=senkou).min()
    df['senkou_span_b'] = ((high_52 + low_52) / 2).shift(kijun)
    
    return df

def get_ichimoku_score(symbol):
    """تحلیل روند ۴ ساعته با ایچیموکو"""
    df_4h = fetch_futures_klines(symbol, '4h', datetime.now(timezone.utc) - timedelta(days=60), datetime.now(timezone.utc))
    if df_4h.empty or len(df_4h) < 52: return 0, "داده کافی برای ایچیموکو 4 ساعته نیست."
    
    df_4h = get_ichimoku(df_4h)
    last = df_4h.iloc[-1]
    
    if pd.isna(last.get('senkou_span_a')) or pd.isna(last.get('senkou_span_b')):
        return 0, "محاسبه ابر کومو ممکن نبود."
    
    if last['close'] > last['senkou_span_a'] and last['close'] > last['senkou_span_b']:
        return 1, "قیمت بالای ابر کومو 4 ساعته است (صعودی)"
    if last['close'] < last['senkou_span_a'] and last['close'] < last['senkou_span_b']:
        return -1, "قیمت پایین ابر کومو 4 ساعته است (نزولی)"
    return 0, "قیمت داخل ابر کومو 4 ساعته است (خنثی)"

def get_linreg_score(symbol, period=100):
    """تحلیل روند با رگرسیون خطی ۴ ساعته به صورت دستی"""
    df_4h = fetch_futures_klines(symbol, '4h', datetime.now(timezone.utc) - timedelta(days=int(period*4/6)), datetime.now(timezone.utc))
    if df_4h.empty or len(df_4h) < period: return 0, "داده کافی برای رگرسیون خطی نیست."
    
    points = df_4h['close'].tail(period)
    x = np.arange(len(points))
    # پیدا کردن بهترین خط با استفاده از numpy
    slope, _ = np.polyfit(x, points, 1)
    
    if slope > 0: return 1, "شیب کانال رگرسیون 4 ساعته مثبت است."
    if slope < 0: return -1, "شیب کانال رگرسیون 4 ساعته منفی است."
    return 0, "شیب کانال رگرسیون 4 ساعته خنثی است."
    
def get_weekly_vp_score(symbol):
    """تحلیل روند بر اساس پروفایل حجمی هفته گذشته"""
    today = datetime.now(timezone.utc)
    start_of_this_week = today - timedelta(days=today.weekday())
    start_of_last_week = start_of_this_week - timedelta(weeks=1)
    df_last_week = fetch_futures_klines(symbol, '1h', start_of_last_week, start_of_this_week)
    if df_last_week.empty: return 0, "داده کافی برای پروفایل حجمی هفتگی نیست."
    vp = calc_daily_volume_profile(df_last_week)
    vah, val = vp.get('vah'), vp.get('val')
    if not vah or not val: return 0, "محاسبه محدوده ارزش هفتگی ممکن نبود."
    current_price_df = fetch_futures_klines(symbol, '1m', today - timedelta(minutes=5), today)
    if current_price_df.empty: return 0, "قیمت لحظه‌ای دریافت نشد."
    current_price = current_price_df.iloc[-1]['close']
    if current_price > vah: return 1, f"قیمت بالای محدوده ارزش هفته قبل ({vah:,.2f}) است."
    if current_price < val: return -1, f"قیمت پایین محدوده ارزش هفته قبل ({val:,.2f}) است."
    return 0, "قیمت داخل محدوده ارزش هفته قبل است."

def generate_master_trend_report(symbol, state_manager):
    """
    گزارش جامع روند را با ترکیب سه تحلیل پیشرفته تولید می‌کند.
    """
    print(f"Generating master trend report for {symbol}...")
    report_lines = ["**📊 گزارش جامع روند (چندزمانی):**\n"]
    total_score = 0
    try:
        ichimoku_score, ichimoku_narrative = get_ichimoku_score(symbol)
        total_score += ichimoku_score
        report_lines.append(f"- **ایچیموکو (4H)**: {ichimoku_narrative} (امتیاز: `{ichimoku_score}`)")
    except Exception as e: report_lines.append(f"- **ایچیموکو (4H)**: خطا در تحلیل - {e}")
    try:
        vp_score, vp_narrative = get_weekly_vp_score(symbol)
        total_score += vp_score
        report_lines.append(f"- **پروفایل حجمی (هفتگی)**: {vp_narrative} (امتیاز: `{vp_score}`)")
    except Exception as e: report_lines.append(f"- **پروفایل حجمی (هفتگی)**: خطا در تحلیل - {e}")
    try:
        linreg_score, linreg_narrative = get_linreg_score(symbol)
        total_score += linreg_score
        report_lines.append(f"- **رگرسیون خطی (4H)**: {linreg_narrative} (امتیاز: `{linreg_score}`)")
    except Exception as e: report_lines.append(f"- **رگرسیون خطی (4H)**: خطا در تحلیل - {e}")

    final_trend = "SIDEWAYS"
    if total_score >= 2: final_trend = "BULLISH"
    elif total_score > 0: final_trend = "BULLISH"
    elif total_score <= -2: final_trend = "BEARISH"
    elif total_score < 0: final_trend = "BEARISH"
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score}`، روند کلی **{final_trend}** ارزیابی می‌شود.")
    
    state_manager.update_symbol_state(symbol, 'htf_trend', final_trend)
    state_manager.update_symbol_state(symbol, 'trend_report', "\n".join(report_lines))
    
    return final_trend, "\n".join(report_lines)