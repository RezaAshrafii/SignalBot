# interactive_bot.py
# نسخه نهایی، کامل و بازنویسی شده

import threading
import asyncio
import traceback
import pandas as pd
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler
)

from performance_reporter import PerformanceReporter
from trend_analyzer import generate_master_trend_report
from indicators import calculate_atr


# در فایل: interactive_bot.py

# تعریف وضعیت‌های جدید برای مکالمات
# مکالمه ترید دستی
# در فایل: interactive_bot.py

# تعریف وضعیت‌های جدید برای مکالمه مدیریت پوزیشن
MANAGE_CHOOSE_POS, MANAGE_CHOOSE_ACTION, MANAGE_GET_NEW_SL, MANAGE_GET_NEW_TP = range(4, 8)
TRADE_CHOOSE_SYMBOL, TRADE_CHOOSE_DIRECTION, TRADE_GET_SL, TRADE_GET_TP = range(4)
# مکالمه مدیریت پوزیشن
# تعریف وضعیت‌ها برای مکالمه ترید

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
            ['/positions پوزیشن‌های باز', '/manage مدیریت پوزیشن'],
            ['/trade ترید دستی', '/autotrade ترید خودکار'],
            ['/report گزارش عملکرد', '/reinit اجرای مجدد تحلیل'],
        ]

        self.main_menu_markup = ReplyKeyboardMarkup(self.main_menu_keyboard, resize_keyboard=True)
        self.register_handlers()
        print("[InteractiveBot] Initialization complete.")

