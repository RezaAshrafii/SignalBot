# posmanagerfunc/chart_generator.py
import pandas as pd
import mplfinance as mpf
import io

def generate_chart_image(klines, key_levels, current_price, symbol):
    """
    بر اساس داده‌های ورودی، یک تصویر چارت تولید کرده و آن را به صورت بایت برمی‌گرداند.
    """
    if not klines:
        return None

    # تبدیل لیست دیکشنری کندل‌ها به DataFrame مورد نیاز mplfinance
    df = pd.DataFrame(klines)
    df['open_time'] = pd.to_datetime(df['open_time'])
    df.set_index('open_time', inplace=True)
    
    # اطمینان از اینکه ستون‌ها از نوع عددی هستند
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    # آماده‌سازی خطوط افقی برای سطوح کلیدی
    hlines = [lvl['level'] for lvl in key_levels]
    line_colors = []
    for lvl in key_levels:
        if 'H' in lvl['level_type']: line_colors.append('red')   # مقاومت‌ها
        elif 'L' in lvl['level_type']: line_colors.append('green') # حمایت‌ها
        else: line_colors.append('blue') # بقیه سطوح مانند POC

    # ساخت استایل چارت
    mc = mpf.make_marketcolors(up='green', down='red', wick={'up':'green', 'down':'red'}, volume='inherit')
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':')

    # ایجاد یک بافر در حافظه برای ذخیره تصویر
    buf = io.BytesIO()
    
    # رسم چارت
    mpf.plot(
        df,
        type='candle',
        style=style,
        title=f'\n{symbol} - 1-Minute Chart',
        ylabel='Price (USDT)',
        volume=True,
        hlines=dict(hlines=hlines, colors=line_colors, linestyle='--'),
        savefig=dict(fname=buf, dpi=100), # ذخیره در بافر
        figsize=(12, 7)
    )
    
    buf.seek(0)
    return buf