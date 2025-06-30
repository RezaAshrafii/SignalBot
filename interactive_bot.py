import threading, asyncio, traceback
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytz
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, ConversationHandler  # <<< اصلاح اصلی اینجاست
)
import chart_generator
from indicators import calculate_atr
from trend_analyzer import generate_master_trend_report

from performance_reporter import PerformanceReporter
CHOOSE_SYMBOL, CHOOSE_DIRECTION = range(2)

class InteractiveBot:
    def __init__(self, token, state_manager, position_manager, setup_manager, reinit_func):
        print("[InteractiveBot] Initializing...")
        self.application = Application.builder().token(token).build()
        self.state_manager = state_manager
        self.position_manager = position_manager
        self.setup_manager = setup_manager
        self.perform_reinitialization = reinit_func
        self.performance_reporter = PerformanceReporter(self.position_manager)


        self.main_menu_keyboard = [
            ['/trend روند روز', '/suggestion پیشنهاد سیگنال'],
            ['/trade ترید دستی', '/autotrade ترید خودکار'],
            ['/report گزارش عملکرد', '/reinit اجرای مجدد تحلیل'],
        ]


        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        self.register_handlers()
        print("[InteractiveBot] Initialization complete.")


    def register_handlers(self):
        trade_conv_handler = ConversationHandler(
            entry_points=[CommandHandler('trade', self.trade_start)],
            states={
                CHOOSE_SYMBOL: [CallbackQueryHandler(self.trade_symbol_chosen)],
                CHOOSE_DIRECTION: [CallbackQueryHandler(self.trade_direction_chosen)],
            },
            fallbacks=[CommandHandler('cancel', self.trade_cancel)],
        )

        self.application.add_handler(trade_conv_handler)
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('trend', self.handle_trend_report))
        self.application.add_handler(CommandHandler('suggestion', self.handle_signal_suggestion))
        self.application.add_handler(CommandHandler('report', self.handle_report_options))
        self.application.add_handler(CommandHandler('autotrade', self.toggle_autotrade_handler))
        self.application.add_handler(CommandHandler('reinit', self.handle_reinit))

        self.application.add_handler(MessageHandler(filters.Regex('^/trend روند روز$'), self.handle_trend_report))
        self.application.add_handler(MessageHandler(filters.Regex('^/suggestion پیشنهاد سیگنال$'), self.handle_signal_suggestion))
        self.application.add_handler(MessageHandler(filters.Regex('^/trade ترید دستی$'), self.trade_start))
        self.application.add_handler(MessageHandler(filters.Regex('^/autotrade ترید خودکار$'), self.toggle_autotrade_handler))
        self.application.add_handler(MessageHandler(filters.Regex('^/report گزارش عملکرد$'), self.handle_report_options))
        self.application.add_handler(MessageHandler(filters.Regex('^/reinit اجرای مجدد تحلیل$'), self.handle_reinit))

        # --- [اصلاح اصلی اینجاست] ---
        # ثبت کنترل‌کننده‌های دکمه‌های شیشه‌ای با pattern مشخص
        self.application.add_handler(CallbackQueryHandler(self.handle_proposal_buttons, pattern='^(confirm:|reject:|set_rr:|feedback:)'))
        self.application.add_handler(CallbackQueryHandler(self.handle_report_buttons, pattern='^report_'))


    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"سلام {user_name} عزیز!\n\nربات معامله‌گر فعال است.", reply_markup=self.main_menu_markup)


    async def handle_reinit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال اجرای مجدد تحلیل‌ها... این فرآیند ممکن است کمی طول بکشد.")
        try:
            threading.Thread(target=self.perform_reinitialization).start()
            await update.message.reply_text("✅ فرمان بازنشانی تحلیل‌ها ارسال شد.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ارسال فرمان: {e}")


    async def handle_proposal_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پاسخ به کلیک کاربر روی دکمه‌های کارت پیشنهاد سیگنال (تایید، رد، R/R)."""
        query = update.callback_query
        await query.answer()

        try:
            parts = query.data.split(":")
            action = parts[0]
            proposal_id = parts[1] if len(parts) > 1 else None

            if action == 'confirm':
                response_text = self.position_manager.confirm_paper_trade(proposal_id)
                await query.edit_message_text(text=f"{query.message.text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=None)
            elif action == 'reject':
                response_text = self.position_manager.reject_proposal(proposal_id)
                await query.edit_message_text(text=f"{query.message.text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=None)
            elif action == 'set_rr':
                rr_value = parts[2]
                new_text, new_keyboard = self.position_manager.update_proposal_rr(proposal_id, rr_value)
                if new_text and new_keyboard:
                    await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode='Markdown')
            elif action == 'feedback':
                 # این بخش برای آینده است و فعلا منطق خاصی ندارد
                await query.edit_message_text(text=f"{query.message.text}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)

        except Exception as e:
            print(f"[CALLBACK_HANDLER_ERROR] {e}")
            traceback.print_exc()
            await query.edit_message_text(text="خطایی در پردازش درخواست رخ داد.")

    
    async def handle_reinit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال اجرای مجدد تحلیل‌ها... این فرآیند ممکن است کمی طول بکشد.")
        try:
            # --- [تغییر] اجرای تابع در یک ترد جدید برای جلوگیری از بلاک شدن ربات ---
            threading.Thread(target=self.perform_reinitialization).start()
            await update.message.reply_text("✅ فرمان بازنشانی تحلیل‌ها ارسال شد.")
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ارسال فرمان: {e}")
        

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
        message = "📝 **گزارش خلاصه روند روزانه**\n"
        for symbol in self.state_manager.get_all_symbols():
            trend = self.state_manager.get_symbol_state(symbol, 'htf_trend', 'نامشخص')
            message += f"\n--- **{symbol}** --- \nروند اصلی شناسایی شده: **{trend}**\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    # --- [تغییر] این تابع دیگر تحلیل انجام نمی‌دهد، فقط گزارش می‌دهد ---
    async def handle_full_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = "📊 **گزارش کامل تحلیل روند**\n"
        for symbol in self.state_manager.get_all_symbols():
            report = self.state_manager.get_symbol_state(symbol, 'trend_report', 'گزارشی یافت نشد.')
            message += f"\n--- **{symbol}** ---\n{report}\n"
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

            if "BULLISH" in trend:
                suggestion = "در سطوح **حمایتی** زیر به دنبال تاییدیه **خرید** باشید:\n"
                relevant_levels = [lvl for lvl in levels if lvl['level_type'] in ['PDL', 'VAL', 'POC'] or 'low' in lvl['level_type'].lower()]
            elif "BEARISH" in trend:
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