import threading, asyncio, traceback
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import chart_generator
from indicators import calculate_atr
from trend_analyzer import generate_master_trend_report

# --- کلاس اصلی ربات ---
class InteractiveBot:
    def __init__(self, token, state_manager):
        print("[InteractiveBot] Initializing...")
        self.application = Application.builder().token(token).build()
        self.state_manager = state_manager
        # --- [اصلاح شد] --- position_manager در اینجا None است و بعداً تنظیم می‌شود
        self.position_manager = None 
        
        self.main_menu_keyboard = [
            ['/trend روند روز', '/suggestion پیشنهاد سیگنال'],
            [r'/levels سطوح نزدیک (چارت)', '📈 پوزیشن‌های باز'],
            ['💰 عملکرد روزانه', '/report گزارش روزانه'],
            ['🔇/🔊 حالت سکوت']
        ]
        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        self.register_handlers()
        print("[InteractiveBot] Initialization complete.")

    def set_position_manager(self, position_manager):
        """
        این متد برای حل مشکل وابستگی چرخه‌ای، position_manager را بعد از ساخت تنظیم می‌کند.
        """
        self.position_manager = position_manager

    def register_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 پوزیشن‌های باز$'), self.handle_open_positions))
        self.application.add_handler(MessageHandler(filters.Regex('^💰 عملکرد روزانه$'), self.handle_daily_performance))
        self.application.add_handler(CommandHandler('levels', self.handle_nearby_levels_chart))
        self.application.add_handler(MessageHandler(filters.Regex(r'^\/levels سطوح نزدیک \(چارت\)$'), self.handle_nearby_levels_chart))
        self.application.add_handler(CommandHandler('report', self.handle_report))
        self.application.add_handler(MessageHandler(filters.Regex('^/report گزارش روزانه$'), self.handle_report))
        self.application.add_handler(CommandHandler('trend', self.handle_trend_report))
        self.application.add_handler(MessageHandler(filters.Regex('^/trend روند روز$'), self.handle_trend_report))
        self.application.add_handler(CommandHandler('suggestion', self.handle_signal_suggestion))
        self.application.add_handler(MessageHandler(filters.Regex('^/suggestion پیشنهاد سیگنال$'), self.handle_signal_suggestion))
        self.application.add_handler(MessageHandler(filters.Regex('^🔇/🔊 حالت سکوت$'), self.handle_toggle_silent_mode))
        self.application.add_handler(CallbackQueryHandler(self.handle_button_clicks))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"سلام {user_name} عزیز!\n\nربات معامله‌گر فعال است.", reply_markup=self.main_menu_markup)

    async def handle_button_clicks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پاسخ به کلیک کاربر روی تمام دکمه‌های شیشه‌ای."""
        query = update.callback_query
        await query.answer()
        
        # --- [اصلاح شد] --- بررسی می‌کنیم position_manager قبل از استفاده تنظیم شده باشد
        if not self.position_manager:
            print("[ERROR] PositionManager not set in InteractiveBot.")
            await query.edit_message_text(text="خطا: مدیر پوزیشن هنوز آماده به کار نیست.", reply_markup=None)
            return

        try:
            parts = query.data.split(":")
            action = parts[0]
            proposal_id = parts[1] if len(parts) > 1 else None

            if action in ['confirm', 'reject']:
                original_text = query.message.text_markdown.split("\n\n**سود/زیان لحظه‌ای:")[0]
                response_text = ""
                if action == 'confirm':
                    response_text = self.position_manager.confirm_paper_trade(proposal_id, query.message.chat_id, query.message.message_id)
                else: # reject
                    response_text = self.position_manager.reject_proposal(proposal_id)
                
                await query.edit_message_text(text=f"{original_text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=None)
                
                feedback_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👍 سیگنال خوب بود", callback_data=f"feedback:{proposal_id}:good"), InlineKeyboardButton("👎 سیگنال بد بود", callback_data=f"feedback:{proposal_id}:bad")]])
                await context.bot.send_message(chat_id=query.message.chat_id, text="لطفاً کیفیت این پیشنهاد را ارزیابی کنید:", reply_markup=feedback_keyboard)

            elif action == 'set_rr':
                rr_value = parts[2]
                new_text, new_keyboard = self.position_manager.update_proposal_rr(proposal_id, rr_value)
                if new_text and new_keyboard: await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode='Markdown')
            
            elif action == 'feedback':
                feedback = parts[2]
                self.position_manager.log_feedback(proposal_id, feedback)
                await query.edit_message_text(text=f"{query.message.text}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)

        except Exception as e: 
            print(f"[CALLBACK_HANDLER_ERROR] {e}")
            traceback.print_exc()

    async def handle_toggle_silent_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_silent = self.state_manager.get_symbol_state('__app__', 'is_silent')
        self.state_manager.update_symbol_state('__app__', 'is_silent', not is_silent)
        await update.message.reply_text(f"🔇 حالت سکوت **{'فعال' if not is_silent else 'غیرفعال'}** شد.")

    async def handle_nearby_levels_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال آماده‌سازی چارت، لطفاً چند لحظه صبر کنید...")
        for symbol in self.state_manager.get_all_symbols():
            klines = self.state_manager.get_symbol_state(symbol, 'klines_1m')
            # --- [اصلاح شد] --- استفاده از نام صحیح تابع get_full_symbol_state
            state = self.state_manager.get_full_symbol_state(symbol)
            current_price, levels = state.get('last_price'), state.get('untouched_levels', [])
            
            if not klines or not isinstance(klines, list) or not levels:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"داده کافی برای رسم چارت {symbol} وجود ندارد."); continue
            
            nearby_levels = [lvl for lvl in levels if abs(lvl['level'] - current_price) / current_price * 100 <= 2.0]
            if not nearby_levels: continue
            
            caption = f"🔑 **سطوح کلیدی نزدیک به قیمت فعلی برای {symbol}**"
            # فرض می‌کنیم chart_generator این تابع را دارد
            image_buffer = chart_generator.generate_chart_image(klines, nearby_levels, current_price, symbol)
            if image_buffer: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_buffer, caption=caption, parse_mode='Markdown')

    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions: 
            await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown'); return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            message += f"▶️ **{pos.get('symbol')} - {pos.get('direction', '').upper()}**\n - قیمت ورود: `{pos.get('entry_price', 0):,.2f}`\n - حد ضرر: `{pos.get('stop_loss', 0):,.2f}`\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance()
        profit = performance.get('daily_profit_percent', 0.0)
        limit = performance.get('drawdown_limit', 0.0)
        profit_str = f"+{profit:.2f}%" if profit >= 0 else f"{profit:.2f}%"
        await update.message.reply_text(f"💰 **عملکرد روزانه**\n\n▫️ سود / زیان امروز:  **{profit_str}**\n▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n", parse_mode='Markdown')
        
    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        report_string = self.position_manager.get_daily_trade_report()
        await update.message.reply_text(report_string, parse_mode='Markdown')

    async def handle_trend_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """گزارش تحلیلی روند را به صورت لحظه‌ای تولید و نمایش می‌دهد."""
        await update.message.reply_text("در حال تحلیل لحظه‌ای روند، لطفاً صبر کنید...")
        message = "📝 **گزارش تحلیل روند روزانه (لحظه‌ای)**\n"
        
        # برای هر ارز یک گزارش کامل تولید کرده و به پیام نهایی اضافه می‌کند
        for symbol in self.state_manager.get_all_symbols():
            try:
                # تابع صحیح با آرگومان‌های صحیح فراخوانی می‌شود.
                # این تابع خودش داده‌های لازم را دریافت و تحلیل می‌کند.
                final_trend, trend_report = generate_master_trend_report(symbol, self.state_manager)
                
                # وضعیت روند در state_manager آپدیت می‌شود
                self.state_manager.update_symbol_state(symbol, 'htf_trend', final_trend)
                
                message += f"\n--- **{symbol}** ---\n{trend_report}\n"

            except Exception as e:
                # در صورت بروز خطا برای یک ارز، آن را گزارش کرده و به سراغ بعدی می‌رود
                message += f"\n--- **{symbol}** ---\n⚠️ خطا در تحلیل روند: {e}\n"
                print(f"Failed to generate trend report for {symbol}: {e}")
                
        # در انتها، پیام کامل و جامع برای کاربر ارسال می‌شود
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_signal_suggestion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بر اساس روند، بهترین نواحی برای ورود را با جزئیات کامل پیشنهاد می‌دهد."""
        # --- [اصلاح شد] --- پیام اولیه را ذخیره می‌کنیم تا بتوانیم آن را ویرایش کنیم
        sent_message = await update.message.reply_text("در حال آماده‌سازی پیشنهادهای استراتژیک...")
        message = "🎯 **پیشنهادهای استراتژیک روز**\n"
        
        for symbol in self.state_manager.get_all_symbols():
            trend = self.state_manager.get_symbol_state(symbol, 'htf_trend')
            if not trend or trend == 'PENDING':
                # اگر روند محاسبه نشده بود، ابتدا آن را محاسبه می‌کنیم
                _, trend_report = generate_master_trend_report(symbol, self.state_manager)
                trend = self.state_manager.get_symbol_state(symbol, 'htf_trend')
            levels = self.state_manager.get_symbol_state(symbol, 'untouched_levels')
            klines = self.state_manager.get_symbol_state(symbol, 'klines_1m')
            level_tests = self.state_manager.get_symbol_state(symbol, 'level_test_counts') or {}
            
            if not trend or not levels or trend == "INSUFFICIENT_DATA": continue
            
            message += f"\n--- **{symbol}** (روند: **{trend}**) ---\n"
            
            if klines and isinstance(klines, list) and len(klines) > 14:
                atr = calculate_atr(pd.DataFrame(klines))
                last_price = self.state_manager.get_symbol_state(symbol, 'last_price')
                if last_price and atr < last_price * 0.001:
                    message += "⚠️ **هشدار**: نوسانات بازار در حال حاضر پایین است.\n"

            if "UP" in trend:
                suggestion = "در سطوح **حمایتی** زیر به دنبال تاییدیه **خرید** باشید:\n"
                relevant_levels = [lvl for lvl in levels if lvl['level_type'] in ['PDL', 'VAL', 'POC'] or 'low' in lvl['level_type'].lower()]
            elif "DOWN" in trend:
                suggestion = "در سطوح **مقاومتی** زیر به دنبال تاییدیه **فروش** باشید:\n"
                relevant_levels = [lvl for lvl in levels if lvl['level_type'] in ['PDH', 'VAH', 'POC'] or 'high' in lvl['level_type'].lower()]
            else:
                suggestion = "روند خنثی است. معامله با احتیاط توصیه می‌شود.\n"; relevant_levels = []
            
            if not relevant_levels: suggestion += "سطح مناسبی برای معامله یافت نشد.\n"
            
            message += suggestion
            relevant_levels.sort(key=lambda x: x['level'], reverse=True)
            for lvl in relevant_levels:
                test_count = level_tests.get(str(lvl['level']), 0)
                message += f"  - `{lvl['level_type']}` در `{lvl['level']:,.2f}` (تست شده: `{test_count}` بار)\n"
                        
        await context.bot.edit_message_text(text=message, chat_id=sent_message.chat_id, message_id=sent_message.message_id, parse_mode='Markdown')


    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست.")

    def _runner(self):
        """این تابع، حلقه رویداد را برای ترد جدید مدیریت می‌کند."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if hasattr(self.position_manager, 'set_application_and_loop') and self.position_manager:
                self.position_manager.set_application_and_loop(self.application, loop)
            loop.run_until_complete(self.application.run_polling(stop_signals=None))
        except Exception:
            print("!!! CRITICAL ERROR IN INTERACTIVE BOT THREAD !!!")
            traceback.print_exc()

    def run(self):
        """ربات را در یک ترد جداگانه اجرا می‌کند."""
        print("Starting interactive bot in a separate thread...")
        threading.Thread(target=self._runner, daemon=True, name="InteractiveBotThread").start()