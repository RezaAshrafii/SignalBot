# interactive_bot.py
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

class InteractiveBot:
    def __init__(self, token, state_manager, position_manager):
        print("[InteractiveBot] Initializing...")
        self.application = Application.builder().token(token).build()
        self.state_manager = state_manager
        self.position_manager = position_manager
        self.main_menu_keyboard = [['📊 وضعیت کلی', '/levels  уровни'], ['📈 پوزیشن‌های باز', '💰 عملکرد روزانه'], ['ℹ️ راهنما']]
        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        self.register_handlers()
        print("[InteractiveBot] Initialization complete.")

    def register_handlers(self):
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(MessageHandler(filters.Regex('^📊 وضعیت کلی$'), self.handle_status))
        self.application.add_handler(MessageHandler(filters.Regex('^📈 پوزیشن‌های باز$'), self.handle_open_positions))
        self.application.add_handler(MessageHandler(filters.Regex('^💰 عملکرد روزانه$'), self.handle_daily_performance))
        self.application.add_handler(MessageHandler(filters.Regex('^ℹ️ راهنما$'), self.handle_help))
        # --- [دستور جدید] ---
        self.application.add_handler(CommandHandler('levels', self.handle_nearby_levels))
        self.application.add_handler(MessageHandler(filters.Regex('^/levels уровни$'), self.handle_nearby_levels))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown))

    # ... (متدهای start, handle_status, handle_open_positions, handle_daily_performance, handle_help بدون تغییر) ...
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        await update.message.reply_text(f"سلام {user_name} عزیز!\n\nربات معامله‌گر فعال است.", reply_markup=self.main_menu_markup)
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = "📊 **وضعیت کلی سیستم**\n\n"
        symbols_to_monitor = self.state_manager.get_all_symbols()
        if not symbols_to_monitor: await update.message.reply_text("هنوز ارزی برای نظارت تعریف نشده است."); return
        for symbol in symbols_to_monitor:
            state = self.state_manager.get_symbol_snapshot(symbol)
            price_str = f"{state.get('last_price'):,.2f}" if state.get('last_price') else "در حال دریافت..."
            message += f"🔹 **{symbol}**\n   - قیمت فعلی: `{price_str}`\n   - روند روزانه: `{state.get('htf_trend', 'N/A')}`\n   - سطوح فعال: `{len(state.get('untouched_levels', []))}` عدد\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions: await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown'); return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos.get('entry_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            message += f"▶️ **{pos.get('symbol')} - {pos.get('direction', '').upper()}**\n   - نوع ستاپ: `{pos.get('setup_type', 'N/A')}`\n   - قیمت ورود: `{pos.get('entry_price', 0):,.2f}`\n   - حد ضرر: `{pos.get('stop_loss', 0):,.2f}`\n   - زمان ورود: `{entry_time_str}`\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance()
        profit = performance.get('daily_profit_percent', 0.0); limit = performance.get('drawdown_limit', 0.0)
        profit_str = f"+{profit:.2f}%" if profit >= 0 else f"{profit:.2f}%"
        message = f"💰 **عملکرد روزانه**\n\n▫️ سود / زیان امروز:  **{profit_str}**\n▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("ℹ️ **راهنمای ربات**\n\nاین ربات به صورت خودکار فرصت‌های معاملاتی را شناسایی و مدیریت می‌کند.", parse_mode='Markdown')

    # --- [تابع جدید] ---
    async def handle_nearby_levels(self, update: Update, context: ContextTypes.DEFAULT_TYPE, proximity_percent=2.0):
        """نزدیک‌ترین سطوح کلیدی به قیمت فعلی را نمایش می‌دهد."""
        message = "🔑 **سطوح کلیدی نزدیک به قیمت فعلی**\n"
        found_any = False
        symbols_to_monitor = self.state_manager.get_all_symbols()

        for symbol in symbols_to_monitor:
            state = self.state_manager.get_symbol_snapshot(symbol)
            current_price = state.get('last_price')
            levels = state.get('untouched_levels', [])
            
            if not current_price or not levels:
                continue

            nearby_levels = [
                lvl for lvl in levels 
                if abs(lvl['level'] - current_price) / current_price * 100 <= proximity_percent
            ]
            
            if nearby_levels:
                found_any = True
                message += f"\n🔹 **{symbol}** (قیمت فعلی: `{current_price:,.2f}`)\n"
                # مرتب‌سازی سطوح بر اساس فاصله از قیمت فعلی
                nearby_levels.sort(key=lambda x: abs(x['level'] - current_price))
                for lvl in nearby_levels:
                    position = "Higher" if lvl['level'] > current_price else "Lower"
                    message += f"   - `{lvl['level_type']}` ({lvl['date']}): `{lvl['level']:,.2f}` ({position})\n"
        
        if not found_any:
            message = "هیچ سطح کلیدی در نزدیکی قیمت فعلی (محدوده ۲٪) یافت نشد."

        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست.")