# interactive_bot.py
import threading
import asyncio
import traceback
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

class InteractiveBot:
    def __init__(self, token, state_manager, position_manager):
        print("[InteractiveBot] Initializing...")
        self.application = Application.builder().token(token).build()
        self.state_manager = state_manager
        self.position_manager = position_manager
        self.main_menu_keyboard = [['📊 وضعیت کلی'], ['📈 پوزیشن‌های باز', '💰 عملکرد روزانه'], ['ℹ️ راهنما']]
        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        self.register_handlers()
        print("[InteractiveBot] Initialization complete.")

    def register_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 وضعیت کلی$'), self.handle_status))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 پوزیشن‌های باز$'), self.handle_open_positions))
        self.application.add_handler(MessageHandler(filters.Regex('^💰 عملکرد روزانه$'), self.handle_daily_performance))
        self.application.add_handler(MessageHandler(filters.Regex('^ℹ️ راهنما$'), self.handle_help))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        welcome_text = f"سلام {user_name} عزیز!\n\nبه ربات معامله‌گر خودکار خوش آمدید. لطفاً یکی از گزینه‌های زیر را انتخاب کنید:"
        await update.message.reply_text(welcome_text, reply_markup=self.main_menu_markup)

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        full_state = self.state_manager.get_full_state()
        if not full_state:
            await update.message.reply_text("هنوز داده‌ای برای نمایش وجود ندارد.")
            return
        message = "📊 **وضعیت کلی سیستم**\n\n"
        for symbol, state in full_state.items():
            last_price = self.state_manager.get_symbol_state(symbol, 'last_price')
            price_str = f"{last_price:,.2f}" if isinstance(last_price, (int, float)) else "در حال دریافت..."
            htf_trend = state.get('htf_trend', 'نامشخص')
            untouched_levels = state.get('untouched_levels', [])
            num_levels = len(untouched_levels) if untouched_levels else 0
            message += f"🔹 **{symbol}**\n   - قیمت فعلی: `{price_str}`\n   - روند روزانه: `{htf_trend}`\n   - سطوح فعال: `{num_levels}` عدد\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            message = "📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد."
            await update.message.reply_text(message, parse_mode='Markdown')
            return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos.get('entry_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            setup_type = pos.get('setup_type', 'N/A')
            entry_price = pos.get('entry_price', 0)
            stop_loss = pos.get('stop_loss', 0)
            message += f"▶️ **{pos['symbol']} - {pos['direction'].upper()}**\n   - نوع ستاپ: `{setup_type}`\n   - قیمت ورود: `{entry_price:,.2f}`\n   - حد ضرر: `{stop_loss:,.2f}`\n   - زمان ورود: `{entry_time_str}`\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance()
        profit = performance.get('daily_profit_percent', 0.0)
        limit = performance.get('drawdown_limit', 0.0)
        profit_str = f"+{profit:.2f}%" if profit >= 0 else f"{profit:.2f}%"
        message = f"💰 **عملکرد روزانه**\n\n▫️ سود / زیان امروز:  **{profit_str}**\n▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = "ℹ️ **راهنمای ربات**\n\nاین ربات به صورت خودکار فرصت‌های معاملاتی را شناسایی و مدیریت می‌کند."
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست. لطفاً از دکمه‌های منو استفاده کنید.")

    def run(self):
        thread = threading.Thread(target=self.run_bot, daemon=True)
        thread.start()
        print("Interactive Telegram Bot thread started.")

    def run_bot(self):
        """
        حلقه اصلی اجرای ربات تلگرام با اصلاحیه برای حل مشکل ترد.
        """
        try:
            print("[InteractiveBot] Starting polling...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # --- [این خط اصلاح شد] ---
            # با ارسال stop_signals=None، به کتابخانه می‌گوییم که سیگنال‌های سیستم را مدیریت نکند.
            loop.run_until_complete(self.application.run_polling(stop_signals=None))
            
        except Exception as e:
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print("!!! CRITICAL ERROR IN INTERACTIVE BOT THREAD !!!")
            print(f"!!! Error Type: {type(e).__name__}")
            print(f"!!! Error Message: {e}")
            print("!!! Traceback:")
            traceback.print_exc()
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")