# position_manager.py
import time
import threading
from datetime import datetime
from alert import send_bulk_telegram_alert

class PositionManager:
    def __init__(self, state_manager, bot_token, chat_ids, risk_config, active_monitors, backtest_mode=False):
        self.state_manager = state_manager
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.risk_config = risk_config
        self.active_monitors = active_monitors
        
        self.active_positions = {}
        self.closed_trades = [] # برای ثبت تاریخچه معاملات در بک‌تست
        self.lock = threading.Lock()
        
        # --- حالت بک‌تست ---
        self.backtest_mode = backtest_mode
        if self.backtest_mode:
            print("PositionManager is running in BACKTEST MODE.")

    def on_new_signal(self, setup, symbol):
        with self.lock:
            if symbol in self.active_positions:
                return # پوزیشن باز وجود دارد
            
            print(f"\n{'='*20} NEW TRADE SIGNAL {'='*20}")
            self._open_position(setup, symbol)

    def _open_position(self, setup, symbol):
        direction = "Buy" if "BULLISH" in setup['signal_type'] else "Sell"
        entry_price = setup['price']
        stop_loss = setup['stop_loss_suggestion']
        
        # محاسبه حد سود اول (ریسک به ریوارد ۱)
        risk_amount = abs(entry_price - stop_loss)
        if direction == 'Buy':
            rr1_target = entry_price + (risk_amount * self.risk_config['RR_RATIOS'][0])
        else: # Sell
            rr1_target = entry_price - (risk_amount * self.risk_config['RR_RATIOS'][0])
        
        position_data = {
            "symbol": symbol, "direction": direction, "status": "OPEN",
            "entry_price": entry_price, "stop_loss": stop_loss,
            "tp1": rr1_target, "entry_time": setup['timestamp']
        }
        self.active_positions[symbol] = position_data
        
        if self.backtest_mode:
            print(f"✅ [BACKTEST] Position Opened: {direction} {symbol} @ {entry_price:.2f} | SL: {stop_loss:.2f} | TP1: {rr1_target:.2f}")
        else:
            # اطلاع به مانیتور و ارسال الرت تلگرام در حالت لایو
            if symbol in self.active_monitors:
                self.active_monitors[symbol].on_position_opened(direction)
            
            alert_message = (
                f"🟢 **پوزیشن جدید باز شد: {direction} {symbol}** 🟢\n\n"
                f"قیمت ورود: `{entry_price:.4f}`\n"
                f"حد ضرر: `{stop_loss:.4f}`\n"
                f"حد سود اول: `{rr1_target:.4f}`"
            )
            self.send_info_alert(alert_message)

    def _close_position(self, symbol, close_price, reason, close_time):
        with self.lock:
            if symbol in self.active_positions:
                position = self.active_positions.pop(symbol)
                
                pnl_percent = ((close_price - position['entry_price']) / position['entry_price']) * 100
                if position['direction'] == 'Sell':
                    pnl_percent *= -1
                
                # --- [اصلاح شد] ---
                # روش صحیح برای ادغام دو دیکشنری در پایتون
                trade_result = {
                    **position, 
                    "close_price": close_price, 
                    "close_reason": reason,
                    "pnl_percent": pnl_percent, 
                    "close_time": close_time
                }
                self.closed_trades.append(trade_result)
                
                if self.backtest_mode:
                    result_icon = "🏆" if pnl_percent > 0 else " L "
                    print(f"{result_icon} [BACKTEST] Position Closed: {symbol} at {close_price:.2f} | Reason: {reason} | P&L: {pnl_percent:.2f}%")
                else:
                    if symbol in self.active_monitors:
                        self.active_monitors[symbol].on_position_closed()
                    self.send_info_alert(f"🔴 **پوزیشن {symbol} بسته شد** 🔴\nدلیل: {reason}\nسود/زیان: {pnl_percent:.2f}%")
    
    def check_and_update_positions(self, current_candle):
        """
        این متد در حالت بک‌تست برای هر کندل جدید فراخوانی می‌شود تا وضعیت پوزیشن‌ها را چک کند.
        """
        if not self.active_positions:
            return
            
        symbol = current_candle['symbol']
        if symbol in self.active_positions:
            position = self.active_positions[symbol]
            candle_low = current_candle['low']
            candle_high = current_candle['high']
            
            # --- [اصلاح شد] ---
            # ساختار شرطی برای Buy و Sell به درستی از هم جدا شد
            if position['direction'] == 'Buy':
                if candle_low <= position['stop_loss']:
                    self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit", current_candle['open_time'])
                elif candle_high >= position['tp1']:
                    self._close_position(symbol, position['tp1'], "Take-Profit 1 Hit", current_candle['open_time'])
            
            elif position['direction'] == 'Sell':
                if candle_high >= position['stop_loss']:
                    self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit", current_candle['open_time'])
                elif candle_low <= position['tp1']:
                    self._close_position(symbol, position['tp1'], "Take-Profit 1 Hit", current_candle['open_time'])
    
    def get_backtest_results(self):
        """نتایج نهایی بک‌تست را برمی‌گرداند."""
        total_trades = len(self.closed_trades)
        if total_trades == 0:
            return "No trades were executed."
        
        winning_trades = sum(1 for t in self.closed_trades if t['pnl_percent'] > 0)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        total_pnl = sum(t['pnl_percent'] for t in self.closed_trades)
        
        results = (
            f"\n{'='*25} BACKTEST RESULTS {'='*25}\n"
            f"Total Trades: {total_trades}\n"
            f"Winning Trades: {winning_trades}\n"
            f"Losing Trades: {losing_trades}\n"
            f"Win Rate: {win_rate:.2f}%\n"
            f"Total P&L (Percent): {total_pnl:.2f}%\n"
            f"{'='*68}"
        )
        return results

    def run_updater(self):
        """یک ترد جداگانه برای مدیریت پوزیشن‌های لایو اجرا می‌کند."""
        if self.backtest_mode:
            return
        thread = threading.Thread(target=self._position_update_loop, daemon=True)
        thread.start()

    def _position_update_loop(self):
        """
        حلقه اصلی مدیریت پوزیشن در حالت لایو.
        """
        while True:
            time.sleep(0.2)
            with self.lock:
                if not self.active_positions:
                    continue
                active_symbols = list(self.active_positions.keys())

            for symbol in active_symbols:
                if symbol in self.active_monitors:
                    monitor = self.active_monitors[symbol]
                    # فرض می‌کنیم قیمت لحظه‌ای از state_manager قابل دریافت است
                    last_price = monitor.state_manager.get_symbol_state(symbol, 'last_price')
                    if not last_price: continue

                    # این بخش می‌تواند با منطق بررسی استاپ‌های لحظه‌ای کامل‌تر شود
                    # در اینجا یک نمونه ساده برای SL/TP قرار داده شده است
                    self.check_and_update_positions({
                        'symbol': symbol, 'low': last_price, 'high': last_price, 
                        'open_time': datetime.now(timezone.utc)
                    })

    def send_info_alert(self, message):
        """پیام به تلگرام ارسال می‌کند."""
        if self.backtest_mode or not self.bot_token:
            return
        send_bulk_telegram_alert(message, self.bot_token, self.chat_ids)
            
    def get_open_positions(self):
        with self.lock:
            return list(self.active_positions.values())
            
    def get_daily_performance(self):
        with self.lock:
            # این یک پیاده‌سازی ساده است و می‌تواند با بررسی تاریخ معاملات کامل‌تر شود
            total_pnl = sum(t['pnl_percent'] for t in self.closed_trades if t['close_time'].date() == datetime.now().date())
            return {"daily_profit_percent": total_pnl, "drawdown_limit": self.risk_config["DAILY_DRAWDOWN_LIMIT_PERCENT"]}