# setups/advanced_orderflow_setup.py

import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from .base_setup import BaseSetup
from indicators import calculate_atr # برای حد ضرر پویا

class AdvancedOrderflowSetup(BaseSetup):
    """
    کلاس یکپارچه برای ستاپ‌های پیشرفته مبتنی بر Order Flow, Volume Profile و VWAP.
    """
    def __init__(self, state_manager, config=None):
        default_config = {
            'regression_window': 14,
            'delta_divergence_threshold': -0.5, # همبستگی منفی برای واگرایی
            'volume_z_score_threshold': 2.0, # آستانه Z-score برای حجم غیرعادی
        }
        super().__init__(state_manager, config or default_config)
        self.name = "AdvancedOrderflow"

    def check(self, symbol: str, price_data: pd.DataFrame, levels: dict, session_indicators: dict, atr: float, **kwargs):
        """
        متد اصلی برای بررسی تمام ستاپ‌های این کلاس.
        """
        if price_data.empty or len(price_data) < 20 or not session_indicators:
            return None
        
        # استخراج داده‌های مورد نیاز
        current_candle = price_data.iloc[-1]
        prev_candle = price_data.iloc[-2]
        val = levels.get('val', 0)
        vah = levels.get('vah', 0)
        
        # اجرای هر ستاپ
        signals = []
        signals.append(self._check_stop_hunt(symbol, current_candle, prev_candle, val, vah, atr, session_indicators))
        signals.append(self._check_pdf_reversal(symbol, current_candle, val, vah, atr, session_indicators, price_data))
        signals.append(self._check_delta_regression(symbol, current_candle, atr, session_indicators))
        signals.append(self._check_vwap_deviation(symbol, current_candle, atr, session_indicators))

        # بازگرداندن اولین سیگنال معتبر پیدا شده
        for signal in signals:
            if signal:
                return signal
        return None

    def _find_dynamic_target(self, entry_price, direction, levels):
        """یک حد سود پویا بر اساس سطوح کلیدی بعدی پیدا می‌کند."""
        if direction == 'Buy':
            # نزدیک‌ترین سطح مقاومت (PDH, VAH) بالاتر از قیمت ورود
            targets = [levels.get('pdh', np.inf), levels.get('vah', np.inf)]
            valid_targets = [t for t in targets if t > entry_price]
            return min(valid_targets) if valid_targets else entry_price * 1.02
        else: # Sell
            # نزدیک‌ترین سطح حمایت (PDL, VAL) پایین‌تر از قیمت ورود
            targets = [levels.get('pdl', 0), levels.get('val', 0)]
            valid_targets = [t for t in targets if t < entry_price]
            return max(valid_targets) if valid_targets else entry_price * 0.98

    # ------------------------ ستاپ ۱: استاپ هانت در VAL/VAH ------------------------
    def _check_stop_hunt(self, symbol, current, prev, val, vah, atr, indicators):
        if val == 0 or vah == 0: return None
        
        # شرایط خرید: شکار استاپ در VAL و بازگشت به بالا
        buy_conditions = (
            prev['low'] < val and
            current['close'] > val and
            current['close'] > current['open'] and
            indicators.get('delta', 0) > 0 # تایید با دلتای مثبت
        )
        if all(buy_conditions):
            sl = prev['low'] - (atr * 0.5)
            tp = self._find_dynamic_target(current['close'], 'Buy', {'vah': vah})
            return self._create_signal('Long', symbol, current['close'], sl, tp, "Stop Hunt at VAL", [f"✅ شکار نقدینگی در VAL ({val:.2f})", f"✅ تایید با دلتای مثبت"])

        # شرایط فروش: شکار استاپ در VAH و بازگشت به پایین
        sell_conditions = (
            prev['high'] > vah and
            current['close'] < vah and
            current['close'] < current['open'] and
            indicators.get('delta', 0) < 0 # تایید با دلتای منفی
        )
        if all(sell_conditions):
            sl = prev['high'] + (atr * 0.5)
            tp = self._find_dynamic_target(current['close'], 'Sell', {'val': val})
            return self._create_signal('Short', symbol, current['close'], sl, tp, "Stop Hunt at VAH", [f"✅ شکار نقدینگی در VAH ({vah:.2f})", f"✅ تایید با دلتای منفی"])
        return None

    # ------------------------ ستاپ ۲: بازگشت با حجم غیرعادی (PDF) ------------------------
    def _check_pdf_reversal(self, symbol, current, val, vah, atr, indicators, df):
        if val == 0 or vah == 0: return None
        
        # محاسبه Z-Score حجم کندل فعلی
        mean_vol = df['volume'].mean()
        std_vol = df['volume'].std()
        z_score = (current['volume'] - mean_vol) / std_vol if std_vol > 0 else 0

        # شرایط خرید: حجم بالا در نزدیکی VAL
        buy_conditions = (
            abs(current['close'] - val) < (atr * 1.5) and
            z_score >= self.config['volume_z_score_threshold'] and
            current['close'] > current['open'] and indicators.get('delta', 0) > 0
        )
        if all(buy_conditions):
            sl = current['low'] - (atr * 0.5)
            tp = self._find_dynamic_target(current['close'], 'Buy', {'vah': vah})
            return self._create_signal('Long', symbol, current['close'], sl, tp, "PDF Reversal at VAL", [f"✅ حجم غیرعادی (Z-Score: {z_score:.2f}) در VAL", "✅ جذب سفارشات خرید"])

        # شرایط فروش: حجم بالا در نزدیکی VAH
        sell_conditions = (
            abs(current['close'] - vah) < (atr * 1.5) and
            z_score >= self.config['volume_z_score_threshold'] and
            current['close'] < current['open'] and indicators.get('delta', 0) < 0
        )
        if all(sell_conditions):
            sl = current['high'] + (atr * 0.5)
            tp = self._find_dynamic_target(current['close'], 'Sell', {'val': val})
            return self._create_signal('Short', symbol, current['close'], sl, tp, "PDF Reversal at VAH", [f"✅ حجم غیرعادی (Z-Score: {z_score:.2f}) در VAH", "✅ جذب سفارشات فروش"])
        return None

    # ------------------------ ستاپ ۳: رگرسیون و واگرایی دلتا ------------------------
    def _check_delta_regression(self, symbol, current, atr, indicators):
        price_window = indicators.get('price_window', [])
        delta_window = indicators.get('delta_window', [])

        if len(price_window) < self.config['regression_window']:
            return None
            
        X = np.arange(len(delta_window)).reshape(-1, 1)
        price_slope = LinearRegression().fit(X, price_window).coef_[0]
        delta_slope = LinearRegression().fit(X, delta_window).coef_[0]
        correlation = np.corrcoef(price_window, delta_window)[0, 1]

        # شرایط خرید: واگرایی صعودی
        buy_conditions = (
            price_slope < 0 and delta_slope > 0 and
            correlation < self.config['delta_divergence_threshold'] and current['delta'] > 0
        )
        if all(buy_conditions):
            sl = current['low'] - (atr * 1.5)
            tp = self._find_dynamic_target(current['close'], 'Buy', {})
            return self._create_signal('Long', symbol, current['close'], sl, tp, "Delta Bullish Divergence", [f"✅ واگرایی دلتا: قیمت 📉, دلتا 📈", f"✅ همبستگی: {correlation:.2f}"])

        # شرایط فروش: واگرایی نزولی
        sell_conditions = (
            price_slope > 0 and delta_slope < 0 and
            correlation < self.config['delta_divergence_threshold'] and current['delta'] < 0
        )
        if all(sell_conditions):
            sl = current['high'] + (atr * 1.5)
            tp = self._find_dynamic_target(current['close'], 'Sell', {})
            return self._create_signal('Short', symbol, current['close'], sl, tp, "Delta Bearish Divergence", [f"✅ واگرایی دلتا: قیمت 📈, دلتا 📉", f"✅ همبستگی: {correlation:.2f}"])
        return None

    # ------------------------ ستاپ ۴: بازگشت از باندهای VWAP ------------------------
    def _check_vwap_deviation(self, symbol, current, atr, indicators):
        vwap = indicators.get('vwap', 0)
        upper_band = indicators.get('vwap_upper', 0)
        lower_band = indicators.get('vwap_lower', 0)
        if vwap == 0: return None
        
        # شرایط خرید: بازگشت از باند پایین VWAP
        buy_conditions = (
            current['low'] <= lower_band and
            current['close'] > lower_band and
            current['close'] > current['open'] and indicators.get('delta', 0) > 0
        )
        if all(buy_conditions):
            sl = current['low'] - (atr * 0.5)
            return self._create_signal('Long', symbol, current['close'], sl, vwap, "VWAP Lower Band Reversal", [f"✅ بازگشت از باند پایین VWAP ({lower_band:.2f})", "✅ هدف: بازگشت به VWAP"])

        # شرایط فروش: بازگشت از باند بالای VWAP
        sell_conditions = (
            current['high'] >= upper_band and
            current['close'] < upper_band and
            current['close'] < current['open'] and indicators.get('delta', 0) < 0
        )
        if all(sell_conditions):
            sl = current['high'] + (atr * 0.5)
            return self._create_signal('Short', symbol, current['close'], sl, vwap, "VWAP Upper Band Reversal", [f"✅ بازگشت از باند بالای VWAP ({upper_band:.2f})", "✅ هدف: بازگشت به VWAP"])
        return None

    def _create_signal(self, direction, symbol, entry, sl, tp, setup_name, reasons):
        """یک ساختار استاندارد برای سیگنال ایجاد می‌کند."""
        return {
            'symbol': symbol,
            'type': direction,
            'level': entry,
            'stop_loss': sl,
            'take_profit': tp,
            'setup': setup_name,
            'reasons': reasons
        }