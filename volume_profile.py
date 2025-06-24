# volume_profile.py
import pandas as pd

def calc_daily_volume_profile(daily_df):
    """
    پروفایل حجمی روزانه (POC, VAH, VAL) را محاسبه می‌کند.
    """
    if daily_df.empty:
        return {'poc': 0, 'vah': 0, 'val': 0}

    # استفاده از observed=True برای رفع هشدار و سازگاری با آینده
    price_volume = daily_df.groupby(pd.cut(daily_df['close'], bins=100), observed=True)['volume'].sum()
    
    if price_volume.empty:
        return {'poc': 0, 'vah': 0, 'val': 0}

    poc_level = price_volume.idxmax()
    poc_price = poc_level.mid
    
    sorted_volume = price_volume.sort_values(ascending=False)
    
    total_volume = daily_df['volume'].sum()
    value_area_limit = total_volume * 0.70
    
    cumulative_volume = 0
    value_area_levels = []
    
    for level, volume in sorted_volume.items():
        if cumulative_volume >= value_area_limit:
            break
        cumulative_volume += volume
        value_area_levels.append(level.mid)
        
    if not value_area_levels:
        return {'poc': poc_price, 'vah': poc_price, 'val': poc_price}
        
    vah = max(value_area_levels)
    val = min(value_area_levels)
    
    return {'poc': poc_price, 'vah': vah, 'val': val}