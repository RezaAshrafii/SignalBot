# position_manager.py
import time, threading, asyncio
from datetime import datetime, timezone
from alert import send_bulk_telegram_alert
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

class PositionManager:
    def __init__(self, state_manager, bot_token, chat_ids, risk_config, active_monitors):
        self.state_manager = state_manager; self.bot_token = bot_token; self.chat_ids = chat_ids
        self.risk_config = risk_config; self.active_monitors = active_monitors
        self.lock = threading.Lock(); self.paper_balance = 10000.0
        self.active_positions = {}; self.closed_trades = []; self.pending_proposals = {}
        self.application = None

    def log_feedback(self, proposal_id, feedback):
        """بازخورد کاربر را در یک فایل یا کنسول ثبت می‌کند."""
        # در یک سیستم واقعی، این می‌تواند در یک دیتابیس یا فایل CSV ذخیره شود
        feedback_log_message = f"Feedback received for proposal {proposal_id}: {feedback}"
        print(f"[FEEDBACK] {feedback_log_message}")
        with open("feedback_log.txt", "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {feedback_log_message}\n")


    def set_application(self, application): self.application = application
    def _build_proposal_message_and_keyboard(self, proposal_id, proposal_data, selected_rr=2):
        symbol = proposal_data['symbol']; direction = proposal_data['direction']; entry_price = proposal_data['entry_price']; stop_loss = proposal_data['stop_loss']
        risk_amount = abs(entry_price - stop_loss)
        tp_price = entry_price + (risk_amount * selected_rr) if direction == 'Buy' else entry_price - (risk_amount * selected_rr)
        proposal_data['tp_price'] = tp_price; proposal_data['current_rr'] = selected_rr
        reasons_str = "\n".join(proposal_data.get('reasons', []))
        message_text = (f"**📣 پیشنهاد سیگنال جدید 📣**\n\n"
                        f"**ارز**: `{symbol}`\n"
                        f"**جهت**: {'🟢 خرید' if direction == 'Buy' else '🔴 فروش'}\n"
                        f"**سشن**: `{proposal_data.get('session', 'N/A')}`\n\n"
                        f"**دلایل:**\n{reasons_str}\n\n"
                        f"**جزئیات معامله (R/R: 1:{selected_rr}):**\n"
                        f"  - قیمت ورود: `{entry_price:,.2f}`\n  - حد ضرر: `{stop_loss:,.2f}`\n  - حد سود: `{tp_price:,.2f}`\n\n"
                        f"**سود/زیان لحظه‌ای: `-`**")
        keyboard = [[InlineKeyboardButton("✅ تایید ورود", callback_data=f"confirm:{proposal_id}"), InlineKeyboardButton("❌ رد کردن", callback_data=f"reject:{proposal_id}")],
                    [InlineKeyboardButton(f"R/R: 1{' ✅' if selected_rr==1 else ''}", callback_data=f"set_rr:{proposal_id}:1"),
                     InlineKeyboardButton(f"R/R: 2{' ✅' if selected_rr==2 else ''}", callback_data=f"set_rr:{proposal_id}:2"),
                     InlineKeyboardButton(f"R/R: 3{' ✅' if selected_rr==3 else ''}", callback_data=f"set_rr:{proposal_id}:3")]]
        return message_text, InlineKeyboardMarkup(keyboard)

    def on_new_proposal(self, signal_package):
        entry_price = self.state_manager.get_symbol_state(signal_package['symbol'], 'last_price')
        if not entry_price: return
        stop_loss = signal_package.get("stop_loss_suggestion") or (entry_price * 0.995 if signal_package['direction'] == "Buy" else entry_price * 1.005)
        proposal_id = f"{signal_package['symbol']}_{int(time.time())}"
        self.pending_proposals[proposal_id] = {**signal_package, 'entry_price': entry_price, 'stop_loss': stop_loss}
        message_text, reply_markup = self._build_proposal_message_and_keyboard(proposal_id, self.pending_proposals[proposal_id])
        sent_messages = self.send_info_alert(message_text, reply_markup)
        if sent_messages: self.pending_proposals[proposal_id]['message_info'] = [{'chat_id': m.chat.id, 'message_id': m.message_id} for m in sent_messages if m]

    def update_proposal_rr(self, proposal_id, rr_value):
        with self.lock:
            if proposal_id not in self.pending_proposals: return None, None
            return self._build_proposal_message_and_keyboard(proposal_id, self.pending_proposals[proposal_id], selected_rr=int(rr_value))

    def confirm_paper_trade(self, proposal_id, chat_id, message_id):
        with self.lock:
            if proposal_id not in self.pending_proposals: return "این پیشنهاد منقضی شده است."
            proposal = self.pending_proposals.pop(proposal_id)
            symbol = proposal['symbol']
            if symbol in self.active_positions: return f"یک پوزیشن باز برای {symbol} از قبل وجود دارد."
            self.active_positions[symbol] = {"symbol": symbol, "direction": proposal['direction'], "entry_price": proposal['entry_price'], "stop_loss": proposal['stop_loss'], "take_profit": proposal.get('tp_price', 0), "entry_time": datetime.now(timezone.utc), "message_info": [{'chat_id': chat_id, 'message_id': message_id}]}
            print(f"[PAPER TRADE] Position opened for {symbol}"); return f"✅ معامله مجازی **{proposal['direction']} {symbol}** باز شد."

    def reject_proposal(self, proposal_id):
        with self.lock:
            if proposal_id in self.pending_proposals: self.pending_proposals.pop(proposal_id)
            return "❌ پیشنهاد معامله رد شد."
    
    def _close_position(self, symbol, close_price, reason):
        with self.lock:
            if symbol in self.active_positions:
                position = self.active_positions.pop(symbol)
                pnl = (close_price - position['entry_price']) if position['direction'] == 'Buy' else (position['entry_price'] - close_price)
                pnl_percent = (pnl / position['entry_price']) * 100
                trade_result = {**position, "close_price": close_price, "close_reason": reason, "pnl_percent": pnl_percent, "pnl_usd": pnl, "close_time": datetime.now(timezone.utc)}
                self.closed_trades.append(trade_result)
                result_icon = "🏆" if pnl > 0 else " L "
                print(f"{result_icon} [PAPER TRADE] Position Closed: {symbol} at {close_price:.2f} | P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")

    async def check_positions_for_sl_tp(self, state_manager):
        with self.lock: active_positions_copy = list(self.active_positions.values())
        for pos in active_positions_copy:
            price = state_manager.get_symbol_state(pos['symbol'], 'last_price')
            if not price: continue
            if pos['direction'] == 'Buy' and price <= pos['stop_loss']: self._close_position(pos['symbol'], pos['stop_loss'], "Stop-Loss Hit")
            elif pos['direction'] == 'Buy' and price >= pos['take_profit']: self._close_position(pos['symbol'], pos['take_profit'], "Take-Profit Hit")
            elif pos['direction'] == 'Sell' and price >= pos['stop_loss']: self._close_position(pos['symbol'], pos['stop_loss'], "Stop-Loss Hit")
            elif pos['direction'] == 'Sell' and price <= pos['take_profit']: self._close_position(pos['symbol'], pos['take_profit'], "Take-Profit Hit")
            
    async def update_open_positions_pnl(self):
        if self.application is None or not self.active_positions: return
        with self.lock: active_positions_copy = list(self.active_positions.values())
        for position in active_positions_copy:
            price = self.state_manager.get_symbol_state(position['symbol'], 'last_price')
            if not price: continue
            pnl = (price - position['entry_price']) if position['direction'] == 'Buy' else (position['entry_price'] - price)
            pnl_percent = (pnl / position['entry_price']) * 100
            pnl_text = f"**سود/زیان لحظه‌ای: `${pnl:,.2f}` ({pnl_percent:+.2f}%)**"
            updated_text = f"**معامله فعال: {position['direction']} {position['symbol']}**\n\n" \
                           f"قیمت ورود: `{position['entry_price']:,.2f}`\nحد ضرر: `{position['stop_loss']:,.2f}`\nحد سود: `{position['take_profit']:,.2f}`\n\n{pnl_text}"
            for info in position.get('message_info', []):
                try: await self.application.bot.edit_message_text(chat_id=info['chat_id'], message_id=info['message_id'], text=updated_text, parse_mode='Markdown')
                except Exception: pass
    
    def get_daily_trade_report(self):
        """گزارش کامل معاملات بسته شده امروز را تولید می‌کند."""
        with self.lock:
            today = datetime.now(timezone.utc).date()
            todays_trades = [t for t in self.closed_trades if t.get('close_time') and t['close_time'].date() == today]
        
        if not todays_trades: return "امروز هیچ معامله بسته‌شده‌ای ثبت نشده است."
        
        wins = sum(1 for t in todays_trades if t['pnl_percent'] > 0)
        losses = len(todays_trades) - wins
        win_rate = (wins / len(todays_trades)) * 100 if todays_trades else 0
        total_pnl = sum(t['pnl_percent'] for t in todays_trades)

        report = f"📈 **گزارش معاملات امروز** `({today.strftime('%Y-%m-%d')})` 📈\n\n" \
                 f"**خلاصه عملکرد:**\n" \
                 f"- تعداد کل معاملات: **{len(todays_trades)}**\n" \
                 f"- معاملات سودده: **{wins}**\n" \
                 f"- معاملات ضررده: **{losses}**\n" \
                 f"- نرخ برد (Win Rate): **{win_rate:.1f}%**\n" \
                 f"- سود/زیان خالص: **{total_pnl:+.2f}%**\n\n" \
                 f"------------------------------------\n" \
                 f"**لیست معاملات:**\n"
        
        for i, trade in enumerate(todays_trades):
            icon = "🟢" if trade['pnl_percent'] > 0 else "🔴"
            report += f"{i+1}. {icon} `{trade['symbol']}` ({trade['direction']}) | P&L: **{trade['pnl_percent']:.2f}%**\n"
        
        return report

    def get_open_positions(self):
        with self.lock: return list(self.active_positions.values())
    def get_daily_performance(self):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            pnl = sum(t.get('pnl_percent', 0) for t in self.closed_trades if t.get('close_time') and t['close_time'].date() == today)
            return {"daily_profit_percent": pnl, "drawdown_limit": self.risk_config.get("DAILY_DRAWDOWN_LIMIT_PERCENT", 3.0)}
    def send_info_alert(self, message, reply_markup=None):
        if not self.bot_token: return []
        return send_bulk_telegram_alert(message, self.bot_token, self.chat_ids, reply_markup)