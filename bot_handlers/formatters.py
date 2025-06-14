# bot_handlers/formatters.py
from datetime import datetime

def format_bot_status(state_manager):
    symbols = state_manager.get_all_symbols()
    trading_status = "فعال ✅" if state_manager.get('is_trading_enabled') else "متوقف ⏸️"
    pnl = state_manager.get_global_state('daily_pnl')
    balance = state_manager.get_global_state('account_balance')
    
    text = f"**📊 وضعیت کلی ربات**\n- وضعیت سیگنال‌دهی: *{trading_status}*\n- ارزهای تحت نظر: {', '.join(symbols)}\n\n"
    text += f"**مدیریت مالی:**\n  - موجودی شبیه‌سازی: `${balance:,.2f}`\n  - سود/زیان امروز: `${pnl:,.2f}`\n\n"
    for symbol in symbols:
        price = state_manager.get_symbol_state(symbol).get('last_known_price', 0.0)
        trend = state_manager.get_symbol_state(symbol).get('htf_trend', 'N/A').replace('_', ' ')
        text += f"**{symbol}:**\n  - قیمت: `${price:,.2f}`\n  - روند روز: `{trend}`\n"
    return text

def format_signal_history(state_manager):
    history = state_manager.get_global_state('signal_history')
    if not history: return "📜 **آخرین سیگنال‌ها**\n\nهنوز سیگنالی صادر نشده است."
    text = "📜 **آخرین سیگنال‌ها (تا ۱۰ مورد آخر):**\n\n"
    for signal in history:
        text += f"- **{signal['symbol']}** | {signal['type']} @ `${signal['price']:,.2f}` | زمان: {signal['time']}\n"
    return text

def format_risk_settings(state_manager):
    config = state_manager.get_risk_config()
    text = f"**💰 تنظیمات فعلی مدیریت ریسک:**\n\n"
    text += f"- درصد ریسک در هر معامله: `{config['RISK_PER_TRADE_PERCENT']}%`\n"
    text += f"- حد ضرر روزانه: `{config['DAILY_DRAWDOWN_LIMIT_PERCENT']}%`\n"
    text += f"- نسبت‌های ریسک به ریوارد: `{config['RR_RATIOS']}`\n\n"
    text += "برای تغییر، پارامتر جدید را در فرمت `key=value` ارسال کنید. مثال: `RISK_PER_TRADE_PERCENT=1.5`"
    return text