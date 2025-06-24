# bot_handlers/formatters.py (نسخه کامل و نهایی)

from datetime import datetime
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# =================================================================
# توابع قبلی شما (بدون تغییر)
# =================================================================
def format_bot_status(state_manager):
    # ... (کد این تابع بدون تغییر باقی می‌ماند)
    pass

def format_signal_history(state_manager):
    # ... (کد این تابع بدون تغییر باقی می‌ماند)
    pass

def format_risk_settings(state_manager):
    # ... (کد این تابع بدون تغییر باقی می‌ماند)
    pass

# =================================================================
# بخش جدید: این دو تابع به انتهای فایل اضافه می‌شوند
# =================================================================

def format_proposal_message(proposal_data: dict, proposal_id: str, selected_rr: int = 2):
    """
    یک پکیج سیگنال را دریافت کرده و آن را به یک پیام متنی زیبا و دکمه‌های
    شیشه‌ای برای ارسال در تلگرام تبدیل می‌کند.
    """
    # استخراج اطلاعات از پکیج سیگنال
    symbol = proposal_data.get('symbol', 'N/A')
    direction = proposal_data.get('type', 'N/A') # استفاده از 'type' به عنوان جهت
    entry_price = proposal_data.get('level', 0)
    stop_loss = proposal_data.get('stop_loss', 0)
    setup = proposal_data.get('setup', 'N/A')
    reasons = proposal_data.get('reasons', [f"✅ ستاپ: {setup}"])
    session = proposal_data.get('session', 'N/A')

    # محاسبه حد سود بر اساس ریسک به ریوارد
    if entry_price == 0 or stop_loss == 0:
        risk_amount = 0
        tp_price = 0
    else:
        risk_amount = abs(entry_price - stop_loss)
        tp_price = entry_price + (risk_amount * selected_rr) if direction == 'Buy' or direction == 'BUY' else entry_price - (risk_amount * selected_rr)

    # ساخت متن پیام با فرمت Markdown
    reasons_str = "\n".join(reasons)
    message_text = (
        f"**📣 پیشنهاد سیگنال جدید 📣**\n\n"
        f"**ارز**: `{symbol}`\n"
        f"**جهت**: {'🟢 خرید (Buy)' if direction.upper() == 'BUY' else '🔴 فروش (Sell)'}\n"
        f"**سشن**: `{session}`\n\n"
        f"**دلایل:**\n{reasons_str}\n\n"
        f"**جزئیات معامله (R/R: 1:{selected_rr}):**\n"
        f" - قیمت ورود: `{entry_price:,.4f}`\n"
        f" - حد ضرر: `{stop_loss:,.4f}`\n"
        f" - حد سود: `{tp_price:,.4f}`\n\n"
        f"**سود/زیان لحظه‌ای: `-`**"
    )
    
    # ساخت دکمه‌های شیشه‌ای (Inline Keyboard)
    keyboard_buttons = [
        [
            InlineKeyboardButton("✅ تایید ورود", callback_data=f"confirm:{proposal_id}"),
            InlineKeyboardButton("❌ رد کردن", callback_data=f"reject:{proposal_id}")
        ],
        [
            InlineKeyboardButton(f"R/R 1:1{' ✅' if selected_rr == 1 else ''}", callback_data=f"set_rr:{proposal_id}:1"),
            InlineKeyboardButton(f"R/R 1:2{' ✅' if selected_rr == 2 else ''}", callback_data=f"set_rr:{proposal_id}:2"),
            InlineKeyboardButton(f"R/R 1:3{' ✅' if selected_rr == 3 else ''}", callback_data=f"set_rr:{proposal_id}:3")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    return message_text, reply_markup


def format_trend_report(symbol: str, htf_trend: str, trend_report: str):
    """
    گزارش روند تولید شده را برای نمایش در تلگرام فرمت‌بندی می‌کند.
    (این تابع برای هماهنگی با interactive_bot اضافه شده است)
    """
    message = f"--- **{symbol}** ---\n{trend_report}\n"
    return message