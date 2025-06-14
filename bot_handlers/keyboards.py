# bot_handlers/keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu_keyboard():
    """منوی اصلی را ایجاد می‌کند."""
    keyboard = [
        [InlineKeyboardButton("📊 وضعیت و تحلیل", callback_data='menu_status')],
        [InlineKeyboardButton("⚙️ پیکربندی و مدیریت", callback_data='menu_config')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_status_menu_keyboard():
    """منوی بخش "وضعیت و تحلیل" را ایجاد می‌کند."""
    keyboard = [
        [InlineKeyboardButton("📈 وضعیت کلی ربات", callback_data='status_overview')],
        [InlineKeyboardButton("📉 تحلیل ارز", callback_data='ask_analysis_symbol')],
        [InlineKeyboardButton("📜 آخرین سیگنال‌ها", callback_data='status_history')],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_config_menu_keyboard(state_manager):
    """منوی بخش "پیکربندی و مدیریت" را ایجاد می‌کند."""
    trading_status = state_manager.get('is_trading_enabled')
    toggle_text = "⏸️ غیرفعال کردن ربات" if trading_status else "▶️ فعال کردن ربات"
    
    keyboard = [
        [InlineKeyboardButton("➕/➖ مدیریت ارزها", callback_data='config_symbols')],
        [InlineKeyboardButton("💰 تنظیمات ریسک", callback_data='config_risk')],
        [InlineKeyboardButton(toggle_text, callback_data='toggle_trading')],
        [InlineKeyboardButton("⬅️ بازگشت", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_symbol_management_keyboard(symbols):
    """منوی مدیریت ارزها (حذف/اضافه) را ایجاد می‌کند."""
    keyboard = [[InlineKeyboardButton(f"❌ حذف {s}", callback_data=f"remove_symbol:{s}")] for s in symbols]
    keyboard.append([InlineKeyboardButton("➕ افزودن ارز جدید", callback_data="add_symbol_prompt")])
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data='menu_config')])
    return InlineKeyboardMarkup(keyboard)
    
def get_symbol_selection_keyboard(command_prefix, symbols):
    """منوی انتخاب ارز برای یک دستور خاص را ایجاد می‌کند."""
    keyboard = [[InlineKeyboardButton(s, callback_data=f'{command_prefix}:{s}')] for s in symbols]
    keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data='menu_status')])
    return InlineKeyboardMarkup(keyboard)
    
def get_back_button(callback_data='main_menu'):
    """یک کیبورد فقط با دکمه بازگشت ایجاد می‌کند."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ بازگشت", callback_data=callback_data)]])