# posmanagerfunc/trend_analyzer.py

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
# ایمپورت توابع از فایل‌های دیگر پروژه
from fetch_futures_binance import fetch_futures_klines
from volume_profile import calc_daily_volume_profile

def get_price_action_score(symbol):
    """
    تحلیل روند بر اساس ساختار پرایس اکشن روزانه (Higher-Highs, Lower-Lows).
    این تابع به ساختار بازار در تایم‌فریم بالا نگاه می‌کند.
    """
    # دریافت داده‌های ۳ روز اخیر برای مقایسه روز گذشته با روز قبل از آن
    df_daily = fetch_futures_klines(symbol, '1d', datetime.now(timezone.utc) - timedelta(days=3), datetime.now(timezone.utc))
    if df_daily.empty or len(df_daily) < 2:
        return 0, "داده کافی برای تحلیل پرایس اکشن روزانه نیست."
    
    # آخرین کندل روزانه ممکن است کامل نشده باشد، پس ما از دو کندل قبلی استفاده می‌کنیم.
    last_completed_day = df_daily.iloc[-2]
    day_before = df_daily.iloc[-3]

    is_hh = last_completed_day['high'] > day_before['high']
    is_hl = last_completed_day['low'] > day_before['low']
    is_ll = last_completed_day['low'] < day_before['low']
    is_lh = last_completed_day['high'] < day_before['high']

    if is_hh and is_hl:
        return 2, "ساختار روزانه صعودی قوی (HH & HL)"
    if is_ll and is_lh:
        return -2, "ساختار روزانه نزولی قوی (LL & LH)"
    if is_hh and is_ll:
        return 0, "ساختار روزانه خنثی (Outside Day)"
    if is_lh and is_hl:
        return 0, "ساختار روزانه خنثی (Inside Day)"
    
    return 0, "ساختار روزانه نامشخص"

def get_cvd_score(symbol):
    """
    تحلیل روند کوتاه‌مدت بر اساس جریان سفارشات تجمعی (Cumulative Volume Delta)
    در ۲۴ ساعت گذشته.
    """
    # دریافت داده‌های ۴۸ ساعته با کندل‌های ۱۵ دقیقه‌ای برای تحلیل CVD
    df = fetch_futures_klines(symbol, '15m', datetime.now(timezone.utc) - timedelta(hours=48), datetime.now(timezone.utc))
    if df.empty:
        return 0, "داده کافی برای تحلیل CVD نیست."

    # محاسبه دلتای هر کندل: (حجم خرید - حجم فروش)
    # فرمول: 2 * taker_buy_volume - total_volume
    df['delta'] = 2 * df['taker_buy_base_asset_volume'] - df['volume']
    
    # محاسبه CVD در ۲۴ ساعت گذشته (۹۶ کندل ۱۵ دقیقه‌ای)
    cvd_24h = df['delta'].tail(96).sum()

    if cvd_24h > 0:
        return 1, f"فشار خرید در ۲۴ ساعت گذشته (CVD: {cvd_24h:,.0f})"
    elif cvd_24h < 0:
        return -1, f"فشار فروش در ۲۴ ساعت گذشته (CVD: {cvd_24h:,.0f})"
    
    return 0, "جریان سفارشات در ۲۴ ساعت گذشته خنثی بوده است."


def get_weekly_vp_score(symbol):
    """تحلیل روند بر اساس پروفایل حجمی هفته گذشته"""
    today = datetime.now(timezone.utc)
    start_of_this_week = today - timedelta(days=today.weekday())
    start_of_last_week = start_of_this_week - timedelta(weeks=1)
    
    df_last_week = fetch_futures_klines(symbol, '1h', start_of_last_week, start_of_this_week)
    if df_last_week.empty: return 0, "داده کافی برای پروفایل حجمی هفتگی نیست."
    
    vp = calc_daily_volume_profile(df_last_week)
    vah, val = vp.get('vah'), vp.get('val')
    if not vah or not val or vah == 0 or val == 0: return 0, "محاسبه محدوده ارزش هفتگی ممکن نبود."
    
    current_price_df = fetch_futures_klines(symbol, '1m', today - timedelta(minutes=5), today)
    if current_price_df.empty: return 0, "قیمت لحظه‌ای دریافت نشد."
    current_price = current_price_df.iloc[-1]['close']
    
    if current_price > vah: return 1, f"قیمت بالای محدوده ارزش هفته قبل ({vah:,.2f}) است."
    if current_price < val: return -1, f"قیمت پایین محدوده ارزش هفته قبل ({val:,.2f}) است."
    return 0, "قیمت داخل محدوده ارزش هفته قبل است."

