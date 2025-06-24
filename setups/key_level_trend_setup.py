# setups/key_level_trend_setup.py

import time
import pandas as pd
from .base_setup import BaseSetup

class KeyLevelTrendSetup(BaseSetup):
    def __init__(self, state_manager, config=None):
        default_config = {
            'cooldown_seconds': 60 * 30,
            'price_buffer_percent': 0.0015 # افزایش تلرانس به 0.15%
        }
        super().__init__(state_manager, config or default_config)
        self.name = "KeyLevelTrend"
    
    def check(self, symbol: str, price_data: pd.DataFrame, levels: dict, daily_trend: str, **kwargs):
        # ...
        # استفاده از بافر قابل تنظیم
        price_buffer = price_data['close'].iloc[-1] * self.config['price_buffer_percent']
        
        if daily_trend == 'NEUTRAL' or price_data.empty:
            return None

        low_price = price_data['low'].iloc[-1]
        high_price = price_data['high'].iloc[-1]
        current_price = price_data['close'].iloc[-1]
        price_buffer = current_price * 0.0012  # تلرانس 0.12% برای تشخیص برخورد

        # --- منطق روند صعودی ---
        if daily_trend == 'BULLISH':
            # بررسی سیگنال خرید در VAL (کف ناحیه ارزش)
            val = levels.get('daily_vp', {}).get('val')
            if val and abs(low_price - val) <= price_buffer:
                level_id = f"buy_val_{val:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BUY_at_VAL', symbol, val, val * 0.995)
            
            # بررسی سیگنال خرید در PDL (کف روز قبل)
            pdl = levels.get('pdl')
            if pdl and abs(low_price - pdl) <= price_buffer:
                level_id = f"buy_pdl_{pdl:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('BUY_at_PDL', symbol, pdl, pdl * 0.995)

        # --- منطق روند نزولی ---
        if daily_trend == 'BEARISH':
            # بررسی سیگنال فروش در VAH (سقف ناحیه ارزش)
            vah = levels.get('daily_vp', {}).get('vah')
            if vah and abs(high_price - vah) <= price_buffer:
                level_id = f"sell_vah_{vah:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('SELL_at_VAH', symbol, vah, vah * 1.005)

            # بررسی سیگنال فروش در PDH (سقف روز قبل)
            pdh = levels.get('pdh')
            if pdh and abs(high_price - pdh) <= price_buffer:
                level_id = f"sell_pdh_{pdh:.2f}"
                if not self._is_on_cooldown(symbol, level_id):
                    self._set_cooldown(symbol, level_id)
                    return self._create_signal('SELL_at_PDH', symbol, pdh, pdh * 1.005)
        
        return None

    def _is_on_cooldown(self, symbol, level_id):
        """بررسی می‌کند آیا یک سطح خاص در حالت cooldown است یا نه."""
        last_alert_time = self.state_manager.get_level_alert_time(symbol, level_id)
        return time.time() - last_alert_time < self.config['cooldown_seconds']

    def _set_cooldown(self, symbol, level_id):
        """زمان آخرین هشدار را برای یک سطح خاص تنظیم می‌کند."""
        self.state_manager.update_level_alert_time(symbol, level_id)
        print(f"Cooldown set for level '{level_id}' on {symbol}")

    def _create_signal(self, setup_type, symbol, price, sl):
        """یک پکیج استاندارد برای سیگنال ایجاد می‌کند."""
        direction = 'BUY' if 'BUY' in setup_type else 'SELL'
        print(f"🚀 [{self.name}][{symbol}] Signal: {setup_type} at {price:.2f}")
        return {'type': direction, 'level': price, 'stop_loss': sl}