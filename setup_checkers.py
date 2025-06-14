# setup_checkers.py
def check_long_tail(candle, level_data):
    level_price, level_type = level_data['level'], level_data['level_type']
    o, h, l, c = candle['open'], candle['high'], candle['low'], candle['close']
    total_range = h - l;
    if total_range == 0: return None
    upper_shadow, lower_shadow = h - max(o, c), min(o, c) - l
    if upper_shadow > total_range * 0.6 and c < o and level_type in ['HIGH', 'VAH']:
        return f"فروش (Long Tail) در مقاومت {level_type}"
    if lower_shadow > total_range * 0.6 and c > o and level_type in ['LOW', 'VAL']:
        return f"خرید (Long Tail) در حمایت {level_type}"
    return None

def check_absorption(candle, avg_volume, level_data):
    o, c = candle['open'], candle['close']
    if candle['volume'] < (avg_volume * 2.0): return None
    total_range = candle['high'] - candle['low']
    if total_range == 0 or (abs(c - o) / total_range) > 0.4: return None
    delta = (2 * candle.get('taker_buy_base_asset_volume', 0)) - candle['volume']
    level_price, level_type = level_data['level'], level_data['level_type']
    if level_type in ['HIGH', 'VAH'] and delta > 0:
        return f"فروش (Absorption) در مقاومت {level_type}"
    if level_type in ['LOW', 'VAL'] and delta < 0:
        return f"خرید (Absorption) در حمایت {level_type}"
    return None