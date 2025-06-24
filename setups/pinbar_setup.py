# setups/pinbar_setup.py

from collections import defaultdict
from datetime import datetime, timezone
from .base_setup import BaseSetup

class PinbarSetup(BaseSetup):
    """
    این ستاپ به دنبال الگوی کندلی پین‌بار در تایم‌فریم ۵ دقیقه می‌گردد،
    آن هم زمانی که قیمت به یکی از سطوح کلیدی همسو با روند روزانه رسیده باشد.
    """
    def __init__(self, state_manager, config=None):
        super().__init__(state_manager, config)
        self.name = "PinbarConfirmation"
        # این متغیرها وضعیت داخلی خود ستاپ را مدیریت می‌کنند
        self.active_levels = defaultdict(dict)  # e.g., {'BTCUSDT': {65000: "Touched"}}
        self.level_test_counts = defaultdict(lambda: defaultdict(int))

    def _get_trading_session(self, utc_hour):
        if 1 <= utc_hour < 8: return "Asian Session"
        elif 8 <= utc_hour < 16: return "London Session"
        elif 16 <= utc_hour < 23: return "New York Session"
        else: return "After Hours"

    def _check_pin_bar(self, candle, direction):
        candle_range = candle.get('high', 0) - candle.get('low', 0)
        if candle_range == 0: return False
        body = abs(candle.get('open', 0) - candle.get('close', 0))
        upper_wick = candle.get('high', 0) - max(candle.get('open', 0), candle.get('close', 0))
        lower_wick = min(candle.get('open', 0), candle.get('close', 0)) - candle.get('low', 0)
        
        is_pin_bar_body = body < candle_range / 3
        if direction == 'Buy':
            return is_pin_bar_body and lower_wick > body * 2
        elif direction == 'Sell':
            return is_pin_bar_body and upper_wick > body * 2
        return False

    def _check_level_proximity(self, symbol, kline_1m, key_levels):
        """با هر کندل ۱ دقیقه، برخورد به سطوح را چک می‌کند."""
        for level_data in key_levels:
            level_price = level_data['level']
            if kline_1m['low'] <= level_price <= kline_1m['high']:
                if self.active_levels[symbol].get(level_price) != "Touched":
                    print(f"🎯 [{self.name}][{symbol}] Price touched level {level_data['level_type']} at {level_price}")
                    self.active_levels[symbol][level_price] = "Touched"
                    self.level_test_counts[symbol][level_price] += 1
                    # آپدیت وضعیت در state_manager برای نمایش در داشبورد
                    self.state_manager.update_symbol_state(symbol, 'level_test_counts', dict(self.level_test_counts[symbol]))

    def _evaluate_level_interaction(self, symbol, kline_5m, key_levels, daily_trend):
        """با بسته شدن کندل ۵ دقیقه، به دنبال سیگنال پین‌بار می‌گردد."""
        for level_price, status in list(self.active_levels.get(symbol, {}).items()):
            if status != "Touched": continue
            
            level_data = next((l for l in key_levels if l['level'] == level_price), None)
            if not level_data: continue
            
            trade_direction = None
            if "UP" in daily_trend and level_data['level_type'] in ['PDL', 'VAL', 'POC']:
                trade_direction = 'Buy'
            elif "DOWN" in daily_trend and level_data['level_type'] in ['PDH', 'VAH', 'POC']:
                trade_direction = 'Sell'
            
            if not trade_direction: continue
            
            if self._check_pin_bar(kline_5m, trade_direction):
                # پکیج سیگنال را ایجاد و برگردان
                utc_now = datetime.now(timezone.utc)
                test_count = self.level_test_counts[symbol][level_data['level']]
                session = self._get_trading_session(utc_now.hour)
                reasons = [
                    f"✅ پین‌بار ۵ دقیقه‌ای در جهت روند.",
                    f"✅ در سطح کلیدی: {level_data['level_type']} ({level_price})",
                    f"✅ تست شماره {test_count} از این سطح."
                ]
                stop_loss = kline_5m['low'] if trade_direction == 'Buy' else kline_5m['high']
                
                # ناحیه لمس شده را از لیست فعال حذف می‌کنیم تا سیگنال تکراری ندهد
                del self.active_levels[symbol][level_price]

                return {
                    "type": trade_direction,
                    "level": kline_5m['close'],
                    "stop_loss": stop_loss,
                    "setup": self.name,
                    "reasons": reasons, # ارسال دلایل برای نمایش به کاربر
                    "session": session,
                }
        return None

    def check(self, symbol, kline_1m, kline_5m, key_levels, daily_trend, **kwargs):
        # این ستاپ به هر دو کندل ۱ دقیقه و ۵ دقیقه نیاز دارد
        if not kline_1m: return None

        # بخش ۱: چک کردن برخورد با هر کندل ۱ دقیقه‌ای
        self._check_level_proximity(symbol, kline_1m, key_levels)

        # بخش ۲: ارزیابی اصلی فقط زمانی که کندل ۵ دقیقه جدیدی بسته شده باشد
        if not kline_5m:
            return None
        
        return self._evaluate_level_interaction(symbol, kline_5m, key_levels, daily_trend)