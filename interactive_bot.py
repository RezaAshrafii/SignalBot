# interactive_bot.py
import asyncio
import traceback
from datetime import datetime
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
        welcome_text = f"سلام {user_name} عزیز!\n\nبه ربات معامله‌گر خودکار خوش آمدید."
        await update.message.reply_text(welcome_text, reply_markup=self.main_menu_markup)

    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = "📊 **وضعیت کلی سیستم**\n\n"
        symbols_to_monitor = self.state_manager.get_all_symbols() # فرض می‌کنیم چنین متدی وجود دارد
        if not symbols_to_monitor: await update.message.reply_text("هنوز ارزی برای نظارت تعریف نشده است."); return

        for symbol in symbols_to_monitor:
            state = self.state_manager.get_symbol_snapshot(symbol) # فرض می‌کنیم چنین متدی وجود دارد
            price_str = f"{state.get('last_price'):,.2f}" if state.get('last_price') else "در حال دریافت..."
            message += f"🔹 **{symbol}**\n   - قیمت فعلی: `{price_str}`\n   - روند روزانه: `{state.get('htf_trend', 'N/A')}`\n   - سطوح فعال: `{len(state.get('untouched_levels', []))}` عدد\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown')
            return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos.get('entry_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            message += f"▶️ **{pos.get('symbol')} - {pos.get('direction', '').upper()}**\n   - نوع ستاپ: `{pos.get('setup_type', 'N/A')}`\n   - قیمت ورود: `{pos.get('entry_price', 0):,.2f}`\n   - حد ضرر: `{pos.get('stop_loss', 0):,.2f}`\n   - زمان ورود: `{entry_time_str}`\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance()
        profit = performance.get('daily_profit', 0.0)
        drawdown = performance.get('daily_drawdown', 0.0)
        limit = performance.get('drawdown_limit', 0.0)
        profit_str = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
        message = f"💰 **عملکرد روزانه**\n\n▫️ سود / زیان امروز:  **{profit_str}**\n▫️ افت سرمایه امروز:  **{drawdown:.2f}%**\n▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("ℹ️ **راهنمای ربات**\n\nاین ربات به صورت خودکار فرصت‌های معاملاتی را شناسایی و مدیریت می‌کند.", parse_mode='Markdown')

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست. لطفاً از دکمه‌های منو استفاده کنید.")

    # متد run() دیگر لازم نیست، چون main.py اجرای ربات را مدیریت می‌کند.