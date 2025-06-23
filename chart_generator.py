# posmanagerfunc/chart_generator.py
import pandas as pd
import mplfinance as mpf
import io

def generate_chart_image(klines, key_levels, current_price, symbol):
    """
    بر اساس داده‌های ورودی، یک تصویر چارت تولید کرده و آن را به صورت بایت برمی‌گرداند.
    """
    if not klines or len(klines) < 2:
        return None

    # تبدیل لیست دیکشنری کندل‌ها به DataFrame مورد نیاز mplfinance
    df = pd.DataFrame(klines)
    df['open_time'] = pd.to_datetime(df['open_time'])
    df.set_index('open_time', inplace=True)
    
    # اطمینان از اینکه ستون‌ها از نوع عددی هستند
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    # آماده‌سازی خطوط افقی برای سطوح کلیدی
    hlines_data = {'hlines': [], 'colors': [], 'linestyles': '--'}
    if key_levels:
        hlines_data['hlines'].extend([lvl['level'] for lvl in key_levels])
        for lvl in key_levels:
            if 'H' in lvl['level_type']: hlines_data['colors'].append('red')
            elif 'L' in lvl['level_type']: hlines_data['colors'].append('green')
            else: hlines_data['colors'].append('blue')

    # اضافه کردن خط قیمت فعلی
    if current_price:
        hlines_data['hlines'].append(current_price)
        hlines_data['colors'].append('orange')

    # ساخت استایل چارت
    mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', wick={'up':'green', 'down':'red'}, volume='inherit')
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', base_mpf_style='charles')

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
        hlines=hlines_data,
        savefig=dict(fname=buf, dpi=120), # ذخیره در بافر
        figsize=(15, 8)
    )
    
    buf.seek(0)
    return buf