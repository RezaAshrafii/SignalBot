import requests

def send_telegram_alert(msg, bot_token, chat_id):
    """Sends a single alert to a specified Telegram chat with Markdown format."""
    
    # --- [دستور دیباگ جدید] ---
    # این خط توکن و آیدی چت را قبل از استفاده، در لاگ چاپ می‌کند
    # ما از | در دو طرف مقادیر استفاده می‌کنیم تا فاصله‌های احتمالی مشخص شوند
    print(f"[DEBUG] Using Token: |{bot_token}| for Chat ID: |{chat_id}|")
    # --- [پایان دیباگ] ---

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            print(f"[ALERT][Telegram Error] Status: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"[ALERT][Telegram Connection Exception]: {e}")

def send_bulk_telegram_alert(msg, bot_token, chat_ids):
    """Sends a message to a list of Telegram chats."""
    for chat_id in chat_ids:
        send_telegram_alert(msg, bot_token, chat_id)

def notify_startup(bot_token, chat_ids, symbols):
    """
    Notifies that the bot has started successfully for specific symbols.
    """
    symbol_str = ", ".join(symbols)
    msg = f"✅ **ربات معامله‌گر برای ارزهای {symbol_str} با موفقیت راه‌اندازی شد و در حال نظارت بر بازار است.**"
    send_bulk_telegram_alert(msg, bot_token, chat_ids)

# This block allows for direct testing of the alert functionality.
if __name__ == "__main__":
    test_bot_token = "7763608030:AAFHw6vzddwZ4YVa9gXfC5PS-bbKZBSnXyw"
    test_chat_ids = ["6697060159", "7158872719"]
    test_symbols = ["BTCUSDT", "ETHUSDT"]
    
    print("Sending startup notification for testing...")
    notify_startup(test_bot_token, test_chat_ids, test_symbols)
    print("Test complete.")