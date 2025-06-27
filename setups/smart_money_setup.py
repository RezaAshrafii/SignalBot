# setups/smart_money_setup.py

import pandas as pd
import numpy as np
from collections import deque
from scipy.stats import linregress
from scipy.signal import find_peaks
from datetime import datetime, timezone
from .base_setup import BaseSetup

class SmartMoneySetup(BaseSetup):
    """
    ستاپ جامع مبتنی بر مفاهیم Smart Money و تحلیل روند چندزمانی.
    این ستاپ به دنبال نواحی POI (Point of Interest) می‌گردد که از ترکیب
    Liquidity Sweep, BOS و Order Block ایجاد شده و سپس منتظر تاییدیه
    در جهت روند اصلی بازار برای ورود به معامله می‌ماند.
    """
    def __init__(self, state_manager, config=None):
        default_config = {
            'swing_lookback_5m': 5,      # فاصله برای تشخیص سوینگ در تایم ۵ دقیقه
            'swing_lookback_15m': 3,     # فاصله برای تشخیص سوینگ در تایم ۱۵ دقیقه (برای حد سود)
            'min_rr_ratio': 1.0,         # حداقل نسبت ریسک به ریوارد برای ورود
            'history_candles_needed': 300 # حداقل تعداد کندل ۱ دقیقه برای شروع تحلیل
        }
        super().__init__(state_manager, config or default_config)
        self.name = "SmartMoneySetup"
        
        # مدیریت وضعیت داخلی ستاپ برای هر ارز
        self.points_of_interest = {}
        self.last_5m_timestamp = {}

    # ==========================================================================
    # بخش اول: توابع تحلیلی (برگرفته از اسکریپت شما)
    # ==========================================================================

    def _calculate_ichimoku(self, df):
        nine_period_high = df['high'].rolling(window=9).max()
        nine_period_low = df['low'].rolling(window=9).min()
        df['tenkan_sen'] = (nine_period_high + nine_period_low) / 2
        twenty_six_period_high = df['high'].rolling(window=26).max()
        twenty_six_period_low = df['low'].rolling(window=26).min()
        df['kijun_sen'] = (twenty_six_period_high + twenty_six_period_low) / 2
        df['senkou_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(26)
        fifty_two_period_high = df['high'].rolling(window=52).max()
        fifty_two_period_low = df['low'].rolling(window=52).min()
        df['senkou_b'] = ((fifty_two_period_high + fifty_two_period_low) / 2).shift(26)
        return df

    def _get_ichimoku_score(self, df_4h, last_price):
        if df_4h.empty or len(df_4h) < 52: return 0
        df_4h = self._calculate_ichimoku(df_4h.copy())
        last_kumo = df_4h.iloc[-1]
        if pd.isna(last_kumo['senkou_a']) or pd.isna(last_kumo['senkou_b']): return 0
        if last_price > last_kumo['senkou_a'] and last_price > last_kumo['senkou_b']: return 1
        if last_price < last_kumo['senkou_a'] and last_price < last_kumo['senkou_b']: return -1
        return 0

    def _get_linreg_score(self, df_4h, period=100):
        if df_4h.empty or len(df_4h) < period: return 0
        # Use tail to avoid issues with NaNs at the beginning
        data_to_regress = df_4h.tail(period)['close'].dropna()
        if len(data_to_regress) < period: return 0
        slope, _, _, _, _ = linregress(x=np.arange(len(data_to_regress)), y=data_to_regress)
        normalized_slope = slope / data_to_regress.mean()
        if normalized_slope > 0.0002: return 1
        if normalized_slope < -0.0002: return -1
        return 0

    def _get_daily_pa_cvd_score(self, historical_daily_df, intraday_df):
        pa_score = 0
        if len(historical_daily_df) >= 3:
            day_2, day_3 = historical_daily_df.iloc[-2], historical_daily_df.iloc[-1]
            if day_3['high'] > day_2['high'] and day_3['low'] > day_2['low']: pa_score = 2
            elif day_3['high'] < day_2['high'] and day_3['low'] < day_2['low']: pa_score = -2
        
        cvd_score = 0
        if not intraday_df.empty and 'taker_buy_base_asset_volume' in intraday_df.columns:
            delta = 2 * intraday_df['taker_buy_base_asset_volume'].sum() - intraday_df['volume'].sum()
            if delta > 0: cvd_score = 1
            elif delta < 0: cvd_score = -1
        return pa_score + cvd_score

    def _analyze_master_trend(self, df_1m, last_price):
        # Resample data for different timeframes
        df_4h = df_1m.resample('4H').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        df_daily = df_1m.resample('D').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'taker_buy_base_asset_volume': 'sum', 'volume': 'sum'}).dropna()
        
        # Split daily data for PA/CVD analysis
        historical_daily_df = df_daily.iloc[:-1]
        intraday_df = df_1m[df_1m.index.date == df_1m.index.date[-1]]

        ichimoku_score = self._get_ichimoku_score(df_4h, last_price)
        linreg_score = self._get_linreg_score(df_4h)
        pa_cvd_score = self._get_daily_pa_cvd_score(historical_daily_df, intraday_df)
        
        total_score = (ichimoku_score * 1.5) + (linreg_score * 1.5) + (pa_cvd_score * 1.0)
        
        if total_score >= 2: return "Bullish"
        if total_score <= -2: return "Bearish"
        return "SIDEWAYS"

    def _find_swing_points(self, df, distance):
        high_peaks, _ = find_peaks(df['high'], distance=distance)
        df['is_swing_high'] = False
        df.iloc[high_peaks, df.columns.get_loc('is_swing_high')] = True
        low_peaks, _ = find_peaks(-df['low'], distance=distance)
        df['is_swing_low'] = False
        df.iloc[low_peaks, df.columns.get_loc('is_swing_low')] = True
        return df

    def _find_poi_with_or_logic(self, df_htf):
        points_of_interest = []
        check_ob = lambda c1, c2: ('Bullish', 'OB') if c2['close'] > c1['high'] and c1['open'] > c1['close'] else (('Bearish', 'OB') if c2['close'] < c1['low'] and c1['open'] < c1['close'] else (None, None))
        for i in range(1, len(df_htf)):
            current_candle = df_htf.iloc[i]
            past_swings = df_htf.iloc[:i][df_htf.iloc[:i]['is_swing_high'] | df_htf.iloc[:i]['is_swing_low']]
            if past_swings.empty: continue
            last_sw_high_val = past_swings[past_swings['is_swing_high']]['high'].iloc[-1] if not past_swings[past_swings['is_swing_high']].empty else None
            last_sw_low_val = past_swings[past_swings['is_swing_low']]['low'].iloc[-1] if not past_swings[past_swings['is_swing_low']].empty else None
            sweep_dir, sweep_type = (('Bearish', 'Liquidity Sweep') if last_sw_high_val and current_candle['high'] > last_sw_high_val and current_candle['close'] < last_sw_high_val else
                                     (('Bullish', 'Liquidity Sweep') if last_sw_low_val and current_candle['low'] < last_sw_low_val and current_candle['close'] > last_sw_low_val else (None, None)))
            if not sweep_dir: continue
            bos_dir, bos_type = (('Bullish', 'BOS') if last_sw_high_val and current_candle['close'] > last_sw_high_val else 
                                 (('Bearish', 'BOS') if last_sw_low_val and current_candle['close'] < last_sw_low_val else (None, None)))
            ob_dir, ob_type = check_ob(df_htf.iloc[i-1], current_candle)
            reasons = {sweep_type}
            if sweep_dir == bos_dir: reasons.add(bos_type)
            if sweep_dir == ob_dir: reasons.add(ob_type)
            if len(reasons) > 1:
                poi = {
                    'type': f"POI 5m: {' + '.join(sorted(list(reasons)))}",
                    'entry_price': current_candle['high'] if sweep_dir == 'Bullish' else current_candle['low'],
                    'stop_loss': current_candle['low'] if sweep_dir == 'Bullish' else current_candle['high'],
                    'discovery_time': current_candle.name, 'direction': sweep_dir
                }
                points_of_interest.append(poi)
        return points_of_interest

    def _get_dynamic_take_profit(self, df_15m, entry_time, direction):
        past_swings = df_15m[df_15m.index < entry_time]
        if direction == 'Bullish':
            swing_highs = past_swings[past_swings['is_swing_high']]
            if not swing_highs.empty: return swing_highs.iloc[-1]['high']
        elif direction == 'Bearish':
            swing_lows = past_swings[past_swings['is_swing_low']]
            if not swing_lows.empty: return swing_lows.iloc[-1]['low']
        return None

    def _get_trading_session(self, utc_hour):
        if 1 <= utc_hour < 8: return "Asian Session"
        elif 8 <= utc_hour < 16: return "London Session"
        elif 16 <= utc_hour < 23: return "New York Session"
        else: return "After Hours"

    # ==========================================================================
    # بخش دوم: متد اصلی برای اجرا در ربات زنده
    # ==========================================================================
    def check(self, symbol: str, kline_history: deque, kline_1m: dict, **kwargs):
        if len(kline_history) < self.config['history_candles_needed']:
            return None

        # --- ۱. آماده‌سازی داده‌ها و وضعیت ---
        if symbol not in self.points_of_interest: self.points_of_interest[symbol] = []
        if symbol not in self.last_5m_timestamp: self.last_5m_timestamp[symbol] = None
        
        df_1m_full = pd.DataFrame(list(kline_history))
        # Add the latest kline data needed for CVD calculation
        df_1m_full['taker_buy_base_asset_volume'] = [k.get('taker_buy_base_asset_volume', 0) for k in kline_history]
        df_1m_full['timestamp'] = pd.to_datetime(df_1m_full['open_time'])
        df_1m_full.set_index('timestamp', inplace=True)

        # --- ۲. آپدیت نواحی POI با هر کندل جدید ۵ دقیقه‌ای ---
        current_minute = kline_1m['open_time'].minute
        if current_minute % 5 == 0 and kline_1m['open_time'] != self.last_5m_timestamp.get(symbol):
            self.last_5m_timestamp[symbol] = kline_1m['open_time']
            df_5m = df_1m_full.resample('5min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
            df_5m_swings = self._find_swing_points(df_5m.copy(), distance=self.config['swing_lookback_5m'])
            new_pois = self._find_poi_with_or_logic(df_5m_swings)
            for poi in new_pois:
                if not any(p['discovery_time'] == poi['discovery_time'] for p in self.points_of_interest[symbol]):
                    self.points_of_interest[symbol].append(poi)
                    print(f"✅ [{self.name}][{symbol}] New POI detected at {poi['entry_price']:.2f} ({poi['direction']})")

        # --- ۳. بررسی برخورد و تاییدیه برای ورود به معامله ---
        for poi in list(self.points_of_interest[symbol]):
            if poi['discovery_time'] >= kline_1m['open_time']: continue
            
            is_touched = (poi['direction'] == 'Bullish' and kline_1m['low'] <= poi['entry_price']) or \
                         (poi['direction'] == 'Bearish' and kline_1m['high'] >= poi['entry_price'])
            if not is_touched: continue

            # پس از برخورد، ناحیه از لیست حذف می‌شود تا فقط یک بار سیگنال بدهد
            self.points_of_interest[symbol].remove(poi)

            is_bullish_conf = poi['direction'] == 'Bullish' and kline_1m['close'] > kline_1m['open']
            is_bearish_conf = poi['direction'] == 'Bearish' and kline_1m['close'] < kline_1m['open']
            if not (is_bullish_conf or is_bearish_conf): continue
            
            # --- ۴. بررسی‌های نهایی: همسویی با روند و ریسک به ریوارد ---
            master_trend = self._analyze_master_trend(df_1m_full, kline_1m['close'])
            if (poi['direction'] == 'Bullish' and master_trend != 'Bullish') or \
               (poi['direction'] == 'Bearish' and master_trend != 'Bearish'):
                print(f"❌ [{self.name}][{symbol}] Signal ignored. POI direction ({poi['direction']}) misaligned with Master Trend ({master_trend}).")
                continue

            df_15m = df_1m_full.resample('15min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
            df_15m_swings = self._find_swing_points(df_15m.copy(), distance=self.config['swing_lookback_15m'])
            take_profit = self._get_dynamic_take_profit(df_15m_swings, kline_1m['open_time'], poi['direction'])
            if take_profit is None: continue
            
            entry_price = kline_1m['close']
            stop_loss = poi['stop_loss']
            risk_points = abs(entry_price - stop_loss)
            reward_points = abs(take_profit - entry_price)
            if risk_points == 0 or (reward_points / risk_points) < self.config['min_rr_ratio']: continue
            
            # --- ۵. ساخت و ارسال پکیج سیگنال استاندارد ---
            print(f"🚀 [{self.name}][{symbol}] Signal Confirmed! Entering {poi['direction']} trade.")
            
            # آماده‌سازی دلایل برای نوتیفیکیشن تلگرام
            reasons = [
                f"✅ ستاپ: **{poi['type']}**",
                f"✅ همسو با روند اصلی بازار: **{master_trend}**",
                f"✅ R/R: **{reward_points / risk_points:.2f}**"
            ]

            return {
                "direction": poi['direction'],
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit, # حد سود داینامیک اضافه شد
                "setup": poi['type'],
                "reasons": reasons,
                "session": self._get_trading_session(kline_1m['open_time'].hour)
            }
        return None