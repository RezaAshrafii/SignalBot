# position_manager.py
import time, threading
from datetime import datetime, timezone
# این خط اصلاح شد تا از تابع صحیح موجود در alert.py استفاده کند
from alert import send_bulk_telegram_alert

class PositionManager:
    def __init__(self, state_manager, bot_token, chat_ids, risk_config):
        self.state_manager = state_manager
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        
        self.risk_per_trade = risk_config.get("RISK_PER_TRADE_PERCENT", 1.0) / 100
        self.daily_drawdown_limit = risk_config.get("DAILY_DRAWDOWN_LIMIT_PERCENT", 3.0)
        self.rr_ratios = risk_config.get("RR_RATIOS", [1, 2, 3])
        
        self.active_positions = {}
        self.trade_history = []
        self.daily_profit = 0.0
        self.daily_drawdown = 0.0
        self.is_trading_disabled = False
        self.lock = threading.Lock()

    def on_new_signal(self, signal_package):
        with self.lock:
            symbol = signal_package['symbol']
            if self.is_trading_disabled:
                self.send_info_alert(f"⚠️ **سیستم متوقف است** ⚠️\n\nسیگنال {signal_package['setup_type']} برای `{symbol}` دریافت شد اما به دلیل رسیدن به حد ضرر روزانه، معاملات جدید باز نمی‌شوند.")
                return
            
            if symbol in self.active_positions:
                return

            self._open_position(signal_package)

    def _open_position(self, signal):
        position_data = {
            **signal,
            "status": "OPEN",
            "take_profits": self._calculate_take_profits(signal['entry_price'], signal['stop_loss'], signal['direction']),
            "pnl": 0.0
        }
        self.active_positions[signal['symbol']] = position_data
        
        tp_str = '\n'.join([f"   - TP{i+1}: `{tp['price']:,.2f}` ({tp['size_percent']}%)" for i, tp in enumerate(position_data['take_profits'])])
        
        message = (
            f"✅ **پوزیشن جدید باز شد** ✅\n\n"
            f"Symbol: `{signal['symbol']}`\n"
            f"جهت: **{signal['direction'].upper()}**\n"
            f"نوع ستاپ: `{signal['setup_type']}`\n"
            f"قیمت ورود: `{signal['entry_price']:,.2f}`\n"
            f"حد ضرر: `{signal['stop_loss']:,.2f}`\n\n"
            f"🎯 **اهداف سود:**\n{tp_str}"
        )
        self.send_info_alert(message)

    def _calculate_take_profits(self, entry_price, stop_loss, direction):
        risk_per_unit = abs(entry_price - stop_loss)
        tps = []
        size_distribution = [50, 30, 20] 
        
        for i, rr in enumerate(self.rr_ratios):
            if direction == 'Buy':
                tp_price = entry_price + (risk_per_unit * rr)
            else: # Sell
                tp_price = entry_price - (risk_per_unit * rr)
            
            tps.append({
                "price": tp_price, 
                "size_percent": size_distribution[i],
                "hit": False
            })
        return tps

    def update_positions(self):
        pass

    def send_info_alert(self, message):
        # فراخوانی تابع با نام صحیح
        send_bulk_telegram_alert(message, self.bot_token, self.chat_ids)

    def get_open_positions(self):
        """لیستی از پوزیشن‌های فعال فعلی را برمی‌گرداند."""
        with self.lock:
            return list(self.active_positions.values())

    def get_daily_performance(self):
        """سود و زیان و دراودان روزانه را برمی‌گرداند."""
        with self.lock:
            return {
                "daily_profit": self.daily_profit,
                "daily_drawdown": self.daily_drawdown,
                "drawdown_limit": self.daily_drawdown_limit
            }