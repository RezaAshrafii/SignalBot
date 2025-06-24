# alert.py (نسخه نهایی و کامل)

import requests
import json
import time
from datetime import datetime # <<< این خط برای حل خطای اول اضافه شده است

def send_telegram_message(bot_token: str, chat_id: str, text: str, reply_markup=None):
    """
    یک تابع عمومی و ایمن برای ارسال یک پیام به یک کاربر در تلگرام.
    """
    if not all([bot_token, chat_id, text]):
        print("[SendMessage] Error: bot_token, chat_id, or text is missing.")
        return None
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown'
    }
    if reply_markup:
        if isinstance(reply_markup, dict):
            payload['reply_markup'] = json.dumps(reply_markup)
        else:
            payload['reply_markup'] = reply_markup.to_json()

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return response.json().get('result')
    except requests.exceptions.RequestException as e:
        print(f"[SendMessage] HTTP Request Error: {e}")
        return None

def send_bulk_telegram_alert(message: str, bot_token: str, chat_ids: list, reply_markup=None):
    """
    یک پیام را به لیستی از کاربران در تلگرام ارسال می‌کند.
    """
    sent_messages = []
    for chat_id in chat_ids:
        if chat_id:
            # اینجا فرض می‌کنیم نتیجه یک دیکشنری است
            sent_message_dict = send_telegram_message(bot_token, chat_id, message, reply_markup)
            if sent_message_dict:
                # یک آبجکت ساده برای شبیه‌سازی ساختار پیام تلگرام می‌سازیم
                SimpleMessage = type('SimpleMessage', (), {'chat': type('Chat', (), {'id': sent_message_dict.get('chat', {}).get('id')})(), 'message_id': sent_message_dict.get('message_id')})
                sent_messages.append(SimpleMessage())
            time.sleep(0.1)
    return sent_messages

def notify_startup(bot_token, chat_ids, symbols):
    """پیام شروع به کار ربات را ارسال می‌کند."""
    symbol_str = ", ".join(symbols)
    message = (f"✅ **ربات با موفقیت راه‌اندازی شد!**\n\n"
               f"**زمان:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n"
               f"**ارزهای تحت نظر:** `{symbol_str}`")
    send_bulk_telegram_alert(message, bot_token, chat_ids)