# position_manager.py

import time
import threading
import asyncio
from datetime import datetime, timezone
import uuid
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# --- ایمپورت کردن تابع صحیح از alert.py ---
from alert import send_bulk_telegram_alert


def get_trading_session(utc_hour):
    """بر اساس ساعت جهانی (UTC)، سشن معاملاتی را برمی‌گرداند."""
    if 1 <= utc_hour < 8:
        return "Asian Session"
    elif 8 <= utc_hour < 16:
        return "London Session"
    elif 16 <= utc_hour < 23:
        return "New York Session"
    else:
        return "After Hours"

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
        """متن و دکمه‌های کارت پیشنهاد را بر اساس ریوارد انتخابی می‌سازد."""
        symbol = proposal_data['symbol']; direction = proposal_data['direction']
        entry_price = proposal_data['entry_price']; stop_loss = proposal_data['stop_loss']
        risk_amount = abs(entry_price - stop_loss)
        tp_price = entry_price + (risk_amount * selected_rr) if direction == 'Buy' else entry_price - (risk_amount * selected_rr)
        
        # آپدیت کردن قیمت TP در پیشنهاد ذخیره شده
        proposal_data['tp_price'] = tp_price
        proposal_data['current_rr'] = selected_rr
        
        reasons_str = "\n".join(proposal_data.get('reasons', ["-"]))
        # --- [اصلاح شد] --- فرمت نمایش اعداد به ۲ رقم اعشار تغییر کرد
        message_text = (f"**📣 پیشنهاد سیگنال جدید 📣**\n\n"
                        f"**ارز**: `{symbol}`\n"
                        f"**جهت**: {'🟢 خرید' if direction == 'Buy' else '🔴 فروش'}\n"
                        f"**سشن**: `{proposal_data.get('session', 'N/A')}`\n\n"
                        f"**دلایل:**\n{reasons_str}\n\n"
                        f"**جزئیات معامله (R/R: 1:{selected_rr}):**\n"
                        f" - قیمت ورود: `{entry_price:,.2f}`\n - حد ضرر: `{stop_loss:,.2f}`\n - حد سود: `{tp_price:,.2f}`\n\n"
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
        """یک کارت پیشنهاد معامله جدید دریافت کرده و آن را برای کاربر ارسال می‌کند."""
        entry_price = self.state_manager.get_symbol_state(signal_package['symbol'], 'last_price')
        if not entry_price: return
        
        # --- [اصلاح شد] --- استفاده از کلید صحیح 'stop_loss_suggestion'
        stop_loss = signal_package.get("stop_loss_suggestion")
        if not stop_loss: return # اگر حد ضرر مشخص نبود، سیگنال را نادیده بگیر
        
        proposal_id = f"{signal_package['symbol']}_{int(time.time())}"
        
        # --- [اصلاح شد] --- رفع خطای گرامری در ساخت دیکشنری
        proposal_data = {**signal_package, 'entry_price': entry_price, 'stop_loss': stop_loss}
        
        self.pending_proposals[proposal_id] = proposal_data
        message_text, reply_markup = self._build_proposal_message_and_keyboard(proposal_id, self.pending_proposals[proposal_id])
        
        sent_messages = self.send_info_alert(message_text, reply_markup)
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
                
                # محاسبه سود و زیان
                pnl = (close_price - position['entry_price']) if position['direction'] == 'Buy' else (position['entry_price'] - close_price)
                pnl_percent = (pnl / position['entry_price']) * 100 if position['entry_price'] != 0 else 0
                
                # محاسبه ریسک به ریوارد واقعی
                initial_risk_percent = abs(position['entry_price'] - position['stop_loss']) / position['entry_price'] * 100 if position['entry_price'] != 0 else 0
                realized_rr = pnl_percent / initial_risk_percent if initial_risk_percent != 0 else 0

                # --- [تغییر اصلی] --- ثبت کامل جزئیات معامله برای گزارش‌گیری
                trade_result = {
                    "symbol": symbol,
                    "direction": position.get('direction'),
                    "entry_price": position.get('entry_price'),
                    "close_price": close_price,
                    "stop_loss": position.get('stop_loss'),
                    "take_profit": position.get('take_profit'),
                    "entry_time": position.get('entry_time'),
                    "close_time": datetime.now(timezone.utc),
                    "close_reason": reason,
                    "setup_name": position.get('setup', 'Manual'), # نام ستاپ
                    "session": position.get('session', 'N/A'),     # سشن معاملاتی
                    "pnl_percent": pnl_percent,
                    "realized_rr": realized_rr,
                }
                self.closed_trades.append(trade_result)
                
                # برای ذخیره‌سازی دائمی، می‌توان این دیکشنری را در یک فایل CSV یا JSON ذخیره کرد.
                # (این قابلیت در فازهای بعدی اضافه خواهد شد)
                
                result_icon = "🏆" if pnl > 0 else "🔻"
                print(f"{result_icon} [TRADE CLOSED] Symbol: {symbol}, Reason: {reason}, P&L: {pnl_percent:+.2f}%")
                
                close_message = (f"{'✅' if pnl > 0 else '🔴'} **پوزیشن {symbol} بسته شد**\n\n"
                                f"دلیل: {reason}\n"
                                f"سود/زیان: **{pnl_percent:+.2f}%** (`R:R {realized_rr:.2f}`)")
                
                # فقط در صورتی که پیام از یک پیشنهاد سیگنال آمده باشد، آن را ویرایش کن
                if position.get('message_info'):
                    # این بخش برای آپدیت پیام کارت پیشنهاد است و صحیح است
                    pass # منطق فعلی آپدیت پیام در اینجا قرار می‌گیرد
                else:
                    self.send_info_alert(close_message)

    
    def check_positions_for_sl_tp(self):
        """وضعیت پوزیشن‌های باز را برای برخورد با حد سود یا ضرر بررسی می‌کند."""
        with self.lock:
            # از یک کپی استفاده می‌کنیم تا در حین حلقه، دیکشنری اصلی تغییر نکند
            active_positions_copy = list(self.active_positions.keys())
        
        for symbol in active_positions_copy:
            with self.lock:
                # وضعیت فعلی پوزیشن را دوباره چک می‌کنیم
                if symbol not in self.active_positions:
                    continue
                position = self.active_positions[symbol]
            
            price = self.state_manager.get_symbol_state(symbol, 'last_price')
            if not price: continue

            if position['direction'] == 'Buy':
                if price <= position['stop_loss']:
                    self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit")
                elif price >= position['take_profit']:
                    self._close_position(symbol, position['take_profit'], "Take-Profit Hit")
            elif position['direction'] == 'Sell':
                if price >= position['stop_loss']:
                    self._close_position(symbol, position['stop_loss'], "Stop-Loss Hit")
                elif price <= position['take_profit']:
                    self._close_position(symbol, position['take_profit'], "Take-Profit Hit")


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

    def _position_update_loop(self):
        """حلقه اصلی برای مدیریت پوزیشن‌های باز."""
        while True:
            time.sleep(5) # هر ۵ ثانیه چک می‌کند
            try:
                # --- [اصلاح شد] --- فراخوانی تابع جدید
                self.check_positions_for_sl_tp()
                # تابع آپدیت P&L نیز باید فراخوانی شود
                # این بخش نیاز به event loop دارد که از interactive_bot می‌آید
                if self.application and self.event_loop:
                    asyncio.run_coroutine_threadsafe(self.update_open_positions_pnl(), self.event_loop)
            except Exception as e:
                print(f"[POSITION_UPDATER_ERROR] {e}")
    

    def run_updater(self):
        threading.Thread(target=self._position_update_loop, daemon=True).start()

    def _position_update_loop(self):
        while True:
            time.sleep(5)
            try: self._check_and_update_live_positions()
            except Exception as e: print(f"[POSITION_UPDATER_ERROR] {e}")

    def get_daily_trade_report(self):
        """گزارش کامل معاملات بسته شده امروز را تولید می‌کند."""
        with self.lock:
            today = datetime.now(timezone.utc).date()
            todays_trades = [t for t in self.closed_trades if t.get('close_time') and t['close_time'].date() == today]
        
        if not todays_trades:
            return "امروز هیچ معامله بسته‌شده‌ای ثبت نشده است."
        
        wins = sum(1 for t in todays_trades if t['pnl_percent'] > 0)
        losses = len(todays_trades) - wins
        win_rate = (wins / len(todays_trades)) * 100 if todays_trades else 0
        total_pnl = sum(t['pnl_percent'] for t in todays_trades)

        report = (f"📈 **گزارش معاملات امروز** `({today.strftime('%Y-%m-%d')})` 📈\n\n"
                  f"**خلاصه عملکرد:**\n"
                  f"- کل معاملات: **{len(todays_trades)}**\n"
                  f"- معاملات سودده: **{wins}**\n"
                  f"- معاملات ضررده: **{losses}**\n"
                  f"- نرخ برد (Win Rate): **{win_rate:.1f}%**\n"
                  f"- سود/زیان خالص: **{total_pnl:+.2f}%**\n\n"
                  f"------------------------------------\n"
                  f"**لیست معاملات:**\n")
        
        for i, trade in enumerate(todays_trades):
            icon = "🟢" if trade['pnl_percent'] > 0 else "🔴"
            report += f"{i+1}. {icon} `{trade['symbol']}` ({trade['direction']}) | P&L: **{trade['pnl_percent']:.2f}%**\n"
        
        return report

    def get_open_positions(self):
        with self.lock:
            return list(self.active_positions.values())
        
    # --- [تابع تکمیل شده] ---
    def get_daily_performance(self):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            pnl_percent = sum(t.get('pnl_percent', 0) for t in self.closed_trades if t.get('close_time') and t['close_time'].date() == today)
            # در آینده می‌توان منطق محاسبه Drawdown را نیز اضافه کرد
            return {
                "daily_profit_percent": pnl_percent,
                "drawdown_limit": self.risk_config.get("DAILY_DRAWDOWN_LIMIT_PERCENT", 3.0)
            }
            
    def send_info_alert(self, message, reply_markup=None):
        if not self.bot_token:
            return []
        return send_bulk_telegram_alert(message, self.bot_token, self.chat_ids, reply_markup)

    # ==============================================================================
    # +++ توابع جدید برای بک‌تست و معاملات خودکار +++
    # ==============================================================================

    # در فایل: position_manager.py

    # در فایل: position_manager.py (این تابع را به انتهای کلاس اضافه کنید)

    def open_position_auto(self, symbol, direction, entry_price, sl, tp, setup_name):
        """
        یک پوزیشن را به صورت خودکار و بدون نیاز به تایید کاربر باز می‌کند.
        """
        with self.lock:
            if symbol in self.active_positions:
                print(f"[AUTO-TRADE] Skipping new position for {symbol} as one is already active.")
                return

            entry_time = datetime.now(timezone.utc)
            print(f"🤖 AUTO-TRADE ENGAGED: Opening {direction} position for {symbol} based on '{setup_name}' setup.")

            # استخراج سشن معاملاتی فعلی
            # فرض می‌کنیم تابعی به نام get_trading_session در این فایل یا فایل دیگری وجود دارد
            # اگر وجود ندارد، باید آن را اضافه کنیم. برای سادگی فعلا "N/A" قرار می‌دهیم.
            session = "N/A" # در آینده می‌توان این بخش را کامل کرد
            
            # ساخت آبجکت پوزیشن
            self.active_positions[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": sl,
                "take_profit": tp,
                "entry_time": entry_time,
                "setup_name": setup_name,
                "session": session,
                "message_info": []
            }

            # ارسال گزارش به تلگرام
            alert_message = (
                f"🤖 **پوزیشن خودکار باز شد** 🤖\n\n"
                f"**ارز:** `{symbol}`\n"
                f"**نوع:** `{'🟢 ' if direction == 'Buy' else '🔴 '}{direction}`\n"
                f"**قیمت ورود:** `{entry_price:,.2f}`\n"
                f"**حد ضرر:** `{sl:,.2f}`\n"
                f"**حد سود:** `{tp:,.2f}`\n"
                f"**استراتژی:** `{setup_name}`"
            )
            self.send_info_alert(alert_message)

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

    def open_manual_paper_trade(self, symbol, direction, entry_price):
        """یک پوزیشن پیپر تریدینگ را به صورت دستی باز می‌کند."""
        with self.lock:
            if symbol in self.active_positions:
                return f"❌ یک پوزیشن باز برای {symbol} از قبل وجود دارد."

            # برای معاملات دستی، حد ضرر و سود را فعلا خالی می‌گذاریم.
            # در آینده می‌توان این موارد را نیز از کاربر دریافت کرد.
            self.active_positions[symbol] = {
                "symbol": symbol,
                "direction": direction,
                "entry_price": entry_price,
                "stop_loss": 0, # فعلا بدون SL
                "take_profit": 0, # فعلا بدون TP
                "entry_time": datetime.now(timezone.utc),
                "message_info": [] # این پوزیشن پیام قابل ویرایش ندارد
            }
            
            alert_message = (
                f"✍️ **پوزیشن دستی باز شد** ✍️\n\n"
                f"**ارز:** `{symbol}`\n"
                f"**جهت:** `{'🟢 خرید' if direction == 'Buy' else '🔴 فروش'}`\n"
                f"**قیمت ورود:** `{entry_price:,.2f}`"
            )
            self.send_info_alert(alert_message)
            print(f"[MANUAL TRADE] Position opened for {symbol} at {entry_price}")
            return f"✅ پوزیشن دستی {direction} برای {symbol} با موفقیت باز شد."