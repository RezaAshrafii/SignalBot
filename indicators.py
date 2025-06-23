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