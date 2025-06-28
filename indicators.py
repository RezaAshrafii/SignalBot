# posmanagerfunc/indicators.py
import pandas as pd
import numpy as np

def calculate_atr(klines_df, period=14):
    """
    اندیکاتور ATR را بر اساس DataFrame کندل‌ها محاسبه می‌کند.
    """
    if klines_df.empty or len(klines_df) < period:
        return 0

    df = klines_df.copy()
    # اطمینان از اینکه داده‌ها عددی هستند
    high = pd.to_numeric(df['high'])
    low = pd.to_numeric(df['low'])
    close = pd.to_numeric(df['close'])

    # محاسبه True Range
    df['tr0'] = abs(high - low)
    df['tr1'] = abs(high - close.shift())
    df['tr2'] = abs(low - close.shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    
    # محاسبه ATR
    df['atr'] = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    
    return df['atr'].iloc[-1]

def calculate_atr(klines_df, period=14):
    if not isinstance(klines_df, pd.DataFrame) or klines_df.empty or len(klines_df) < period:
        return 0
    df = klines_df.copy()
    high, low, close = pd.to_numeric(df['high']), pd.to_numeric(df['low']), pd.to_numeric(df['close'])
    df['tr0'] = abs(high - low)
    df['tr1'] = abs(high - close.shift())
    df['tr2'] = abs(low - close.shift())
    df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    atr = df['tr'].ewm(alpha=1/period, adjust=False).mean()
    return atr.iloc[-1]

def calculate_session_indicators(df):
    """
    VWAP روزانه، باندهای انحراف معیار و دلتا را محاسبه می‌کند.
    این تابع باید روی دیتای روزانه (از ابتدای روز معاملاتی) اجرا شود.
    """
    if df.empty:
        return {'vwap': 0, 'vwap_upper': 0, 'vwap_lower': 0, 'delta': 0, 'cumulative_delta': 0}

    # اطمینان از اینکه ستون‌ها عددی هستند
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    df['close'] = pd.to_numeric(df['close'])
    df['volume'] = pd.to_numeric(df['volume'])
    df['taker_buy_base_asset_volume'] = pd.to_numeric(df['taker_buy_base_asset_volume'])

    # محاسبه VWAP
    tp = (df['high'] + df['low'] + df['close']) / 3
    cum_vol = df['volume'].cumsum()
    cum_tp_vol = (tp * df['volume']).cumsum()
    
    # جلوگیری از تقسیم بر صفر
    vwap_series = cum_tp_vol / cum_vol.replace(0, np.nan)
    df['vwap'] = vwap_series

    # محاسبه انحراف معیار VWAP
    sq_dev = ((tp - df['vwap'])**2 * df['volume']).cumsum()
    variance = sq_dev / cum_vol.replace(0, np.nan)
    std_dev_series = np.sqrt(variance)
    
    # محاسبه باندهای بالا و پایین (با ضریب ۲)
    df['vwap_upper'] = df['vwap'] + (std_dev_series * 2)
    df['vwap_lower'] = df['vwap'] - (std_dev_series * 2)

    # محاسبه Delta
    sell_volume = df['volume'] - df['taker_buy_base_asset_volume']
    df['delta'] = df['taker_buy_base_asset_volume'] - sell_volume
    df['cumulative_delta'] = df['delta'].cumsum()

    # بازگرداندن آخرین مقادیر محاسبه شده
    last_values = df.iloc[-1]
    return {
        'vwap': last_values['vwap'],
        'vwap_upper': last_values['vwap_upper'],
        'vwap_lower': last_values['vwap_lower'],
        'delta': last_values['delta'],
        'cumulative_delta': last_values['cumulative_delta'],
        'price_window': df['close'].tail(14).tolist(), # برای ستاپ رگرسیون
        'delta_window': df['delta'].tail(14).tolist()  # برای ستاپ رگرسیون
    }