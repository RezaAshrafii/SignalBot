# interactive_bot.py
import threading
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

class InteractiveBot:
    def __init__(self, token, state_manager, position_manager):
        """
        مقداردهی اولیه ربات با استفاده از الگوی جدید ApplicationBuilder.
        """
        self.application = Application.builder().token(token).build()
        
        self.state_manager = state_manager
        self.position_manager = position_manager

        self.main_menu_keyboard = [
            ['📊 وضعیت کلی'],
            ['📈 پوزیشن‌های باز', '💰 عملکرد روزانه'],
            ['ℹ️ راهنما']
        ]
        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        
        self.register_handlers()

    def register_handlers(self):
        """
        تمام کنترل‌کننده‌ها مستقیماً به application اضافه می‌شوند.
        """
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
            await update.message.reply_text("هنوز داده‌ای برای نمایش وجود ندارد. لطفاً منتظر بمانید تا ربات مقداردهی اولیه شود.")
            return

        message = "📊 **وضعیت کلی سیستم**\n\n"
        for symbol, state in full_state.items():
            last_price = state.get('last_price')
            price_str = f"{last_price:,.2f}" if isinstance(last_price, (int, float)) else "در حال دریافت..."
            htf_trend = state.get('htf_trend', 'نامشخص')
            untouched_levels = state.get('untouched_levels', [])
            num_levels = len(untouched_levels) if untouched_levels else 0

            message += f"🔹 **{symbol}**\n"
            message += f"   - قیمت فعلی: `{price_str}`\n"
            message += f"   - روند روزانه: `{htf_trend}`\n"
            message += f"   - سطوح فعال: `{num_levels}` عدد\n\n"
            
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        
        if not open_positions:
            message = "📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد."
            await update.message.reply_text(message, parse_mode='Markdown')
            return

        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos['entry_time'].strftime('%Y-%m-%d %H:%M:%S')
            message += f"▶️ **{pos['symbol']} - {pos['direction'].upper()}**\n"
            message += f"   - نوع ستاپ: `{pos['setup_type']}`\n"
            message += f"   - قیمت ورود: `{pos['entry_price']:,.2f}`\n"
            message += f"   - حد ضرر: `{pos['stop_loss']:,.2f}`\n"
            message += f"   - زمان ورود: `{entry_time_str}`\n\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance()
        profit = performance['daily_profit']
        drawdown = performance['daily_drawdown']
        limit = performance['drawdown_limit']
        
        profit_str = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
        
        message = "💰 **عملکرد روزانه**\n\n"
        message += f"▫️ سود / زیان امروز:  **{profit_str}**\n"
        message += f"▫️ افت سرمایه امروز:  **{drawdown:.2f}%**\n"
        message += f"▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = "ℹ️ **راهنمای ربات**\n\nاین ربات به صورت خودکار بر اساس استراتژی‌های تعریف‌شده، فرصت‌های معاملاتی را در بازار فیوچرز بایننس شناسایی و مدیریت می‌کند.\n\n**دکمه‌های منو:**\n- **📊 وضعیت کلی:** خلاصه‌ای از وضعیت فعلی هر ارز.\n- **📈 پوزیشن‌های باز:** لیست پوزیشن‌های باز.\n- **💰 عملکرد روزانه:** سود/زیان و دراودان امروز.\n- **ℹ️ راهنما:** همین پیام راهنما."
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست. لطفاً از دکمه‌های منو استفاده کنید.")

    def run(self):
        """
        ربات را در یک ترد جداگانه اجرا می‌کند.
        """
        thread = threading.Thread(target=self.run_bot, daemon=True)
        thread.start()
        print("Interactive Telegram Bot has started.")

    def run_bot(self):
        """
        یک حلقه رویداد جدید برای ترد ایجاد، تنظیم و اجرا می‌کند.
        این روش صحیح برای اجرای asyncio در یک ترد مجزا است.
        """
        # ۱. یک حلقه رویداد جدید بساز
        loop = asyncio.new_event_loop()
        # ۲. آن را به عنوان حلقه فعال برای این ترد تنظیم کن
        asyncio.set_event_loop(loop)
        
        # ۳. تابع اصلی async را تا زمان تکمیل در این حلقه اجرا کن
        try:
            loop.run_until_complete(self.application.run_polling())
        finally:
            loop.close()