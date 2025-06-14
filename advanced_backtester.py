# advanced_backtester.py
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from collections import deque
from dateutil import tz

# ==============================================================================
# بخش ۱: توابع اصلی و پایه‌ای (بدون تغییر)
# ==============================================================================

def fetch_futures_klines(symbol, interval, start_time, end_time):
    url = 'https://fapi.binance.com/fapi/v1/klines'; limit = 1500; klines = []
    start_time_ms, end_time_ms = int(start_time.timestamp() * 1000), int(end_time.timestamp() * 1000)
    print(f"Fetching data for {symbol} ({interval}) from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}...")
    while start_time_ms < end_time_ms:
        params = {'symbol': symbol, 'interval': interval, 'startTime': start_time_ms, 'limit': limit}
        try:
            data = requests.get(url, params=params).json()
            if not data or not isinstance(data, list) or len(data) == 0: break
            klines.extend(data); start_time_ms = data[-1][0] + 1
        except Exception as e: print(f"Error fetching data: {e}"); break
    if not klines: return pd.DataFrame()
    columns = ['open_time','open','high','low','close','volume','close_time','quote_asset_volume','num_trades','taker_buy_base_asset_volume','taker_buy_quote_asset_volume','ignore']
    df = pd.DataFrame(klines, columns=columns)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms', utc=True)
    numeric_cols = ['open','high','low','close','volume','taker_buy_base_asset_volume']
    for col in numeric_cols: df[col] = pd.to_numeric(df[col], errors='coerce')
    df.dropna(subset=numeric_cols, inplace=True)
    return df

def calc_daily_volume_profile(df, bin_size=0.5):
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
    total_volume = bin_volumes.sum(); va_vol_target = total_volume * 0.68
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

def find_levels_from_specific_date(df, target_date_obj, date_col='ny_date', bin_size=0.5):
    key_levels = []
    if date_col not in df.columns: raise ValueError(f"Date column '{date_col}' not found.")
    target_date = target_date_obj.date()
    group = df[df[date_col] == target_date]
    if not group.empty:
        vp = calc_daily_volume_profile(group, bin_size=bin_size)
        if vp:
            for level_type in ['VAH', 'VAL', 'HIGH', 'LOW', 'POC']:
                key_levels.append({'level_type': level_type, 'level': vp[level_type], 'date': target_date})
    return key_levels
    
def determine_composite_trend(df):
    daily_data = df.groupby(pd.Grouper(key='open_time', freq='D')).agg(high=('high', 'max'), low=('low', 'min'), taker_buy_volume=('taker_buy_base_asset_volume', 'sum'), total_volume=('volume', 'sum')).dropna()
    if len(daily_data) < 3: return "INSUFFICIENT_DATA"
    last_3_days = daily_data.tail(3); highs, lows = last_3_days['high'].tolist(), last_3_days['low'].tolist()
    trend_score = 0
    for i in range(1, len(highs)):
        if highs[i] > highs[i-1]: trend_score += 1
        if lows[i] > lows[i-1]: trend_score += 1
        if highs[i] < highs[i-1]: trend_score -= 1
        if lows[i] < lows[i-1]: trend_score -= 1
    price_trend = "SIDEWAYS";
    if trend_score > 0: price_trend = "UP"
    elif trend_score < 0: price_trend = "DOWN"
    daily_data['delta'] = 2 * daily_data['taker_buy_volume'] - daily_data['total_volume']
    last_day_delta = daily_data['delta'].iloc[-1]; cvd_trend = "SIDEWAYS"
    if last_day_delta > 0: cvd_trend = "UP"
    elif last_day_delta < 0: cvd_trend = "DOWN"
    if price_trend == "UP" and cvd_trend == "UP": return "STRONG_UP"
    elif price_trend == "DOWN" and cvd_trend == "DOWN": return "STRONG_DOWN"
    else: return "SIDEWAYS"

# ==============================================================================
# بخش ۲: منطق جدید برای ستاپ پیشرفته
# ==============================================================================

