# setups/liq_sweep_setup.py

import pandas as pd
from collections import deque
from .base_setup import BaseSetup

class LiqSweepSetup(BaseSetup):
    """
    این کلاس، استراتژی مبتنی بر جمع‌آوری نقدینگی (Liquidity Sweep) و
    تاییدیه کندلی را برای ورود به معامله پیاده‌سازی می‌کند.
    """
    def __init__(self, state_manager, config=None):
        default_config = {
            'swing_lookback_5m': 5, # تعداد کندل برای تشخیص سوینگ در تایم ۵ دقیقه
            'history_candles_1m': 300 # حداقل تعداد کندل ۱ دقیقه برای تحلیل
        }
        super().__init__(state_manager, config or default_config)
        self.name = "LiqSweep"
        self.points_of_interest = {} # دیکشنری برای نگهداری POI های دست‌نخورده
        self.touched_pois = {}       # دیکشنری برای POI های لمس‌شده که منتظر تایید هستند
        self.last_5m_timestamp = {}  # برای ردیابی کندل‌های ۵ دقیقه جدید

    # ==========================================================================
    # بخش اول: متدهای منطقی (برگرفته از اسکریپت شما)
    # ==========================================================================
    def _find_swing_points(self, data):
        lookback = self.config['swing_lookback_5m']
        data['is_swing_high'] = data['high'].rolling(lookback * 2, center=True).max() == data['high']
        data['is_swing_low'] = data['low'].rolling(lookback * 2, center=True).min() == data['low']
        return data

    def _check_liquidity_sweep(self, index, df_htf):
        if index < 1: return None, None
        current_candle = df_htf.iloc[index]
        past_swings = df_htf.iloc[:index-1]
        last_swing_high = past_swings[past_swings['is_swing_high']]['high']
        if not last_swing_high.empty and current_candle['high'] > last_swing_high.iloc[-1] and current_candle['close'] < last_swing_high.iloc[-1]:
            return 'Bearish', 'Liquidity Sweep'
        last_swing_low = past_swings[past_swings['is_swing_low']]['low']
        if not last_swing_low.empty and current_candle['low'] < last_swing_low.iloc[-1] and current_candle['close'] > last_swing_low.iloc[-1]:
            return 'Bullish', 'Liquidity Sweep'
        return None, None

    def _check_bos(self, index, df_htf):
        if index < 1: return None, None
        current_candle = df_htf.iloc[index]
        past_swings = df_htf.iloc[:index-1]
        last_swing_high = past_swings[past_swings['is_swing_high']]['high']
        if not last_swing_high.empty and current_candle['close'] > last_swing_high.iloc[-1]:
            return 'Bullish', 'BOS'
        last_swing_low = past_swings[past_swings['is_swing_low']]['low']
        if not last_swing_low.empty and current_candle['close'] < last_swing_low.iloc[-1]:
            return 'Bearish', 'BOS'
        return None, None

    def _check_ob(self, index, df_htf):
        if index < 1: return None, None
        candle1, candle2 = df_htf.iloc[index-1], df_htf.iloc[index]
        if candle2['close'] > candle1['high'] and candle1['open'] > candle1['close']:
            return 'Bullish', 'OB'
        if candle2['close'] < candle1['low'] and candle1['open'] < candle1['close']:
            return 'Bearish', 'OB'
        return None, None

    def _find_poi_with_or_logic(self, index, df_htf):
        sweep_dir, sweep_type = self._check_liquidity_sweep(index, df_htf)
        if not sweep_dir:
            return None

        bos_dir, bos_type = self._check_bos(index, df_htf)
        ob_dir, ob_type = self._check_ob(index, df_htf)

        reasons = {sweep_type}
        if sweep_dir == bos_dir: reasons.add(bos_type)
        if sweep_dir == ob_dir: reasons.add(ob_type)

        if len(reasons) > 1:
            poi_candle = df_htf.iloc[index]
            return {
                'type': f"POI 5m: {' + '.join(sorted(list(reasons)))}",
                'entry_price': poi_candle['high'] if sweep_dir == 'Bullish' else poi_candle['low'],
                'stop_loss': poi_candle['low'] if sweep_dir == 'Bullish' else poi_candle['high'],
                'discovery_time': poi_candle.name,
                'direction': sweep_dir
            }
        return None

    # ==========================================================================
    # بخش دوم: متد اصلی check برای اجرا در ربات زنده
    # ==========================================================================
    def check(self, symbol: str, kline_history: deque, **kwargs):
        if len(kline_history) < self.config['history_candles_1m']:
            return None

        # --- آماده‌سازی داده‌ها ---
        if symbol not in self.points_of_interest: self.points_of_interest[symbol] = []
        if symbol not in self.touched_pois: self.touched_pois[symbol] = []
        if symbol not in self.last_5m_timestamp: self.last_5m_timestamp[symbol] = None

        df_1m = pd.DataFrame(list(kline_history))
        df_1m['timestamp'] = pd.to_datetime(df_1m['open_time'], unit='ms')
        df_1m.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close']:
            df_1m[col] = pd.to_numeric(df_1m[col])
        
        current_1m_candle = df_1m.iloc[-1]
        
        # --- ۱. آپدیت نواحی POI با هر کندل جدید ۵ دقیقه‌ای ---
        df_5m = df_1m.resample('5min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
        if df_5m.empty: return None
        
        last_5m_candle_time = df_5m.index[-1]
        if self.last_5m_timestamp[symbol] != last_5m_candle_time:
            self.last_5m_timestamp[symbol] = last_5m_candle_time
            df_5m_with_swings = self._find_swing_points(df_5m.copy())
            
            # برای بهینگی، فقط چند کندل آخر ۵ دقیقه را برای یافتن POI جدید چک می‌کنیم
            for i in range(max(0, len(df_5m_with_swings) - 3), len(df_5m_with_swings)):
                new_poi = self._find_poi_with_or_logic(i, df_5m_with_swings)
                if new_poi:
                    # جلوگیری از افزودن POI تکراری
                    if not any(p['entry_price'] == new_poi['entry_price'] for p in self.points_of_interest[symbol]):
                        self.points_of_interest[symbol].append(new_poi)
                        print(f"✅ [{self.name}][{symbol}] New POI detected at {new_poi['entry_price']:.2f} ({new_poi['direction']})")

        # --- ۲. بررسی برخورد قیمت فعلی با نواحی POI دست‌نخورده ---
        for poi in list(self.points_of_interest[symbol]):
            if poi['discovery_time'] < current_1m_candle.name:
                is_bullish_touch = poi['direction'] == 'Bullish' and current_1m_candle['low'] <= poi['entry_price']
                is_bearish_touch = poi['direction'] == 'Bearish' and current_1m_candle['high'] >= poi['entry_price']
                if is_bullish_touch or is_bearish_touch:
                    print(f" காத்திருப்பு [{self.name}][{symbol}] POI at {poi['entry_price']:.2f} was touched. Waiting for confirmation.")
                    self.touched_pois[symbol].append(poi)
                    self.points_of_interest[symbol].remove(poi)

        # --- ۳. بررسی کندل تاییدیه برای ورود به معامله ---
        for poi in list(self.touched_pois[symbol]):
            is_bullish_confirmation = poi['direction'] == 'Bullish' and current_1m_candle['close'] > current_1m_candle['open']
            is_bearish_confirmation = poi['direction'] == 'Bearish' and current_1m_candle['close'] < current_1m_candle['open']
            
            if is_bullish_confirmation or is_bearish_confirmation:
                entry_price = current_1m_candle['close']
                stop_loss = poi['stop_loss']
                risk_points = abs(entry_price - stop_loss)
                if risk_points == 0: continue

                print(f"🚀 [{self.name}][{symbol}] Confirmation received! Entering {poi['direction']} trade.")
                self.touched_pois[symbol].remove(poi) # ناحیه استفاده شده را حذف می‌کنیم

                # ساخت پکیج سیگنال استاندارد
                return {
                    'type': poi['direction'],
                    'level': entry_price,
                    'stop_loss': stop_loss,
                    'setup': poi['type'] # نام دقیق ستاپ را برای تحلیل بهتر ذخیره می‌کنیم
                }
        return None