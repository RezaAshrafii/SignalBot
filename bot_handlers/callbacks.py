# bot_handlers/callbacks.py
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from . import keyboards, formatters

# تعریف وضعیت‌ها برای مکالمه چند مرحله‌ای
ASK_ADD_SYMBOL, ASK_RISK_PARAM = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('دستیار معاملاتی آماده است:', reply_markup=keyboards.get_main_menu_keyboard())

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مسیردهی تمام کلیک‌های روی دکمه‌ها."""
    query = update.callback_query; await query.answer()
    command, *args = query.data.split(':')
    sm = context.bot_data["state_manager"]

    # منوی اصلی
    if command == 'main_menu': await query.edit_message_text('دستیار معاملاتی آماده است:', reply_markup=keyboards.get_main_menu_keyboard())
    # منوی تحلیل
    elif command == 'menu_status': await query.edit_message_text('بخش وضعیت و تحلیل:', reply_markup=keyboards.get_status_menu_keyboard())
    elif command == 'status_overview': await query.edit_message_text(formatters.format_bot_status(sm), parse_mode='Markdown', reply_markup=keyboards.get_back_button('menu_status'))
    elif command == 'status_history': await query.edit_message_text(formatters.format_signal_history(sm), parse_mode='Markdown', reply_markup=keyboards.get_back_button('menu_status'))
    elif command == 'ask_analysis_symbol': await query.edit_message_text('لطفاً ارز مورد نظر را انتخاب کنید:', reply_markup=keyboards.get_symbol_selection_keyboard('show_analysis_menu', sm.get_all_symbols()))
    # منوی پیکربندی
    elif command == 'menu_config': await query.edit_message_text('بخش پیکربندی و مدیریت:', reply_markup=keyboards.get_config_menu_keyboard(sm))
    elif command == 'toggle_trading':
        sm.toggle_trading(not sm.is_trading_enabled)
        await query.edit_message_text(formatters.format_bot_status(sm), parse_mode='Markdown', reply_markup=keyboards.get_config_menu_keyboard(sm))
    elif command == 'config_symbols': await query.edit_message_text('ارزهای تحت نظر را مدیریت کنید:', reply_markup=keyboards.get_symbol_management_keyboard(sm.get_all_symbols()))
    # مدیریت ارزها
    elif command == 'remove_symbol':
        if sm.remove_symbol(args[0]):
            await query.edit_message_text(f"ارز {args[0]} با موفقیت حذف شد. ربات در حال راه‌اندازی مجدد است...", reply_markup=keyboards.get_config_menu_keyboard(sm))
            context.bot_data["main_app"].restart_services()
        else:
            await query.edit_message_text('حذف ارز امکان‌پذیر نیست (حداقل یک ارز باید باقی بماند).', reply_markup=keyboards.get_symbol_management_keyboard(sm.get_all_symbols()))
    return None

# کنترل‌کننده‌های مکالمه (Conversation)
async def add_symbol_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    await query.edit_message_text("لطفاً نام نماد جدید را با فرمت `BTCUSDT` ارسال کنید. برای لغو /cancel را بزنید.")
    return ASK_ADD_SYMBOL

async def receive_added_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sm = context.bot_data["state_manager"]
    symbol = update.message.text.upper().strip()
    if sm.add_symbol(symbol):
        await update.message.reply_text(f"ارز {symbol} با موفقیت اضافه شد. ربات در حال راه‌اندازی مجدد است...")
        context.bot_data["main_app"].restart_services()
    else:
        await update.message.reply_text(f"ارز {symbol} از قبل وجود داشت.")
    return ConversationHandler.END

async def config_risk_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    sm = context.bot_data["state_manager"]
    await query.edit_message_text(formatters.format_risk_settings(sm), parse_mode='Markdown')
    return ASK_RISK_PARAM

async def receive_risk_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sm = context.bot_data["state_manager"]
    try:
        key, value = update.message.text.split('=')
        key, value = key.strip().upper(), float(value.strip())
        if sm.update_risk_config(key, value):
            await update.message.reply_text(f"پارامتر {key} با موفقیت به {value} تغییر یافت.")
        else:
            await update.message.reply_text(f"نام پارامتر `{key}` نامعتبر است.", parse_mode='Markdown')
    except Exception:
        await update.message.reply_text("فرمت ورودی اشتباه است. مثال: `RISK_PER_TRADE_PERCENT=1.5`", parse_mode='Markdown')
    
    await update.message.reply_text('بخش پیکربندی و مدیریت:', reply_markup=keyboards.get_config_menu_keyboard(sm))
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # اگر از طریق دکمه باشد
    if update.callback_query:
        await update.callback_query.edit_message_text("عملیات لغو شد.", reply_markup=keyboards.get_config_menu_keyboard(context.bot_data["state_manager"]))
    # اگر از طریق دستور /cancel باشد
    else:
        await update.message.reply_text("عملیات لغو شد.", reply_markup=keyboards.get_main_menu_keyboard())
    return ConversationHandler.END