class AdvancedSetupLogic:
    def __init__(self, key_levels):
        self.key_levels = key_levels
        self.pending_setups = []

    def process_candle_30m(self, candle_30m, recent_candles_30m):
        """هر کندل ۳۰ دقیقه‌ای را برای یافتن ناحیه معاملاتی خرید یا فروش بررسی می‌کند."""
        self._check_for_break(candle_30m)
        self._check_for_fvg(recent_candles_30m)
        return self._check_for_pullback(candle_30m)

    def _check_for_break(self, candle):
        """بررسی می‌کند آیا یک سطح کلیدی شکسته شده است (حمایت یا مقاومت)."""
        for level in self.key_levels:
            # جلوگیری از اضافه شدن سناریوی تکراری
            if any(s['broken_level']['level'] == level['level'] for s in self.pending_setups):
                continue
            
            # شکست حمایت (Breakdown)
            if level['level_type'] in ['VAL', 'LOW', 'POC'] and candle['high'] > level['level'] and candle['close'] < level['level']:
                self.pending_setups.append({'direction': 'Sell', 'status': 'break_detected', 'broken_level': level, 'fvg_zone': None})
            
            # شکست مقاومت (Breakout)
            if level['level_type'] in ['VAH', 'HIGH', 'POC'] and candle['low'] < level['level'] and candle['close'] > level['level']:
                self.pending_setups.append({'direction': 'Buy', 'status': 'break_detected', 'broken_level': level, 'fvg_zone': None})

    def _check_for_fvg(self, recent_candles):
        """پس از شکست، به دنبال FVG هم‌جهت می‌گردد."""
        if len(recent_candles) < 3: return
        c1, c2, c3 = recent_candles[-3], recent_candles[-2], recent_candles[-1]

        for setup in self.pending_setups:
            if setup['status'] == 'break_detected' and not setup['fvg_zone']:
                # برای ستاپ فروش، دنبال FVG نزولی بگرد
                if setup['direction'] == 'Sell' and c1['low'] > c3['high']:
                    fvg_zone = {'low': c3['high'], 'high': c1['low']}
                    if abs(fvg_zone['high'] - setup['broken_level']['level']) < (setup['broken_level']['level'] * 0.005):
                        setup.update({'fvg_zone': fvg_zone, 'status': 'fvg_found'})
                
                # برای ستاپ خرید، دنبال FVG صعودی بگرد
                elif setup['direction'] == 'Buy' and c3['low'] > c1['high']:
                    fvg_zone = {'low': c1['high'], 'high': c3['low']}
                    if abs(fvg_zone['low'] - setup['broken_level']['level']) < (setup['broken_level']['level'] * 0.005):
                        setup.update({'fvg_zone': fvg_zone, 'status': 'fvg_found'})

    def _check_for_pullback(self, candle):
        """بررسی می‌کند که آیا قیمت به ناحیه همگرایی پولبک زده و ضعف نشان داده است."""
        for setup in self.pending_setups:
            if setup['status'] == 'fvg_found':
                fvg, level = setup['fvg_zone'], setup['broken_level']
                
                # بررسی پولبک برای ستاپ فروش
                if setup['direction'] == 'Sell' and candle['high'] >= fvg['low']:
                    delta = (2 * candle.get('taker_buy_base_asset_volume', 0)) - candle['volume']
                    if delta < (candle['volume'] * 0.1): # تایید ضعف خریداران
                        setup['status'] = 'completed'
                        return setup

                # بررسی پولبک برای ستاپ خرید
                if setup['direction'] == 'Buy' and candle['low'] <= fvg['high']:
                    delta = (2 * candle.get('taker_buy_base_asset_volume', 0)) - candle['volume']
                    if delta > (candle['volume'] * -0.1): # تایید ضعف فروشندگان (دلتا نباید خیلی منفی باشد)
                        setup['status'] = 'completed'
                        return setup
        return None

def find_ltf_entry_and_sl(one_minute_df, htf_candle_time, direction, lookback_minutes=30):
    """در تایم فریم ۱ دقیقه به دنبال نقطه ورود دقیق و حد ضرر می‌گردد."""
    entry_window_start = htf_candle_time + timedelta(minutes=30)
    entry_window_end = entry_window_start + timedelta(minutes=lookback_minutes)
    entry_df = one_minute_df[(one_minute_df['open_time'] >= entry_window_start) & (one_minute_df['open_time'] < entry_window_end)]
    if entry_df.empty: return None

    if direction == 'Sell':
        swing_high = entry_df['high'].max()
        stop_loss = swing_high * 1.0005
        for i in range(1, len(entry_df)):
            if entry_df['close'].iloc[i] < entry_df['low'].iloc[i-1]: # Market Structure Shift
                return {'entry_time': entry_df['open_time'].iloc[i], 'entry_price': entry_df['close'].iloc[i], 'stop_loss': stop_loss}
    
    if direction == 'Buy':
        swing_low = entry_df['low'].min()
        stop_loss = swing_low * 0.9995
        for i in range(1, len(entry_df)):
            if entry_df['close'].iloc[i] > entry_df['high'].iloc[i-1]: # Market Structure Shift
                return {'entry_time': entry_df['open_time'].iloc[i], 'entry_price': entry_df['close'].iloc[i], 'stop_loss': stop_loss}
    return None

