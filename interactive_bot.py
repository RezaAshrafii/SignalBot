# interactive_bot.py
import asyncio
import threading
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
# ماژول bot_handlers در ساختار فعلی استفاده نمی‌شود، آن را حذف می‌کنیم
# import bot_handlers 

# ماژول جدید برای ساخت چارت
import chart_generator 

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
        # --- [اصلاح شد] --- تابع start به CommandHandler متصل شد
        self.application.add_handler(CommandHandler('start', self.start))
        
        self.application.add_handler(MessageHandler(filters.Regex('^📈 پوزیشن‌های باز$'), self.handle_open_positions))
        self.application.add_handler(MessageHandler(filters.Regex('^💰 عملکرد روزانه$'), self.handle_daily_performance))
        
        # --- [اصلاح شد] --- استفاده از raw string برای رفع SyntaxWarning
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

    # --- [تابع اضافه شده] --- این تابع که حذف شده بود، برای رفع AttributeError اضافه شد
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_name = update.effective_user.first_name
        welcome_text = f"سلام {user_name} عزیز!\n\nربات معامله‌گر فعال است."
        await update.message.reply_text(welcome_text, reply_markup=self.main_menu_markup)

    async def handle_button_clicks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query; await query.answer()
        try:
            parts = query.data.split(":"); action = parts[0]
            if action in ['confirm', 'reject']:
                proposal_id = parts[1]
                response_text = self.position_manager.confirm_paper_trade(proposal_id, query.message.chat_id, query.message.message_id) if action == 'confirm' else self.position_manager.reject_proposal(proposal_id)
                original_text = query.message.text_markdown.split("\n\n**سود/زیان لحظه‌ای:")[0]
                feedback_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👍 سیگنال خوب بود", callback_data=f"feedback:{proposal_id}:good"), InlineKeyboardButton("👎 سیگنال بد بود", callback_data=f"feedback:{proposal_id}:bad")]])
                await query.edit_message_text(text=f"{original_text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=feedback_keyboard)
            elif action == 'set_rr':
                proposal_id, rr_value = parts[1], parts[2]
                new_text, new_keyboard = self.position_manager.update_proposal_rr(proposal_id, rr_value)
                if new_text and new_keyboard: await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode='Markdown')
            elif action == 'feedback':
                proposal_id, feedback = parts[1], parts[2]
                self.position_manager.log_feedback(proposal_id, feedback)
                await query.edit_message_text(text=f"{query.message.text_markdown}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)
        except Exception as e: print(f"[CALLBACK_HANDLER_ERROR] {e}")

    async def handle_toggle_silent_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_silent = self.state_manager.toggle_silent_mode()
        status = "فعال" if is_silent else "غیرفعال"
        await update.message.reply_text(f"🔇 حالت سکوت **{status}** شد.")

    async def handle_nearby_levels_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال آماده‌سازی چارت، لطفاً چند لحظه صبر کنید...")
        for symbol in self.state_manager.get_all_symbols():
            klines = self.state_manager.get_symbol_state(symbol, 'klines_1m')
            state = self.state_manager.get_symbol_snapshot(symbol)
            current_price, levels = state.get('last_price'), state.get('untouched_levels', [])
            if not klines or not current_price or not levels:
                await update.message.reply_text(f"داده کافی برای رسم چارت {symbol} وجود ندارد."); continue
            
            nearby_levels = [lvl for lvl in levels if abs(lvl['level'] - current_price) / current_price * 100 <= 2.0]
            if not nearby_levels: continue

            caption = f"🔑 **سطوح کلیدی نزدیک به قیمت فعلی برای {symbol}**"
            image_buffer = chart_generator.generate_chart_image(klines, nearby_levels, current_price, symbol)
            if image_buffer:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_buffer, caption=caption, parse_mode='Markdown')

    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown')
            return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos.get('entry_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            message += f"▶️ **{pos.get('symbol')} - {pos.get('direction', '').upper()}**\n   - قیمت ورود: `{pos.get('entry_price', 0):,.2f}`\n   - حد ضرر: `{pos.get('stop_loss', 0):,.2f}`\n\n"
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
        message = "📝 **گزارش تحلیل روند روزانه**\n"
        for symbol in self.state_manager.get_all_symbols():
            report_text = self.state_manager.get_symbol_state(symbol, 'trend_report')
            message += f"\n--- **{symbol}** ---\n{report_text or 'گزارش روند هنوز آماده نشده است.'}\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_signal_suggestion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = "🎯 **پیشنهادهای استراتژیک روز**\n"
        for symbol in self.state_manager.get_all_symbols():
            trend = self.state_manager.get_symbol_state(symbol, 'htf_trend')
            levels = self.state_manager.get_symbol_state(symbol, 'untouched_levels')
            if not trend or not levels or trend == "INSUFFICIENT_DATA":
                message += f"\n--- **{symbol}** ---\nاطلاعات کافی برای پیشنهاد وجود ندارد.\n"; continue

            message += f"\n--- **{symbol}** (روند: **{trend}**) ---\n"
            
            if "UP" in trend:
                suggestion = "در سطوح **حمایتی** زیر به دنبال تاییدیه **خرید** باشید:\n"
                relevant_levels = [lvl for lvl in levels if lvl['level_type'] in ['PDL', 'VAL', 'POC']]
            elif "DOWN" in trend:
                suggestion = "در سطوح **مقاومتی** زیر به دنبال تاییدیه **فروش** باشید:\n"
                relevant_levels = [lvl for lvl in levels if lvl['level_type'] in ['PDH', 'VAH', 'POC']]
            else:
                suggestion = "روند خنثی است. معامله با احتیاط توصیه می‌شود.\n"; relevant_levels = []
            
            if not relevant_levels: suggestion += "سطح مناسبی برای معامله در جهت روند یافت نشد.\n"
            
            message += suggestion
            relevant_levels.sort(key=lambda x: x['level'], reverse=True)
            for lvl in relevant_levels: message += f"  - `{lvl['level_type']}` در قیمت `{lvl['level']:,.2f}`\n"
        await update.message.reply_text(message, parse_mode='Markdown')

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("دستور وارد شده معتبر نیست.")