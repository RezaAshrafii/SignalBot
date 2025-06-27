# setups/key_level_trend_setup.py

import time
import pandas as pd
from .base_setup import BaseSetup

class KeyLevelTrendSetup(BaseSetup):
    def __init__(self, state_manager, config=None):
        default_config = {
            'cooldown_seconds': 60 * 30,
            'price_buffer_percent': 0.0015
        }
        super().__init__(state_manager, config or default_config)
        self.name = "KeyLevelTrend"
    
    def check(self, symbol: str, price_data: pd.DataFrame, levels: dict, daily_trend: str, **kwargs):
        if daily_trend == 'NEUTRAL' or price_data.empty:
            return None

        low_price = price_data['low'].iloc[-1]
        high_price = price_data['high'].iloc[-1]
        current_price = price_data['close'].iloc[-1]
        price_buffer = current_price * self.config['price_buffer_percent']

        # --- [اصلاح شد] --- استفاده از نام‌گذاری هماهنگ
        if daily_trend == 'BULLISH':
            val = levels.get('val')
            if val and abs(low_price - val) <= price_buffer:
                level_id = f"buy_val_{val:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BULLISH_at_VAL', symbol, val, val * 0.995)
            
            pdl = levels.get('pdl')
            if pdl and abs(low_price - pdl) <= price_buffer:
                level_id = f"buy_pdl_{pdl:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BULLISH_at_PDL', symbol, pdl, pdl * 0.995)

        # --- [اصلاح شد] --- استفاده از نام‌گذاری هماهنگ
        if daily_trend == 'BEARISH':
            vah = levels.get('vah')
            if vah and abs(high_price - vah) <= price_buffer:
                level_id = f"sell_vah_{vah:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BEARISH_at_VAH', symbol, vah, vah * 1.005)

            pdh = levels.get('pdh')
            if pdh and abs(high_price - pdh) <= price_buffer:
                level_id = f"sell_pdh_{pdh:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BEARISH_at_PDH', symbol, pdh, pdh * 1.005)
        
        return None

    def _is_on_cooldown(self, symbol, level_id):
        last_alert_time = self.state_manager.get_level_alert_time(symbol, level_id)
        return time.time() - last_alert_time < self.config['cooldown_seconds']

    def _set_cooldown(self, symbol, level_id):
        self.state_manager.update_level_alert_time(symbol, level_id)
        print(f"Cooldown set for level '{level_id}' on {symbol}")

    def _create_signal(self, setup_type, symbol, price, sl):
        # --- [اصلاح شد] --- استفاده از نام‌گذاری هماهنگ
        direction = 'Buy' if 'BULLISH' in setup_type else 'Sell'
        print(f"🚀 [{self.name}][{symbol}] Signal: {setup_type} at {price:.2f}")
        return {'type': direction, 'level': price, 'stop_loss': sl}