# ==============================================================================
# بخش ۳: اجرای اصلی بک‌تست
# ==============================================================================
if __name__ == "__main__":
    # ۱. تنظیمات
    SYMBOL, TIMEFRAME = 'BTCUSDT', '30m'
    ANALYSIS_DATE_STR, LEVELS_FROM_DATE_STR = '2025-06-09', '2025-06-08'
    
    # ۲. آماده‌سازی داده‌ها و کانتکست
    print("Step 1: Preparing data and context...")
    analysis_date_obj = datetime.strptime(ANALYSIS_DATE_STR, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    
    print("\nStep 2: Determining the trend for the analysis day...")
    trend_hist_df = fetch_futures_klines(SYMBOL, '1m', analysis_date_obj - timedelta(days=4), analysis_date_obj)
    daily_trend = "SIDEWAYS"
    if not trend_hist_df.empty:
        daily_trend = determine_composite_trend(trend_hist_df)
    print(f"--> The determined trend for {ANALYSIS_DATE_STR} is: {daily_trend}")

    print(f"\nStep 3: Identifying key levels from {LEVELS_FROM_DATE_STR}...")
    levels_date_obj = datetime.strptime(LEVELS_FROM_DATE_STR, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    levels_hist_df = fetch_futures_klines(SYMBOL, '1m', levels_date_obj - timedelta(days=2), levels_date_obj + timedelta(days=1))
    key_levels = []
    if not levels_hist_df.empty:
        levels_hist_df['ny_date'] = (levels_hist_df['open_time'] - pd.Timedelta(hours=4)).dt.date
        key_levels = find_levels_from_specific_date(levels_hist_df, levels_date_obj, date_col='ny_date')
        print("--- Monitoring The Following Key Levels ---"); [print(f"  - {lvl['level_type']} at {lvl['level']:,.2f}") for lvl in key_levels]
    
    # ۳. اجرای حلقه بک‌تست
    print(f"\nStep 4: Starting multi-timeframe backtest for {ANALYSIS_DATE_STR}...")
    
    df_htf = fetch_futures_klines(SYMBOL, TIMEFRAME, analysis_date_obj, analysis_date_obj + timedelta(days=1))
    df_ltf = fetch_futures_klines(SYMBOL, '1m', analysis_date_obj, analysis_date_obj + timedelta(days=1))
    
    if not df_htf.empty and not df_ltf.empty and key_levels:
        setup_handler = AdvancedSetupLogic(key_levels)
        recent_candles_30m = deque(maxlen=5)
        
        for index, row in df_htf.iterrows():
            current_candle_30m = row.to_dict()
            recent_candles_30m.append(current_candle_30m)
            
            htf_setup = setup_handler.process_candle_30m(current_candle_30m, recent_candles_30m)
            
            if htf_setup:
                htf_candle_time = row['open_time']
                direction = htf_setup['direction']
                
                print(f"\n--- HTF Setup Confirmed at {htf_candle_time.strftime('%H:%M')} UTC ---")
                print(f"Searching for {direction} entry on 1m chart...")
                
                entry_details = find_ltf_entry_and_sl(df_ltf, htf_candle_time, direction)
                
                if entry_details:
                    is_buy = direction == 'Buy'; is_sell = direction == 'Sell'
                    trend_is_up = "UP" in daily_trend; trend_is_down = "DOWN" in daily_trend
                    
                    if (is_buy and trend_is_up) or (is_sell and trend_is_down):
                        print("\n" + "="*50)
                        print("🔥🔥 **TREND-CONFIRMED TRADE SIGNAL GENERATED** 🔥🔥")
                        print(f"  -> Setup Type:           {direction} (Breakdown/out-FVG-Retest)")
                        print(f"  -> HTF Signal Time ({TIMEFRAME}): {htf_candle_time.strftime('%Y-%m-%d %H:%M')} UTC")
                        print(f"  -> LTF Entry Time (1m):   {entry_details['entry_time'].strftime('%Y-%m-%d %H:%M')} UTC")
                        print(f"  -> Suggested Entry Price:  ${entry_details['entry_price']:,.2f}")
                        print(f"  -> Suggested Stop-Loss:   ${entry_details['stop_loss']:,.2f}")
                        print("="*50)
                    else:
                        print("  -> A setup was found, but it's against the determined daily trend. Signal ignored.")
                else:
                    print("  -> No optimal 1m entry setup found within the defined window.")

        print("\n--- Backtest Finished ---")