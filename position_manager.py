# position_manager.py
import time
import threading
from datetime import datetime, timezone
from alert import send_bulk_telegram_alert

class PositionManager:
    def __init__(self, state_manager, bot_token, chat_ids, risk_config, active_monitors, backtest_mode=False):
        self.state_manager = state_manager
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.risk_config = risk_config
        self.active_monitors = active_monitors
        self.active_positions = {}
        self.closed_trades = []
        self.lock = threading.Lock()
        self.backtest_mode = backtest_mode
        if self.backtest_mode:
            print("PositionManager is running in BACKTEST MODE.")

    def on_new_signal(self, setup, symbol):
        with self.lock:
            if symbol in self.active_positions: return
            print(f"\n{'='*20} NEW TRADE SIGNAL {'='*20}")
            self._open_position(setup, symbol)

    def _open_position(self, setup, symbol):
        direction = "Buy" if "BULLISH" in setup.get('signal_type', '') else "Sell"
        entry_price = setup.get('price')
        stop_loss = setup.get('stop_loss_suggestion')

        if not all([direction, entry_price, stop_loss]):
            print(f"[ERROR] Invalid setup received for {symbol}: {setup}"); return
        
        risk_amount = abs(entry_price - stop_loss)
        rr_ratios = self.risk_config.get('RR_RATIOS', [1])
        if direction == 'Buy':
            rr1_target = entry_price + (risk_amount * rr_ratios[0])
        else:
            rr1_target = entry_price - (risk_amount * rr_ratios[0])
        
        position_data = {
            "symbol": symbol, "direction": direction, "status": "OPEN",
            "entry_price": entry_price, "stop_loss": stop_loss,
            "tp1": rr1_target, "entry_time": setup.get('timestamp'),
            "setup_type": setup.get('signal_type', 'N/A') # --- [اصلاح شد] --- برای نمایش در تلگرام
        }
        self.active_positions[symbol] = position_data
        
        if self.backtest_mode:
            print(f"✅ [BACKTEST] Position Opened: {direction} {symbol} @ {entry_price:.2f} | SL: {stop_loss:.2f} | TP1: {rr1_target:.2f}")
        else:
            if symbol in self.active_monitors: self.active_monitors[symbol].on_position_opened(direction)
            alert_message = (f"🟢 **پوزیشن جدید باز شد: {direction} {symbol}** 🟢\n\n"
                           f"قیمت ورود: `{entry_price:.4f}`\nحد ضرر: `{stop_loss:.4f}`\nحد سود اول: `{rr1_target:.4f}`")
            self.send_info_alert(alert_message)

    def _close_position(self, symbol, close_price, reason, close_time):
        with self.lock:
            if symbol in self.active_positions:
                position = self.active_positions.pop(symbol)
                pnl_percent = ((close_price - position['entry_price']) / position['entry_price']) * 100
                if position['direction'] == 'Sell': pnl_percent *= -1
                
                # --- [اصلاح شد] --- روش صحیح ادغام دیکشنری
                trade_result = {**position, "close_price": close_price, "close_reason": reason, "pnl_percent": pnl_percent, "close_time": close_time}
                self.closed_trades.append(trade_result)
                
                if self.backtest_mode:
                    result_icon = "🏆" if pnl_percent > 0 else " L "
                    print(f"{result_icon} [BACKTEST] Position Closed: {symbol} at {close_price:.2f} | Reason: {reason} | P&L: {pnl_percent:.2f}%")
                else:
                    if symbol in self.active_monitors: self.active_monitors[symbol].on_position_closed()
                    self.send_info_alert(f"🔴 **پوزیشن {symbol} بسته شد** 🔴\nدلیل: {reason}\nسود/زیان: {pnl_percent:.2f}%")
    
    def check_and_update_positions(self, current_candle):
        if not self.active_positions: return
        symbol = current_candle.get('symbol')
        if symbol in self.active_positions:
            position = self.active_positions[symbol]
            candle_low, candle_high = current_candle.get('low'), current_candle.get('high')
            if not all([candle_low, candle_high]): return
            
            # --- [اصلاح شد] --- ساختار شرطی Buy/Sell
            if position['direction'] == 'Buy':
                if candle_low <= position['stop_loss']: self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit", current_candle.get('open_time'))
                elif candle_high >= position['tp1']: self._close_position(symbol, position['tp1'], "Take-Profit 1 Hit", current_candle.get('open_time'))
            elif position['direction'] == 'Sell':
                if candle_high >= position['stop_loss']: self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit", current_candle.get('open_time'))
                elif candle_low <= position['tp1']: self._close_position(symbol, position['tp1'], "Take-Profit 1 Hit", current_candle.get('open_time'))
    
    def get_backtest_results(self):
        # ... (این تابع برای بک‌تستر است و بدون تغییر باقی می‌ماند) ...
        pass

    def run_updater(self):
        if self.backtest_mode: return
        thread = threading.Thread(target=self._position_update_loop, daemon=True)
        thread.start()

    def _position_update_loop(self):
        while True:
            time.sleep(0.2)
            with self.lock:
                active_symbols = list(self.active_positions.keys())
            for symbol in active_symbols:
                if symbol in self.active_monitors:
                    monitor = self.active_monitors[symbol]
                    last_price = self.state_manager.get_symbol_state(symbol, 'last_price')
                    if not last_price: continue
                    self.check_and_update_positions({'symbol': symbol, 'low': last_price, 'high': last_price, 'open_time': datetime.now(timezone.utc)})

    def send_info_alert(self, message):
        if self.backtest_mode or not self.bot_token: return
        send_bulk_telegram_alert(message, self.bot_token, self.chat_ids)
            
    def get_open_positions(self):
        with self.lock: return list(self.active_positions.values())
            
    def get_daily_performance(self):
        with self.lock:
            # --- [اصلاح شد] --- هماهنگ‌سازی با interactive_bot
            today_str = datetime.now(timezone.utc).date().isoformat()
            total_pnl = sum(t.get('pnl_percent', 0) for t in self.closed_trades if t.get('close_time') and t['close_time'].date().isoformat() == today_str)
            return {"daily_profit": total_pnl, "daily_drawdown": 0.0, "drawdown_limit": self.risk_config.get("DAILY_DRAWDOWN_LIMIT_PERCENT")}