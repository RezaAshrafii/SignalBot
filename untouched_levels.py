# untouched_levels.py
import pandas as pd
from volume_profile import calc_daily_volume_profile

def find_untouched_levels(df, date_col='ny_date', lookback_days=7):
    """
    سطوح کلیدی را بر اساس تاریخچه داده شده، شناسایی می‌کند.
    """
    levels = []
    if df.empty or len(df.groupby(date_col)) < 1:
        return levels

    daily_groups = df.groupby(date_col)
    all_dates = sorted(list(daily_groups.groups.keys()))
    relevant_dates = all_dates[-lookback_days:]
    last_day_date = all_dates[-1]
    
    for lvl_date in relevant_dates:
        daily_df = daily_groups.get_group(lvl_date)
        
        pdl = daily_df['low'].min()
        pdh = daily_df['high'].max()
        # --- [اصلاح شد] --- فراخوانی تابع بدون پارامتر اضافی bin_size
        profile = calc_daily_volume_profile(daily_df)
        poc = profile.get('poc')
        vah = profile.get('vah')
        val = profile.get('val')

        potential_levels = {'PDL': pdl, 'PDH': pdh, 'POC': poc, 'VAH': vah, 'VAL': val}
        
        data_after = df[df[date_col] > lvl_date]
        
        for level_type, level_price in potential_levels.items():
            if not level_price: continue
            
            if lvl_date == last_day_date:
                levels.append({'date': lvl_date, 'level': level_price, 'level_type': level_type})
                continue

            is_touched = False
            if not data_after.empty:
                for _, future_candle in data_after.iterrows():
                    if future_candle['low'] <= level_price <= future_candle['high']:
                        is_touched = True
                        break
            
            if not is_touched:
                levels.append({'date': lvl_date, 'level': level_price, 'level_type': level_type})
                
    if not levels: return []
    final_levels = pd.DataFrame(levels).drop_duplicates(subset=['level']).to_dict('records')
    return sorted(final_levels, key=lambda x: x['level'])