# در فایل: interactive_bot.py

    def register_handlers(self):
        """
        تمام کنترل‌کننده‌ها، از جمله مکالمات جدید را به صورت صحیح ثبت می‌کند.
        """
        # مکالمه ترید دستی (موجود در کد شما)
        trade_conv = ConversationHandler(
            entry_points=[CommandHandler('trade', self.trade_start)],
            states={
                TRADE_CHOOSE_SYMBOL: [CallbackQueryHandler(self.trade_symbol_chosen, pattern='^trade_symbol:')],
                TRADE_CHOOSE_DIRECTION: [CallbackQueryHandler(self.trade_direction_chosen, pattern='^trade_dir:')],
                TRADE_GET_SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.trade_get_sl)],
                TRADE_GET_TP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.trade_get_tp)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_conversation)],
        )

        # --- [بخش جدید] --- مکالمه مدیریت پوزیشن
        manage_conv = ConversationHandler(
            entry_points=[CommandHandler('manage', self.manage_start), MessageHandler(filters.Regex('^/manage مدیریت پوزیشن$'), self.manage_start)],
            states={
                MANAGE_CHOOSE_POS: [CallbackQueryHandler(self.manage_pos_chosen, pattern='^manage_pos:')],
                MANAGE_CHOOSE_ACTION: [CallbackQueryHandler(self.manage_action_chosen, pattern='^manage_action:')],
                MANAGE_GET_NEW_SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.manage_get_new_sl)],
                MANAGE_GET_NEW_TP: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.manage_get_new_tp)],
            },
            fallbacks=[CommandHandler('cancel', self.cancel_conversation)],
        )

        self.application.add_handler(trade_conv)
        self.application.add_handler(manage_conv)

        # --- [بخش اصلاح شده] --- ثبت تمام کنترل‌کننده‌های استاندارد
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('positions', self.handle_open_positions)) # اتصال دستور
        self.application.add_handler(CommandHandler('report', self.handle_report_options))
        self.application.add_handler(CommandHandler('autotrade', self.toggle_autotrade_handler))
        self.application.add_handler(CommandHandler('reinit', self.handle_reinit))
        self.application.add_handler(CommandHandler('trend', self.handle_trend_report))
        self.application.add_handler(CommandHandler('suggestion', self.handle_signal_suggestion))
        
        # کنترل‌کننده‌های دکمه‌های کیبورد اصلی
        self.application.add_handler(MessageHandler(filters.Regex('^/positions پوزیشن‌های باز$'), self.handle_open_positions)) # اتصال دکمه
        self.application.add_handler(MessageHandler(filters.Regex('^/report گزارش عملکرد$'), self.handle_report_options))
        self.application.add_handler(MessageHandler(filters.Regex('^/autotrade ترید خودکار$'), self.toggle_autotrade_handler))
        self.application.add_handler(MessageHandler(filters.Regex('^/reinit اجرای مجدد تحلیل$'), self.handle_reinit))
        self.application.add_handler(MessageHandler(filters.Regex('^/trend روند روز$'), self.handle_trend_report))
        self.application.add_handler(MessageHandler(filters.Regex('^/suggestion پیشنهاد سیگنال$'), self.handle_signal_suggestion))
        self.application.add_handler(MessageHandler(filters.Regex('^/trade ترید دستی$'), self.trade_start))
        
        # کنترل‌کننده‌های دکمه‌های شیشه‌ای (Inline)
        self.application.add_handler(CallbackQueryHandler(self.handle_proposal_buttons, pattern='^(confirm:|reject:|set_rr:|feedback:)'))
        self.application.add_handler(CallbackQueryHandler(self.handle_report_buttons, pattern='^report_'))
        self.application.add_handler(CommandHandler('full_report', self.handle_full_trend_report))



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

    async def toggle_autotrade_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_status = self.state_manager.toggle_autotrade()
        status_text = "فعال ✅" if new_status else "غیرفعال ❌"
        await update.message.reply_text(f"🤖 وضعیت معامله خودکار: **{status_text}**", parse_mode='Markdown')
        
    # در فایل: interactive_bot.py (این تابع را به کلاس InteractiveBot اضافه کنید)

    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لیست پوزیشن‌های باز فعلی را به همراه سود و زیان لحظه‌ای نمایش می‌دهد."""
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown')
            return
        
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            symbol = pos.get('symbol', 'N/A')
            direction = pos.get('direction', 'N/A')
            entry = pos.get('entry_price', 0)
            sl = pos.get('stop_loss', 0)
            tp = pos.get('take_profit', 0)
            
            # دریافت قیمت لحظه‌ای برای محاسبه سود و زیان زنده
            last_price = self.state_manager.get_symbol_state(symbol, 'last_price', entry)
            
            pnl = (last_price - entry) if direction == 'Buy' else (entry - last_price)
            pnl_percent = (pnl / entry) * 100 if entry != 0 else 0
            
            icon = "🟢" if pnl >= 0 else "🔴"
            
            message += (f"▶️ **{symbol} - {direction.upper()}** {icon}\n"
                        f"   - **سود/زیان:** `{pnl_percent:+.2f}%`\n"
                        f"   - **ورود:** `{entry:,.2f}` | **فعلی:** `{last_price:,.2f}`\n"
                        f"   - **حد ضرر:** `{sl:,.2f}` | **حد سود:** `{tp:,.2f}`\n\n")
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_full_trend_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """گزارش کامل و دقیق تحلیل روند را برای تمام ارزها ارسال می‌کند."""
        for symbol in self.state_manager.get_all_symbols():
            report = self.state_manager.get_symbol_state(symbol, 'trend_report', 'گزارش دقیقی برای این ارز یافت نشد.')
            await update.message.reply_text(report, parse_mode='Markdown')

    async def handle_signal_suggestion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        sent_message = await update.message.reply_text("در حال آماده‌سازی پیشنهادهای استراتژیک...")
        message = "🎯 **پیشنهادهای استراتژیک روز**\n"
        
        for symbol in self.state_manager.get_all_symbols():
            state = self.state_manager.get_full_symbol_state(symbol)
            trend = state.get('htf_trend')
            levels = state.get('untouched_levels')
            klines = state.get('klines_1m') # Assuming klines_1m is a DataFrame
            level_tests = state.get('level_test_counts', {})
            
            if not trend or not levels or trend == "INSUFFICIENT_DATA":
                message += f"\n--- **{symbol}** ---\nداده کافی برای تحلیل وجود ندارد.\n"
                continue
            
            message += f"\n--- **{symbol}** (روند: **{trend}**) ---\n"
            
            if klines is not None and not klines.empty and len(klines) > 14:
                atr = calculate_atr(klines)
                last_price = state.get('last_price')
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
            
            if not relevant_levels:
                suggestion += "سطح مناسبی برای معامله یافت نشد.\n"
            
            message += suggestion
            relevant_levels.sort(key=lambda x: x['level'], reverse=True)
            for lvl in relevant_levels:
                test_count = level_tests.get(str(lvl['level']), 0)
                message += f"  - `{lvl['level_type']}` در `{lvl['level']:,.2f}` (تست شده: `{test_count}` بار)\n"
                        
        await context.bot.edit_message_text(text=message, chat_id=sent_message.chat_id, message_id=sent_message.message_id, parse_mode='Markdown')


    # --- توابع مربوط به مکالمه ترید (/trade) ---

# در فایل: interactive_bot.py

    async def trade_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """مکالمه ترید دستی را با پرسیدن نماد شروع می‌کند."""
        symbols = self.state_manager.get_all_symbols()
        if not symbols:
            await update.message.reply_text("هیچ ارزی برای معامله تعریف نشده است.")
            return ConversationHandler.END

        # --- [اصلاح اصلی] --- افزودن پیشوند به callback_data برای تطابق با pattern
        keyboard = [[InlineKeyboardButton(s, callback_data=f"trade_symbol:{s}")] for s in symbols]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("کدام ارز را می‌خواهید معامله کنید؟", reply_markup=reply_markup)
        
        return TRADE_CHOOSE_SYMBOL
    

# در فایل: interactive_bot.py

    async def trade_symbol_chosen(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """انتخاب نماد را مدیریت کرده و جهت معامله را می‌پرسد."""
        query = update.callback_query
        await query.answer()
        # با استفاده از split، پیشوند را جدا کرده و فقط نام ارز را ذخیره می‌کنیم
        context.user_data['trade_symbol'] = query.data.split(':')[1]

        # --- [اصلاح اصلی] --- افزودن پیشوند به callback_data برای تطابق با pattern
        keyboard = [
            [InlineKeyboardButton("🟢 خرید (Long)", callback_data="trade_dir:Buy")],
            [InlineKeyboardButton("🔴 فروش (Short)", callback_data="trade_dir:Sell")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"شما ارز {context.user_data['trade_symbol']} را انتخاب کردید. جهت معامله چیست؟", reply_markup=reply_markup)
        
        # --- [اصلاح اصلی] --- استفاده از نام متغیر وضعیت صحیح
        return TRADE_CHOOSE_DIRECTION

    # در فایل: interactive_bot.py

    async def trade_direction_chosen(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        پس از انتخاب جهت، آن را ذخیره کرده و برای دریافت حد ضرر به مرحله بعد می‌رود.
        """
        query = update.callback_query
        await query.answer()
        # ذخیره جهت معامله در حافظه موقت مکالمه
        context.user_data['direction'] = query.data.split(':')[1]
        
        # ویرایش پیام و درخواست برای حد ضرر
        await query.edit_message_text(text=f"جهت معامله: {context.user_data['direction']}. لطفاً قیمت حد ضرر (Stop-Loss) را وارد کنید:")
        
        # انتقال به مرحله بعدی
        return TRADE_GET_SL

    async def trade_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("عملیات ترید لغو شد.", reply_markup=self.main_menu_markup)
        context.user_data.clear()
        return ConversationHandler.END

    # --- توابع مربوط به دکمه‌های شیشه‌ای (CallbackQuery) ---

    async def handle_proposal_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                await query.edit_message_text(text=f"{query.message.text}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)
        except Exception as e:
            print(f"[PROPOSAL_BUTTON_ERROR] {e}")
            traceback.print_exc()
            await query.edit_message_text(text="خطایی در پردازش درخواست رخ داد.")
            
    async def handle_report_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📊 گزارش روزانه", callback_data="report_1")],
            [InlineKeyboardButton("📅 گزارش هفتگی", callback_data="report_7")],
            [InlineKeyboardButton("🗓️ گزارش ماهانه", callback_data="report_30")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("لطفاً دوره گزارش مورد نظر خود را انتخاب کنید:", reply_markup=reply_markup)

    async def handle_report_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        period_days = int(query.data.split('_')[1])
        report_text = self.performance_reporter.generate_report(period_days)
        await query.edit_message_text(text=report_text, parse_mode='Markdown')

    # --- توابع مربوط به اجرای ربات در ترد جدا ---

# در فایل: interactive_bot.py (این توابع را به کلاس اضافه کنید)

    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """یک مکالمه را لغو می‌کند."""
        await update.message.reply_text("عملیات لغو شد.", reply_markup=self.main_menu_markup)
        context.user_data.clear()
        return ConversationHandler.END

    # --- توابع مکالمه مدیریت پوزیشن ---
    async def manage_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        open_positions = self.position_manager.get_open_positions()
        if not open_positions:
            await update.message.reply_text("هیچ پوزیشن بازی برای مدیریت وجود ندارد.", reply_markup=self.main_menu_markup)
            return ConversationHandler.END
        
        keyboard = [[InlineKeyboardButton(f"{pos['symbol']} - {pos['direction']}", callback_data=f"manage_pos:{pos['symbol']}")] for pos in open_positions]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("کدام پوزیشن را می‌خواهید مدیریت کنید؟", reply_markup=reply_markup)
        return MANAGE_CHOOSE_POS

    async def manage_pos_chosen(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        symbol = query.data.split(':')[1]
        context.user_data['manage_symbol'] = symbol

        keyboard = [
            [InlineKeyboardButton("❌ بستن معامله", callback_data=f"manage_action:close")],
            [InlineKeyboardButton("✏️ ویرایش SL/TP", callback_data=f"manage_action:edit")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"چه کاری برای پوزیشن {symbol} انجام شود؟", reply_markup=reply_markup)
        return MANAGE_CHOOSE_ACTION

    async def manage_action_chosen(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        action = query.data.split(':')[1]
        symbol = context.user_data['manage_symbol']

        if action == 'close':
            last_price = self.state_manager.get_symbol_state(symbol, 'last_price')
            if not last_price:
                await query.edit_message_text("❌ قیمت لحظه‌ای برای بستن معامله در دسترس نیست.")
                return ConversationHandler.END
            
            result = self.position_manager.close_manual_trade(symbol, last_price)
            await query.edit_message_text(result)
            context.user_data.clear()
            return ConversationHandler.END
        
        elif action == 'edit':
            await query.edit_message_text("لطفاً حد ضرر (SL) جدید را وارد کنید:")
            return MANAGE_GET_NEW_SL

    async def manage_get_new_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            sl = float(update.message.text)
            context.user_data['new_sl'] = sl
            await update.message.reply_text("لطفاً حد سود (TP) جدید را وارد کنید:")
            return MANAGE_GET_NEW_TP
        except ValueError:
            await update.message.reply_text("مقدار نامعتبر است. لطفاً فقط عدد وارد کنید.")
            return MANAGE_GET_NEW_SL

    async def manage_get_new_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            tp = float(update.message.text)
            symbol = context.user_data['manage_symbol']
            sl = context.user_data['new_sl']
            
            result = self.position_manager.update_sl_tp(symbol, sl, tp)
            await update.message.reply_text(result, parse_mode='Markdown', reply_markup=self.main_menu_markup)

            context.user_data.clear()
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("مقدار نامعتبر است. لطفاً فقط عدد وارد کنید.")
            return MANAGE_GET_NEW_TP
    # در فایل: interactive_bot.py (این توابع را به انتهای کلاس اضافه کنید)

    # در فایل: interactive_bot.py

# در فایل: interactive_bot.py (این مجموعه توابع را به انتهای کلاس اضافه کنید)

    async def trade_get_sl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        مرحله دریافت حد ضرر از کاربر.
        """
        try:
            sl_price = float(update.message.text)
            context.user_data['sl'] = sl_price
            await update.message.reply_text(f"حد ضرر: {sl_price}. لطفاً قیمت حد سود (Take-Profit) را وارد کنید:")
            return TRADE_GET_TP
        except ValueError:
            await update.message.reply_text("مقدار نامعتبر است. لطفاً فقط عدد وارد کنید.")
            return TRADE_GET_SL

    async def trade_get_tp(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        مرحله دریافت حد سود و اجرای نهایی معامله.
        """
        try:
            tp_price = float(update.message.text)
            # بازیابی اطلاعات ذخیره شده از مراحل قبل
            symbol = context.user_data['trade_symbol']
            direction = context.user_data['direction']
            sl = context.user_data['sl']
            last_price = self.state_manager.get_symbol_state(symbol, 'last_price')

            if not last_price:
                await update.message.reply_text(f"❌ قیمت لحظه‌ای برای {symbol} در دسترس نیست.", reply_markup=self.main_menu_markup)
                return ConversationHandler.END

            # فراخوانی تابع اصلی برای باز کردن پوزیشن
            result_message = self.position_manager.open_manual_paper_trade(symbol, direction, last_price, sl, tp_price)
            await update.message.reply_text(result_message, reply_markup=self.main_menu_markup)
            
            context.user_data.clear() # پاک کردن حافظه مکالمه
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text("مقدار نامعتبر است. لطفاً فقط عدد وارد کنید.")
            return TRADE_GET_TP
        
    async def cancel_conversation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """
        مکالمه فعلی را لغو می‌کند.
        """
        await update.message.reply_text("عملیات لغو شد.", reply_markup=self.main_menu_markup)
        context.user_data.clear()
        return ConversationHandler.END

    def run(self):
        """ربات را در یک ترد جداگانه اجرا می‌کند."""
        threading.Thread(target=self._runner, daemon=True, name="InteractiveBotThread").start()

    def _runner(self):
        """حلقه رویداد را برای ترد جدید مدیریت می‌کند."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self.application.run_polling(stop_signals=None)
        except Exception:
            print("!!! CRITICAL ERROR IN INTERACTIVE BOT THREAD !!!")
            traceback.print_exc()


