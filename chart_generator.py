# chart_generator.py

import pandas as pd
import mplfinance as mpf
import os

def generate_signal_chart(
    symbol: str,
    price_data_15m: pd.DataFrame,
    all_levels: dict,
    volume_profile_data: pd.DataFrame, # دیتافریم دقیق پروفایل حجم
    output_path: str = "charts"
):
    """
    یک چارت کامل شامل کندل‌های ۱۵ دقیقه، سطوح کلیدی و پروفایل حجم روزانه
    مشابه تصویر ارسالی تولید و ذخیره می‌کند.
    """
    if price_data_15m.empty:
        print("Chart generation skipped: 15m price data is empty.")
        return None

    # --- آماده‌سازی داده‌ها ---
    # اطمینان از اینکه ایندکس دیتافریم از نوع Datetime است
    price_data_15m.index = pd.to_datetime(price_data_15m.index)
    
    # آخرین قیمت برای فیلتر کردن سطوح نزدیک
    current_price = price_data_15m['close'].iloc[-1]
    
    # --- ۱. آماده‌سازی لیست سطوح کلیدی برای رسم ---
    horizontal_lines = []
    line_colors = []
    line_styles = []

    # سطوح VAH/VAL/POC
    daily_vp = all_levels.get('daily_vp', {})
    if daily_vp.get('vah'): horizontal_lines.append(daily_vp['vah']); line_colors.append('red'); line_styles.append('-.')
    if daily_vp.get('val'): horizontal_lines.append(daily_vp['val']); line_colors.append('green'); line_styles.append('-.')
    if daily_vp.get('poc', {}).get('price'): horizontal_lines.append(daily_vp['poc']['price']); line_colors.append('cyan'); line_styles.append('--')
        
    # سطوح PDH/PDL
    if all_levels.get('pdh'): horizontal_lines.append(all_levels['pdh']); line_colors.append('orangered'); line_styles.append(':')
    if all_levels.get('pdl'): horizontal_lines.append(all_levels['pdl']); line_colors.append('lime'); line_styles.append(':')

    # افزودن سطوح دیگر مثل FVG یا Ichimoku در اینجا امکان‌پذیر است
    # ...

    # --- ۲. تنظیمات استایل چارت ---
    # استایل تیره مشابه تصویر شما
    mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', edge='inherit', wick='inherit', volume='in')
    style = mpf.make_style(base_mpf_style='nightclouds', marketcolors=mc)

    # --- ۳. آماده‌سازی داده‌های پروفایل حجم ---
    # mplfinance به فرمت خاصی برای پروفایل حجم نیاز دارد
    if volume_profile_data is not None and not volume_profile_data.empty:
        # فرض بر این است که volume_profile_data دارای ستون‌های 'price' و 'volume' است
        vp_df = volume_profile_data.set_index('price')['volume']
    else:
        vp_df = None

    # --- ۴. ساخت و ذخیره چارت ---
    try:
        # اطمینان از وجود پوشه برای ذخیره چارت
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        filename = os.path.join(output_path, f"{symbol}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png")

        # رسم چارت اصلی
        mpf.plot(
            price_data_15m,
            type='candle',
            style=style,
            title=f"\n{symbol} - 15 Minute Chart",
            ylabel='Price ($)',
            volume=True,
            panel_ratios=(4, 1), # نسبت پنل قیمت به پنل حجم
            hlines=dict(hlines=horizontal_lines, colors=line_colors, linestyle=line_styles, linewidths=1.2),
            volume_profile=vp_df,
            volume_profile_width=0.4, # عرض پروفایل حجم
            savefig=filename
        )
        print(f"✅ Chart for {symbol} saved to {filename}")
        return filename
    except Exception as e:
        print(f"❌ Error generating chart for {symbol}: {e}")
        return None