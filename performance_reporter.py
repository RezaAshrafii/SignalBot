# performance_reporter.py
import pandas as pd

def generate_performance_report(closed_positions: list, initial_capital: float = 10000.0) -> str:
    if not closed_positions:
        return "هیچ معامله‌ای برای تحلیل وجود ندارد."

    df = pd.DataFrame(closed_positions)
    
    # --- [اصلاح شد] --- استفاده از کلیدهای صحیح pnl_usd و pnl_percent
    pnl_key = 'pnl_usd'
    
    total_trades = len(df)
    winning_trades = df[df[pnl_key] > 0]
    losing_trades = df[df[pnl_key] <= 0]
    
    total_wins = len(winning_trades)
    total_losses = len(losing_trades)
    
    win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
    
    gross_profit = winning_trades[pnl_key].sum()
    gross_loss = abs(losing_trades[pnl_key].sum())
    total_pnl = gross_profit - gross_loss
    
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    avg_win = winning_trades[pnl_key].mean() if total_wins > 0 else 0
    avg_loss = abs(losing_trades[pnl_key].mean()) if total_losses > 0 else 0
    
    risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

    # --- محاسبه Max Drawdown ---
    df['equity'] = initial_capital + df[pnl_key].cumsum()
    df['peak'] = df['equity'].cummax()
    df['drawdown'] = (df['peak'] - df['equity']) / df['peak']
    max_drawdown = df['drawdown'].max() * 100 if not df['drawdown'].empty else 0

    # --- ساخت گزارش نهایی ---
    report = (
        "--- گزارش نهایی بک‌تست خودکار ---\n\n"
        f"دوره تست: از {df['entry_time'].min().strftime('%Y-%m-%d')} تا {df['close_time'].max().strftime('%Y-%m-%d')}\n"
        f"سرمایه اولیه: ${initial_capital:,.2f}\n"
        "-------------------------------------\n"
        f"سود/زیان کل (Total PnL): ${total_pnl:,.2f}\n"
        f"فاکتور سود (Profit Factor): {profit_factor:.2f}\n"
        f"نرخ برد (Win Rate): {win_rate:.2f}%\n"
        "-------------------------------------\n"
        f"تعداد کل معاملات: {total_trades}\n"
        f"معاملات سودده: {total_wins}\n"
        f"معاملات ضررده: {total_losses}\n"
        "-------------------------------------\n"
        f"میانگین سود هر معامله: ${avg_win:,.2f}\n"
        f"میانگین ضرر هر معامله: ${avg_loss:,.2f}\n"
        f"نسبت ریسک به ریوارد: {risk_reward_ratio:.2f}\n"
        "-------------------------------------\n"
        f"**حداکثر افت سرمایه (Max Drawdown): {max_drawdown:.2f}%**\n"
        "-------------------------------------\n"
    )
    return report