def get_linreg_score(symbol, period=100):
    """تحلیل روند با رگرسیون خطی ۴ ساعته به صورت دستی"""
    df_4h = fetch_futures_klines(symbol, '4h', datetime.now(timezone.utc) - timedelta(days=int(period*4/6)), datetime.now(timezone.utc))
    if df_4h.empty or len(df_4h) < period: return 0, "داده کافی برای رگرسیون خطی نیست."
    
    points = df_4h['close'].tail(period)
    x = np.arange(len(points))
    slope, _ = np.polyfit(x, points, 1)
    
    # نرمال‌سازی شیب بر اساس قیمت برای مقایسه بهتر بین ارزها
    normalized_slope = slope / points.mean()
    
    if normalized_slope > 0.0005: return 2, "شیب کانال رگرسیون 4 ساعته قویا مثبت است."
    if normalized_slope > 0.0001: return 1, "شیب کانال رگرسیون 4 ساعته مثبت است."
    if normalized_slope < -0.0005: return -2, "شیب کانال رگرسیون 4 ساعته قویا منفی است."
    if normalized_slope < -0.0001: return -1, "شیب کانال رگرسیون 4 ساعته منفی است."
    return 0, "شیب کانال رگرسیون 4 ساعته خنثی است."
    
def generate_master_trend_report(symbol, state_manager, df_historical, df_intraday):
    """
    گزارش جامع روند را با ترکیب تحلیل‌های پیشرفته و سیستم امتیازدهی وزن‌دار تولید می‌کند.
    """
    print(f"Generating master trend report for {symbol}...")
    report_lines = ["**📊 گزارش جامع روند (چندزمانی):**\n"]
    total_score = 0
    
    # تعریف وزن برای هر نوع تحلیل
    weights = {
        "price_action": 1.5,
        "volume_profile": 1.5,
        "linear_regression": 1.0,
        "cvd": 0.5 
    }

    # ۱. تحلیل ساختار پرایس اکشن (تایم بالا - بیشترین وزن)
    try:
        pa_score, pa_narrative = get_price_action_score(symbol)
        total_score += pa_score * weights["price_action"]
        report_lines.append(f"- **پرایس اکشن (روزانه)**: {pa_narrative} (امتیاز: `{pa_score * weights['price_action']:.1f}`)")
    except Exception as e: report_lines.append(f"- **پرایس اکشن (روزانه)**: خطا در تحلیل - {e}")
    
    # ۲. تحلیل پروفایل حجمی (تایم بالا - بیشترین وزن)
    try:
        vp_score, vp_narrative = get_weekly_vp_score(symbol)
        total_score += vp_score * weights["volume_profile"]
        report_lines.append(f"- **پروفایل حجمی (هفتگی)**: {vp_narrative} (امتیاز: `{vp_score * weights['volume_profile']:.1f}`)")
    except Exception as e: report_lines.append(f"- **پروفایل حجمی (هفتگی)**: خطا در تحلیل - {e}")
    
    # ۳. تحلیل رگرسیون خطی (تایم میانی - وزن متوسط)
    try:
        linreg_score, linreg_narrative = get_linreg_score(symbol)
        total_score += linreg_score * weights["linear_regression"]
        report_lines.append(f"- **رگرسیون خطی (4H)**: {linreg_narrative} (امتیاز: `{linreg_score * weights['linear_regression']:.1f}`)")
    except Exception as e: report_lines.append(f"- **رگرسیون خطی (4H)**: خطا در تحلیل - {e}")

    # ۴. تحلیل جریان سفارشات (تایم پایین - کمترین وزن)
    try:
        cvd_score, cvd_narrative = get_cvd_score(symbol)
        total_score += cvd_score * weights["cvd"]
        report_lines.append(f"- **جریان سفارشات (24H)**: {cvd_narrative} (امتیاز: `{cvd_score * weights['cvd']:.1f}`)")
    except Exception as e: report_lines.append(f"- **جریان سفارشات (24H)**: خطا در تحلیل - {e}")
    
    # --- نتیجه‌گیری نهایی بر اساس امتیاز کل ---
    final_trend = "NEUTRAL"
    if total_score >= 3.0:
        final_trend = "BULLISH"
    elif total_score > 0.5:
        final_trend = "BULLISH"
    elif total_score <= -3.0:
        final_trend = "BEARISH"
    elif total_score < -0.5:
        final_trend = "BEARISH"
    
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score:.2f}`، روند کلی **{final_trend}** ارزیابی می‌شود.")
    
    state_manager.update_symbol_state(symbol, 'htf_trend', final_trend)
    state_manager.update_symbol_state(symbol, 'trend_report', "\n".join(report_lines))
    
    return final_trend, "\n".join(report_lines)