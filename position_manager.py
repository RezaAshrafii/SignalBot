# position_manager.py

import time
import threading
import asyncio
from datetime import datetime, timezone
import uuid
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# --- ایمپورت کردن تابع صحیح از alert.py ---
from alert import send_bulk_telegram_alert

class PositionManager:
    # --- [اصلاح شد] --- پارامتر backtest_mode به عنوان ورودی اختیاری
    def __init__(self, state_manager, bot_token, chat_ids, risk_config, active_monitors, backtest_mode=False):
        self.state_manager = state_manager
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.risk_config = risk_config
        self.active_monitors = active_monitors
        self.lock = threading.Lock()
        self.paper_balance = 10000.0
        self.active_positions = {}
        self.closed_trades = []
        self.pending_proposals = {}
        self.application = None
        self.event_loop = None
        self.backtest_mode = backtest_mode
        if self.backtest_mode:
            print("PositionManager is running in BACKTEST MODE.")

    def set_application_and_loop(self, application, loop):
        self.application = application
        self.event_loop = loop

    def _build_proposal_message_and_keyboard(self, proposal_id, proposal_data, selected_rr=2):
        symbol = proposal_data['symbol']; direction = proposal_data['direction']
        entry_price = proposal_data['entry_price']; stop_loss = proposal_data['stop_loss']
        risk_amount = abs(entry_price - stop_loss)
        tp_price = entry_price + (risk_amount * selected_rr) if direction == 'Buy' else entry_price - (risk_amount * selected_rr)
        
        proposal_data['tp_price'] = tp_price
        proposal_data['current_rr'] = selected_rr
        
        reasons_str = "\n".join(proposal_data.get('reasons', ["-"]))
        message_text = (f"**📣 پیشنهاد سیگنال جدید �**\n\n"
                        f"**ارز**: `{symbol}`\n"
                        f"**جهت**: {'🟢 خرید' if direction == 'Buy' else '🔴 فروش'}\n"
                        f"**سشن**: `{proposal_data.get('session', 'N/A')}`\n\n"
                        f"**دلایل:**\n{reasons_str}\n\n"
                        f"**جزئیات معامله (R/R: 1:{selected_rr}):**\n"
                        f" - قیمت ورود: `{entry_price:,.4f}`\n - حد ضرر: `{stop_loss:,.4f}`\n - حد سود: `{tp_price:,.4f}`\n\n"
                        f"**سود/زیان لحظه‌ای: `-`**")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید ورود", callback_data=f"confirm:{proposal_id}"), InlineKeyboardButton("❌ رد کردن", callback_data=f"reject:{proposal_id}")],
            [
                InlineKeyboardButton(f"R/R: 1{' ✅' if selected_rr==1 else ''}", callback_data=f"set_rr:{proposal_id}:1"),
                InlineKeyboardButton(f"R/R: 2{' ✅' if selected_rr==2 else ''}", callback_data=f"set_rr:{proposal_id}:2"),
                InlineKeyboardButton(f"R/R: 3{' ✅' if selected_rr==3 else ''}", callback_data=f"set_rr:{proposal_id}:3")
            ]
        ])
        return message_text, keyboard

    def on_new_proposal(self, signal_package):
        entry_price = self.state_manager.get_symbol_state(signal_package['symbol'], 'last_price')
        if not entry_price: return
        stop_loss = signal_package.get("stop_loss") or (entry_price * 0.995 if signal_package['type'] == "Buy" else entry_price * 1.005)
        
        proposal_id = f"{signal_package['symbol']}_{int(time.time())}"
        proposal_data = {
            **signal_package, 
            'entry_price': entry_price, 
            'stop_loss': stop_loss,
            'direction': signal_package.get('type')
        }
        self.pending_proposals[proposal_id] = proposal_data
        message_text, reply_markup = self._build_proposal_message_and_keyboard(proposal_id, self.pending_proposals[proposal_id])
        
        # --- استفاده از تابع صحیح برای ارسال پیام ---
        # نکته: to_dict() برای InlineKeyboardMarkup در نسخه‌های جدید python-telegram-bot ممکن است نیاز باشد
        sent_messages = send_bulk_telegram_alert(message_text, self.bot_token, self.chat_ids, reply_markup.to_dict() if hasattr(reply_markup, 'to_dict') else reply_markup)
        
        if sent_messages:
            self.pending_proposals[proposal_id]['message_info'] = [{'chat_id': m.chat.id, 'message_id': m.message_id} for m in sent_messages if m]

    def update_proposal_rr(self, proposal_id, rr_value):
        with self.lock:
            if proposal_id not in self.pending_proposals: return None, None
            return self._build_proposal_message_and_keyboard(proposal_id, self.pending_proposals[proposal_id], selected_rr=int(rr_value))

    def confirm_paper_trade(self, proposal_id, chat_id, message_id):
        with self.lock:
            if proposal_id not in self.pending_proposals: return "این پیشنهاد منقضی شده است."
            proposal = self.pending_proposals.pop(proposal_id); symbol = proposal['symbol']
            if symbol in self.active_positions: return f"یک پوزیشن باز برای {symbol} از قبل وجود دارد."
            
            self.active_positions[symbol] = {"symbol": symbol, "direction": proposal['direction'], "entry_price": proposal['entry_price'], "stop_loss": proposal['stop_loss'], "take_profit": proposal.get('tp_price', 0), "entry_time": datetime.now(timezone.utc), "message_info": [{'chat_id': chat_id, 'message_id': message_id}]}
            print(f"[PAPER TRADE] Position opened for {symbol}"); return f"✅ معامله مجازی **{proposal['direction']} {symbol}** باز شد."

    def reject_proposal(self, proposal_id):
        with self.lock:
            if proposal_id in self.pending_proposals: self.pending_proposals.pop(proposal_id)
            return "❌ پیشنهاد معامله رد شد."

    def log_feedback(self, proposal_id, feedback):
        feedback_log_message = f"Feedback for proposal {proposal_id}: {feedback}"
        print(f"[FEEDBACK] {feedback_log_message}")
        with open("feedback_log.txt", "a") as f: f.write(f"{datetime.now(timezone.utc).isoformat()} | {feedback_log_message}\n")

    def _close_position(self, symbol, close_price, reason):
        with self.lock:
            if symbol in self.active_positions:
                position = self.active_positions.pop(symbol)
                pnl = (close_price - position['entry_price']) if position['direction'] == 'Buy' else (position['entry_price'] - close_price)
                pnl_percent = (pnl / position['entry_price']) * 100 if position['entry_price'] != 0 else 0
                self.paper_balance += pnl 
                
                # --- [اصلاح شد] --- تبدیل entry_time و close_time به آبجکت datetime
                entry_time = position['entry_time']
                if not isinstance(entry_time, datetime):
                     entry_time = datetime.now(timezone.utc) # Fallback

                trade_result = {
                    "symbol": symbol,
                    "direction": position.get('direction'),
                    "entry_price": position['entry_price'],
                    "close_price": close_price, 
                    "close_reason": reason, 
                    "pnl_percent": pnl_percent, 
                    "pnl_usd": pnl, 
                    "entry_time": entry_time,
                    "close_time": datetime.now(timezone.utc)
                }
                self.closed_trades.append(trade_result)
                
                result_icon = "🏆" if pnl > 0 else " L "
                print(f"{result_icon} [PAPER TRADE] Position Closed: {symbol} at {close_price:.2f} | P&L: ${pnl:.2f} ({pnl_percent:.2f}%)")
                
                close_message = f"{'✅' if pnl > 0 else '🔴'} **پوزیشن {symbol} بسته شد**\n\n" \
                                f"دلیل: {reason}\n" \
                                f"سود/زیان: **{pnl_percent:+.2f}%**"
                send_bulk_telegram_alert(close_message, self.bot_token, self.chat_ids)

    def _check_and_update_live_positions(self):
        with self.lock:
            active_positions_copy = list(self.active_positions.values())
        
        for pos in active_positions_copy:
            symbol = pos['symbol']
            price = self.state_manager.get_symbol_state(symbol, 'last_price')
            if not price: continue

            if pos['direction'] == 'Buy':
                if price <= pos['stop_loss']: self._close_position(symbol, pos['stop_loss'], "Stop-Loss Hit")
                elif price >= pos['take_profit']: self._close_position(symbol, pos['take_profit'], "Take-Profit Hit")
            elif pos['direction'] == 'Sell':
                if price >= pos['stop_loss']: self._close_position(symbol, pos['stop_loss'], "Stop-Loss Hit")
                elif price <= pos['take_profit']: self._close_position(symbol, pos['take_profit'], "Take-Profit Hit")
            
            if symbol in self.active_positions:
                self._update_pnl_message(position=pos, last_price=price)

    def _update_pnl_message(self, position, last_price):
        if self.application is None or self.event_loop is None: return
        pnl = (last_price - position['entry_price']) if position['direction'] == 'Buy' else (position['entry_price'] - last_price)
        pnl_percent = (pnl / position['entry_price']) * 100 if position['entry_price'] != 0 else 0
        pnl_text = f"**سود/زیان لحظه‌ای: `${pnl:,.2f}` ({pnl_percent:+.2f}%)**"
        updated_text = (f"**معامله فعال: {position['direction']} {position['symbol']}**\n\n"
                        f"قیمت ورود: `{position['entry_price']:,.2f}`\nحد ضرر: `{position['stop_loss']:,.2f}`\n"
                        f"حد سود: `{position['take_profit']:,.2f}`\n\n{pnl_text}")
        
        for info in position.get('message_info', []):
            coro = self.application.bot.edit_message_text(chat_id=info['chat_id'], message_id=info['message_id'], text=updated_text, parse_mode='Markdown')
            asyncio.run_coroutine_threadsafe(coro, self.event_loop)

    def run_updater(self):
        threading.Thread(target=self._position_update_loop, daemon=True).start()

    def _position_update_loop(self):
        while True:
            time.sleep(5)
            try: self._check_and_update_live_positions()
            except Exception as e: print(f"[POSITION_UPDATER_ERROR] {e}")

    def get_daily_trade_report(self):
        # ... (کد شما بدون تغییر) ...
        pass
        
    def get_open_positions(self):
        with self.lock: return list(self.active_positions.values())
        
    def get_daily_performance(self):
        # ... (کد شما بدون تغییر) ...
        pass

    # ==============================================================================
    # +++ توابع جدید برای بک‌تست و معاملات خودکار +++
    # ==============================================================================

    def open_position_auto(self, symbol, direction, entry_price, sl, tp, setup_name):
        """
        یک پوزیشن را به صورت خودکار و بدون نیاز به تایید کاربر باز می‌کند.
        این تابع مخصوص استفاده در اسکریپت بک‌تست (auto_trade.py) است.
        """
        with self.lock:
            if symbol in self.active_positions:
                # print(f"یک پوزیشن باز برای {symbol} از قبل وجود دارد.")
                return

            print(f"AUTO TRADE: Position opened for {symbol} ({direction})")
            
            # ساختن آبجکت پوزیشن
            self.active_positions[symbol] = {
                "symbol": symbol,
                "direction": direction, # 'Buy' or 'Sell'
                "entry_price": entry_price,
                "stop_loss": sl,
                "take_profit": tp,
                "entry_time": self.state_manager.get_current_time(), # فرض بر وجود این تابع
                "setup_name": setup_name,
                "message_info": [] # در حالت خودکار، پیام قابل ویرایش نداریم
            }

            # ارسال گزارش به تلگرام
            alert_message = (
                f"🤖 **پوزیشن خودکار باز شد** 🤖\n\n"
                f"**ارز:** `{symbol}`\n"
                f"**نوع:** `{'🟢 ' if direction == 'Buy' else '🔴 '}{direction}`\n"
                f"**قیمت ورود:** `{entry_price}`\n"
                f"**حد ضرر:** `{sl}`\n"
                f"**حد سود:** `{tp}`\n"
                f"**استراتژی:** `{setup_name}`"
            )
            send_bulk_telegram_alert(alert_message, self.bot_token, self.chat_ids)

    def close_all_positions(self):
        """تمام پوزیشن‌های باز را در انتهای بک‌تست می‌بندد."""
        print("در حال بستن تمام پوزیشن‌های باقی‌مانده در انتهای بک‌تست...")
        with self.lock:
            # از یک کپی از کلیدها استفاده می‌کنیم تا در حین حلقه، دیکشنری تغییر نکند
            for symbol in list(self.active_positions.keys()):
                # از آخرین قیمت موجود در state_manager برای بستن استفاده می‌کنیم
                close_price = self.state_manager.get_current_price()
                if close_price:
                    self._close_position(symbol, close_price, "End of Backtest")
