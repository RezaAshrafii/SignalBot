# setups/ichimoku_setup.py

import pandas as pd
import pandas_ta as ta
from collections import deque
from .base_setup import BaseSetup

class IchimokuSetup(BaseSetup):
    """
    این کلاس استراتژی "ناحیه مبدأ ریورسال ایچیموکو" را پیاده‌سازی می‌کند.
    """
    def __init__(self, state_manager, config=None):
        default_config = {
            'sharpness_threshold_percent': 0.5,
            'min_return_delay_hours': 4,
            'zone_tolerance_percent': 0.1,
            'history_candles': 200
        }
        super().__init__(state_manager, config or default_config)
        self.name = "IchimokuReversalOrigin"
        # این دیکشنری نواحی شناسایی‌شده را برای هر ارز به صورت جداگانه نگهداری می‌کند
        self.origin_zones = {}

    def check(self, symbol: str, kline_history: deque, **kwargs):
        if len(kline_history) < self.config['history_candles']:
            return None

        if symbol not in self.origin_zones:
            self.origin_zones[symbol] = []

        df = pd.DataFrame(list(kline_history))
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')

        df.ta.ichimoku(append=True)

        self._find_new_origin_zone(symbol, df)
        return self._check_for_reversal_entry(symbol, df)

    def _find_new_origin_zone(self, symbol: str, df: pd.DataFrame):
        if len(df) < 4: return
        
        last_candle = df.iloc[-2]
        prev_candle = df.iloc[-3]
        tenkan_now = last_candle['ITS_9']
        tenkan_prev = prev_candle['ITS_9']
        tenkan_before_prev = df.iloc[-4]['ITS_9']

        is_v_shape_turn = tenkan_now > tenkan_prev and tenkan_prev < tenkan_before_prev
        if is_v_shape_turn and tenkan_prev > 0:
            sharpness = abs(tenkan_now - tenkan_prev) / tenkan_prev
            if sharpness * 100 > self.config['sharpness_threshold_percent']:
                new_zone = {'type': 'BUY', 'price_level': tenkan_prev, 'created_at': last_candle['open_time'], 'status': 'virgin'}
                if not any(z['price_level'] == new_zone['price_level'] for z in self.origin_zones[symbol]):
                    self.origin_zones[symbol].append(new_zone)
                    print(f"✅ [{self.name}][{symbol}] New BUY Origin Zone Detected at: {new_zone['price_level']:.2f}")

        is_a_shape_turn = tenkan_now < tenkan_prev and tenkan_prev > tenkan_before_prev
        if is_a_shape_turn and tenkan_prev > 0:
            sharpness = abs(tenkan_now - tenkan_prev) / tenkan_prev
            if sharpness * 100 > self.config['sharpness_threshold_percent']:
                new_zone = {'type': 'SELL', 'price_level': tenkan_prev, 'created_at': last_candle['open_time'], 'status': 'virgin'}
                if not any(z['price_level'] == new_zone['price_level'] for z in self.origin_zones[symbol]):
                    self.origin_zones[symbol].append(new_zone)
                    print(f"✅ [{self.name}][{symbol}] New SELL Origin Zone Detected at: {new_zone['price_level']:.2f}")

    def _check_for_reversal_entry(self, symbol: str, df: pd.DataFrame):
        current_kline = df.iloc[-1]
        current_price = current_kline['close']
        
        for zone in self.origin_zones.get(symbol, []):
            if zone['status'] != 'virgin': continue

            time_since_creation = current_kline['open_time'] - zone['created_at']
            if time_since_creation < pd.Timedelta(hours=self.config['min_return_delay_hours']): continue

            price_level = zone['price_level']
            tolerance = price_level * (self.config['zone_tolerance_percent'] / 100)
            
            is_in_buy_zone = zone['type'] == 'BUY' and (price_level - tolerance) <= current_kline['low'] <= (price_level + tolerance)
            is_in_sell_zone = zone['type'] == 'SELL' and (price_level - tolerance) <= current_kline['high'] <= (price_level + tolerance)

            if is_in_buy_zone or is_in_sell_zone:
                print(f"🚀 [{self.name}][{symbol}] Reversal Signal! Price entered '{zone['type']}' zone at {price_level:.2f}")
                zone['status'] = 'touched'
                
                # تطبیق خروجی با فرمت استاندارد ربات
                return {
                    'type': zone['type'],
                    'level': current_price,
                    'stop_loss': df.iloc[-15:]['low'].min() if zone['type'] == 'BUY' else df.iloc[-15:]['high'].max()
                }
        return None