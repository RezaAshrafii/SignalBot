# untouched_levels.py
from volume_profile import calc_daily_volume_profile

def find_untouched_levels(df, date_col='ny_date', bin_size=0.5):
    key_levels = []
    if date_col not in df.columns: raise ValueError(f"Date column '{date_col}' not found.")
    dates = sorted(df[date_col].unique())
    for d in dates[:-1]:
        group = df[df[date_col] == d]
        if group.empty: continue
        vp = calc_daily_volume_profile(group, bin_size=bin_size)
        if vp:
            for level_type in ['VAH', 'VAL', 'HIGH', 'LOW', 'POC']:
                key_levels.append({'level_type': level_type, 'level': vp[level_type], 'date': d})
    untouched_levels = []
    for lvl in key_levels:
        lvl_date = lvl['date']
        data_after = df[df['open_time'].dt.date > lvl_date]
        if not ((data_after['high'] >= lvl['level']) & (data_after['low'] <= lvl['level'])).any():
            untouched_levels.append(lvl)
    return untouched_levels