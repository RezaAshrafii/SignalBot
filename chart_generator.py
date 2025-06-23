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

    df = pd.DataFrame(klines)
    df['open_time'] = pd.to_datetime(df['open_time'])
    df.set_index('open_time', inplace=True)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    hlines_data = {'hlines': [], 'colors': [], 'linestyle': '--'} # <-- [اصلاح شد] linestyles به linestyle تغییر کرد
    if key_levels:
        hlines_data['hlines'].extend([lvl['level'] for lvl in key_levels])
        for lvl in key_levels:
            if 'H' in lvl['level_type']: hlines_data['colors'].append('red')
            elif 'L' in lvl['level_type']: hlines_data['colors'].append('green')
            else: hlines_data['colors'].append('blue')

    if current_price:
        hlines_data['hlines'].append(current_price)
        hlines_data['colors'].append('orange')

    mc = mpf.make_marketcolors(up='#26a69a', down='#ef5350', wick={'up':'green', 'down':'red'}, volume='inherit')
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=':', base_mpf_style='charles')

    buf = io.BytesIO()
    
    mpf.plot(
        df,
        type='candle',
        style=style,
        title=f'\n{symbol} - 1-Minute Chart',
        ylabel='Price (USDT)',
        volume=True,
        hlines=hlines_data,
        savefig=dict(fname=buf, dpi=120),
        figsize=(15, 8)
    )
    
    buf.seek(0)
    return buf