# fvg_logic.py
from collections import deque

class FvgLogic:
    def __init__(self):
        self.recent_candles = deque(maxlen=5); self.active_fvgs = []
    def check_setups(self, candle, key_levels):
        self.recent_candles.append(candle)
        self._find_new_fvgs(key_levels)
        return self._check_fvg_retest(candle)
    def _find_new_fvgs(self, key_levels):
        if len(self.recent_candles) < 3: return
        c1, c2, c3 = self.recent_candles[-3], self.recent_candles[-2], self.recent_candles[-1]
        pattern_min, pattern_max = min(c1['low'],c3['low']), max(c1['high'],c3['high'])
        is_at_key_level = any(level['level'] >= pattern_min and level['level'] <= pattern_max for level in key_levels)
        if not is_at_key_level: return
        if c3['low'] > c1['high'] and not any(fvg['low'] == c1['high'] for fvg in self.active_fvgs):
            self.active_fvgs.append({'type':'bullish','low':c1['high'],'high':c3['low'],'active':True})
        if c1['low'] > c3['high'] and not any(fvg['low'] == c3['high'] for fvg in self.active_fvgs):
            self.active_fvgs.append({'type':'bearish','low':c3['high'],'high':c1['low'],'active':True})
    def _check_fvg_retest(self, candle):
        for fvg in self.active_fvgs:
            if not fvg['active']: continue
            if fvg['type'] == 'bullish' and candle['low'] <= fvg['high']:
                fvg['active'] = False; return "خرید (FVG Filled)"
            if fvg['type'] == 'bearish' and candle['high'] >= fvg['low']:
                fvg['active'] = False; return "فروش (FVG Filled)"
        return None