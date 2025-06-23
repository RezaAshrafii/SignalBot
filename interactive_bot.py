# interactive_bot.py
import threading
import asyncio
import traceback
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import chart_generator
from indicators import calculate_atr
import pytz
# interactive_bot.py
from datetime import datetime, timezone, timedelta
import pandas as pd
import pytz  # --- [اصلاح شد] --- کتابخانه pytz در اینجا ایمپورت شد
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import chart_generator
from fetch_futures_binance import fetch_futures_klines
from indicators import calculate_atr
def analyze_trend_for_report(historical_df, intraday_df):

    """
    این تابع برای تحلیل لحظه‌ای روند در دکمه /trend استفاده می‌شود.
    """
    report_lines = ["**تحلیل روند:**\n"]
    if historical_df.empty or len(historical_df.groupby(pd.Grouper(key='open_time', freq='D'))) < 2:
        return "INSUFFICIENT_DATA", "داده تاریخی کافی برای تحلیل پرایس اکشن (حداقل ۲ روز) وجود ندارد."
    
    daily_data = historical_df.groupby(pd.Grouper(key='open_time', freq='D')).agg(high=('high', 'max'), low=('low', 'min')).dropna()
    last_2_days = daily_data.tail(2)
    if len(last_2_days) < 2:
        return "INSUFFICIENT_DATA", "داده کافی برای مقایسه دو روز اخیر وجود ندارد."

    yesterday, day_before = last_2_days.iloc[-1], last_2_days.iloc[-2]
    
    pa_narrative, pa_score = "دیروز ساختار خنثی (Inside/Expansion Day) مشاهده شد.", 0
    if yesterday['high'] > day_before['high'] and yesterday['low'] > day_before['low']:
        pa_narrative, pa_score = "دیروز ساختار صعودی (HH & HL) ثبت شد.", 2
    elif yesterday['high'] < day_before['high'] and yesterday['low'] < day_before['low']:
        pa_narrative, pa_score = "دیروز ساختار نزولی (LL & LH) ثبت شد.", -2
        
    report_lines.append(f"- **پرایس اکشن (گذشته)**: {pa_narrative} (امتیاز: `{pa_score}`)")
    
    cvd_score = 0
    if intraday_df.empty:
        delta_narrative = "داده‌ای برای تحلیل CVD امروز موجود نیست."
    else:
        intraday_taker_buy = intraday_df['taker_buy_base_asset_volume'].sum()
        intraday_total_volume = intraday_df['volume'].sum()
        current_delta = 2 * intraday_taker_buy - intraday_total_volume
        if current_delta > 0: cvd_score = 1
        elif current_delta < 0: cvd_score = -1
        delta_narrative = f"دلتا تجمعی **امروز** {'مثبت' if cvd_score > 0 else 'منفی' if cvd_score < 0 else 'خنثی'} است (`{current_delta:,.0f}`)."
    
    report_lines.append(f"- **جریان سفارشات (CVD امروز)**: {delta_narrative} (امتیاز: `{cvd_score}`)")
    
    total_score = pa_score + cvd_score
    final_trend = "SIDEWAYS"
    if total_score >= 2: final_trend = "STRONG_UP"
    elif total_score > 0: final_trend = "UP_WEAK"
    elif total_score <= -2: final_trend = "STRONG_DOWN"
    elif total_score < 0: final_trend = "DOWN_WEAK"
    
    report_lines.append(f"\n**نتیجه‌گیری**: با امتیاز کل `{total_score}`، روند امروز **{final_trend}** ارزیابی می‌شود.")
    return final_trend, "\n".join(report_lines)

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
        """پاسخ به کلیک کاربر روی تمام دکمه‌های شیشه‌ای."""
        query = update.callback_query; await query.answer()
        try:
            parts = query.data.split(":"); action = parts[0]
            proposal_id = parts[1] if len(parts) > 1 else None

            # --- [منطق اصلاح‌شده برای حل خطای BadRequest] ---
            if action in ['confirm', 'reject']:
                original_text = query.message.text_markdown.split("\n\n**سود/زیان لحظه‌ای:")[0]
                response_text = ""
                if action == 'confirm':
                    response_text = self.position_manager.confirm_paper_trade(proposal_id, query.message.chat_id, query.message.message_id)
                else: # reject
                    response_text = self.position_manager.reject_proposal(proposal_id)
                
                # ۱. ابتدا پیام اصلی را با نتیجه ویرایش کرده و دکمه‌ها را حذف می‌کنیم
                await query.edit_message_text(text=f"{original_text}\n\n---\n**نتیجه:** {response_text}", parse_mode='Markdown', reply_markup=None)
                
                # ۲. سپس یک پیام جدید برای درخواست بازخورد ارسال می‌کنیم
                if action == 'confirm' or action == 'reject':
                    feedback_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("👍 سیگنال خوب بود", callback_data=f"feedback:{proposal_id}:good"), InlineKeyboardButton("👎 سیگنال بد بود", callback_data=f"feedback:{proposal_id}:bad")]])
                    await context.bot.send_message(chat_id=query.message.chat_id, text="لطفاً کیفیت این پیشنهاد را ارزیابی کنید:", reply_markup=feedback_keyboard)

            elif action == 'set_rr':
                rr_value = parts[2]
                new_text, new_keyboard = self.position_manager.update_proposal_rr(proposal_id, rr_value)
                if new_text and new_keyboard: await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode='Markdown')
            
            elif action == 'feedback':
                feedback = parts[2]
                self.position_manager.log_feedback(proposal_id, feedback)
                # پیام بازخورد را ویرایش کرده و دکمه‌ها را حذف می‌کنیم
                await query.edit_message_text(text=f"{query.message.text}\n\n*بازخورد شما ثبت شد. متشکریم!*", parse_mode='Markdown', reply_markup=None)

        except Exception as e: print(f"[CALLBACK_HANDLER_ERROR] {e}")


        
    async def handle_toggle_silent_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        is_silent = self.state_manager.toggle_silent_mode()
        await update.message.reply_text(f"🔇 حالت سکوت **{'فعال' if is_silent else 'غیرفعال'}** شد.")

    async def handle_nearby_levels_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("در حال آماده‌سازی چارت، لطفاً چند لحظه صبر کنید...")
        for symbol in self.state_manager.get_all_symbols():
            klines = self.state_manager.get_symbol_state(symbol, 'klines_1m')
            state = self.state_manager.get_symbol_snapshot(symbol)
            current_price, levels = state.get('last_price'), state.get('untouched_levels', [])
            if not klines or not current_price or not levels:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=f"داده کافی برای رسم چارت {symbol} وجود ندارد."); continue
            
            nearby_levels = [lvl for lvl in levels if abs(lvl['level'] - current_price) / current_price * 100 <= 2.0]
            if not nearby_levels: continue
            caption = f"🔑 **سطوح کلیدی نزدیک به قیمت فعلی برای {symbol}**"
            image_buffer = chart_generator.generate_chart_image(klines, nearby_levels, current_price, symbol)
            if image_buffer: await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_buffer, caption=caption, parse_mode='Markdown')

    async def handle_open_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        open_positions = self.position_manager.get_open_positions()
        if not open_positions: await update.message.reply_text("📈 **پوزیشن‌های باز**\n\nدرحال حاضر هیچ پوزیشن بازی وجود ندارد.", parse_mode='Markdown'); return
        message = "📈 **پوزیشن‌های باز**\n\n"
        for pos in open_positions:
            entry_time_str = pos.get('entry_time', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
            message += f"▶️ **{pos.get('symbol')} - {pos.get('direction', '').upper()}**\n   - قیمت ورود: `{pos.get('entry_price', 0):,.2f}`\n   - حد ضرر: `{pos.get('stop_loss', 0):,.2f}`\n\n"
        await update.message.reply_text(message, parse_mode='Markdown')
        
    async def handle_daily_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        performance = self.position_manager.get_daily_performance(); profit = performance.get('daily_profit_percent', 0.0); limit = performance.get('drawdown_limit', 0.0)
        profit_str = f"+{profit:.2f}%" if profit >= 0 else f"{profit:.2f}%"; await update.message.reply_text(f"💰 **عملکرد روزانه**\n\n▫️ سود / زیان امروز:  **{profit_str}**\n▫️ حد مجاز افت سرمایه:  `{limit:.2f}%`\n", parse_mode='Markdown')
        
    async def handle_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        report_string = self.position_manager.get_daily_trade_report()
        await update.message.reply_text(report_string, parse_mode='Markdown')

    async def handle_trend_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """گزارش تحلیلی روند را به صورت لحظه‌ای تولید و نمایش می‌دهد."""
        await update.message.reply_text("در حال تحلیل لحظه‌ای روند، لطفاً صبر کنید...")
        message = "📝 **گزارش تحلیل روند روزانه (لحظه‌ای)**\n"
        ny_timezone = pytz.timezone("America/New_York")
        
        for symbol in self.state_manager.get_all_symbols():
            now_utc = datetime.now(timezone.utc)
            # دریافت داده‌های ۱۰ روز اخیر برای تحلیل ساختار
            start_time_utc = now_utc - timedelta(days=10)
            df_full_history = fetch_futures_klines(symbol, '1m', start_time_utc, now_utc)
            if df_full_history.empty:
                message += f"\n--- **{symbol}** ---\nداده‌ای برای تحلیل یافت نشد.\n"
                continue

            # جدا کردن داده‌های تاریخی و روز جاری برای تحلیل
            analysis_end_time_utc = datetime.now(ny_timezone).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
            df_historical = df_full_history[df_full_history['open_time'] < analysis_end_time_utc].copy()
            df_intraday = df_full_history[df_full_history['open_time'] >= analysis_end_time_utc].copy()

            # فراخوانی تابع تحلیل جدید
            htf_trend, trend_report = analyze_trend_for_report(df_historical, df_intraday)
            # آپدیت کردن روند در حافظه برای استفاده بقیه بخش‌ها
            self.state_manager.update_symbol_state(symbol, 'htf_trend', htf_trend)
            
            message += f"\n--- **{symbol}** ---\n{trend_report}\n"
            
        await update.message.reply_text(message, parse_mode='Markdown')

    async def handle_signal_suggestion(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بر اساس روند، بهترین نواحی برای ورود را با جزئیات کامل پیشنهاد می‌دهد."""
        await update.message.reply_text("در حال آماده‌سازی پیشنهادهای استراتژیک...")
        message = "🎯 **پیشنهادهای استراتژیک روز**\n"
        
        for symbol in self.state_manager.get_all_symbols():
            trend = self.state_manager.get_symbol_state(symbol, 'htf_trend')
            # اگر روند هنوز محاسبه نشده، ابتدا آن را با فراخوانی تابع گزارش روند محاسبه کن
            if not trend or trend == 'PENDING':
                await self.handle_trend_report(update, context)
                trend = self.state_manager.get_symbol_state(symbol, 'htf_trend')

            levels = self.state_manager.get_symbol_state(symbol, 'untouched_levels')
            klines = self.state_manager.get_symbol_state(symbol, 'klines_1m')
            level_tests = self.state_manager.get_symbol_state(symbol, 'level_test_counts') or {}
            
            if not trend or not levels or trend == "INSUFFICIENT_DATA": continue
            
            message += f"\n--- **{symbol}** (روند: **{trend}**) ---\n"
            
            if klines and len(klines) > 14:
                atr = calculate_atr(pd.DataFrame(klines))
                last_price = self.state_manager.get_symbol_state(symbol, 'last_price')
                if last_price and atr < last_price * 0.001:
                    message += "⚠️ **هشدار**: نوسانات بازار در حال حاضر پایین است.\n"

            # گسترش سطوح پیشنهادی
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
                message += f"  - `{lvl['level_type']}` در `{lvl['level']:,.2f}` (تست شده: {test_count} بار)\n"
        
        # به جای ارسال پیام جدید، پیام "در حال آماده‌سازی" را ویرایش می‌کنیم
        await context.bot.edit_message_text(text=message, chat_id=update.effective_chat.id, message_id=update.message.message_id + 1, parse_mode='Markdown')

        

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