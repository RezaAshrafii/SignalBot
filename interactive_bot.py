# interactive_bot.py
import threading
import asyncio
import traceback
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import chart_generator

class InteractiveBot:
    def __init__(self, token, state_manager, position_manager):
        print("[InteractiveBot] Initializing..."); self.application = Application.builder().token(token).build()
        self.state_manager = state_manager; self.position_manager = position_manager
        self.main_menu_keyboard = [
            ['/trend روند روز', '/suggestion پیشنهاد سیگنال'],
            [r'/levels سطوح نزدیک (چارت)', '📈 پوزیشن‌های باز'],
            ['💰 عملکرد روزانه', '/report گزارش روزانه'],
            ['🔇/🔊 حالت سکوت']
        ]
        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True); self.register_handlers()
        print("[InteractiveBot] Initialization complete.")

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
        query = update.callback_query; await query.answer()
        try:
            parts = query.data.split(":"); action = parts[0]; proposal_id = parts[1]
            if action in ['confirm', 'reject']:
                response_text = self.position_manager.confirm_paper_trade(proposal_id, query.message.chat_id, query.message.message_id) if action == 'confirm' else self.position_manager.reject_proposal(proposal_id)
                original_text = query.message.text_markdown.split("\n\n**سود/زیان لحظه‌ای:")[0]
                await query.edit_message_text(text=f"{original_text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=None)
            elif action == 'set_rr':
                rr_value = parts[2]
                new_text, new_keyboard = self.position_manager.update_proposal_rr(proposal_id, rr_value)
                if new_text and new_keyboard: await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode='Markdown')
            elif action == 'feedback':
                feedback = parts[2]
                self.position_manager.log_feedback(proposal_id, feedback)
                await query.edit_message_text(text=f"{query.message.text_markdown}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)
        except Exception as e: print(f"[CALLBACK_HANDLER_ERROR] {e}")

    async def handle_toggle_silent_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_silent = self.state_manager.toggle_silent_mode()
        await update.message.reply_text(f"🔇 حالت سکوت **{'فعال' if is_silent else 'غیرفعال'}** شد.")

    async def handle_nearby_levels_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال آماده‌سازی چارت...")
        # ... (کد کامل این تابع از پاسخ قبلی)

    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # ... (کد کامل این تابع از پاسخ قبلی)
        pass

    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # ... (کد کامل این تابع از پاسخ قبلی)
        pass

    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # ... (کد کامل این تابع از پاسخ قبلی)
        pass
        
    async def handle_trend_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # ... (کد کامل این تابع از پاسخ قبلی)
        pass

    async def handle_signal_suggestion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        # ... (کد کامل این تابع از پاسخ قبلی)
        pass

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست.")

    def _runner(self):
        """این تابع، حلقه رویداد را برای ترد جدید مدیریت می‌کند."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            if hasattr(self.position_manager, 'set_application_and_loop'):
                self.position_manager.set_application_and_loop(self.application, loop)
            loop.run_until_complete(self.application.run_polling(stop_signals=None))
        except Exception:
            print("!!! CRITICAL ERROR IN INTERACTIVE BOT THREAD !!!")
            traceback.print_exc()

    def run(self):
        """ربات را در یک ترد جداگانه اجرا می‌کند."""
        print("Starting interactive bot in a separate thread...")
        threading.Thread(target=self._runner, daemon=True, name="InteractiveBotThread").start()