# volume_profile.py
import numpy as np
import pandas as pd

def calc_daily_volume_profile(df, bin_size=0.5, value_area_percent=0.68):
    df = df.copy(); day_low, day_high = df['low'].min(), df['high'].max()
    if pd.isna(day_low): return {}
    min_p, max_p = np.floor(day_low / bin_size) * bin_size, np.ceil(day_high / bin_size) * bin_size
    if min_p == max_p: max_p += bin_size
    price_bins = np.arange(min_p, max_p, bin_size); bin_volumes = np.zeros_like(price_bins, dtype=float)
    for _, row in df.iterrows():
        cl, ch, cv = row['low'], row['high'], row['volume']
        if cv == 0 or ch <= cl: continue
        start_idx, end_idx = np.searchsorted(price_bins, [cl, ch])
        if start_idx >= end_idx:
            if start_idx > 0 and start_idx < len(bin_volumes): bin_volumes[start_idx-1] += cv
            continue
        volume_per_bin = cv / (end_idx - start_idx)
        bin_volumes[start_idx:end_idx] += volume_per_bin
    if bin_volumes.sum() == 0: return {}
    poc_idx = np.argmax(bin_volumes); poc = price_bins[poc_idx] + bin_size / 2
    total_volume = bin_volumes.sum(); va_vol_target = total_volume * value_area_percent
    inc_vol = bin_volumes[poc_idx]; up_idx, down_idx = poc_idx + 1, poc_idx - 1
    while inc_vol < va_vol_target:
        at_top, at_bottom = up_idx >= len(bin_volumes), down_idx < 0
        if at_top and at_bottom: break
        up_vol = bin_volumes[up_idx] if not at_top else -1; down_vol = bin_volumes[down_idx] if not at_bottom else -1
        if up_vol >= down_vol:
            if not at_top: inc_vol += up_vol; up_idx += 1
        else:
            if not at_bottom: inc_vol += down_vol; down_idx -= 1
    val = price_bins[down_idx + 1] + bin_size / 2 if (down_idx + 1) < len(price_bins) else price_bins[0]
    vah = price_bins[up_idx - 1] + bin_size / 2 if (up_idx - 1) >= 0 else price_bins[-1]
    return {'VAH': vah, 'VAL': val, 'POC': poc, 'HIGH': day_high, 'LOW': day_low}