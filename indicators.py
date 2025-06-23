
def calculate_atr(klines_df, period=14):
    """
    اندیکاتور ATR را بر اساس DataFrame کندل‌ها محاسبه می‌کند.
    """
    if klines_df.empty or len(klines_df) < period:
        return 0

    # اطمینان از اینکه داده‌ها عددی هستند
    high = pd.to_numeric(klines_df['high'])
    low = pd.to_numeric(klines_df['low'])
    close = pd.to_numeric(klines_df['close'])

    # محاسبه True Range
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # محاسبه ATR
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    return atr.iloc[-1]