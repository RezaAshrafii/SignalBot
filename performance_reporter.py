# location: performance_reporter.py
import pandas as pd
from datetime import datetime, timedelta, timezone

class PerformanceReporter:
    def __init__(self, position_manager):
        self.position_manager = position_manager

    def _get_trades_in_period(self, period_days):
        """معاملات ثبت شده در یک دوره زمانی خاص را فیلتر می‌کند."""
        all_trades = self.position_manager.closed_trades
        if not all_trades:
            return []
        
        start_date = datetime.now(timezone.utc) - timedelta(days=period_days)
        return [t for t in all_trades if t.get('close_time') and t['close_time'] >= start_date]

    def _calculate_streaks(self, trades):
        """طولانی‌ترین رکوردهای برد و باخت متوالی را محاسبه می‌کند."""
        if not trades:
            return 0, 0
            
        win_streak, max_win_streak = 0, 0
        loss_streak, max_loss_streak = 0, 0
        
        for trade in trades:
            if trade.get('pnl_percent', 0) > 0:
                win_streak += 1
                loss_streak = 0
            else:
                loss_streak += 1
                win_streak = 0
            
            max_win_streak = max(max_win_streak, win_streak)
            max_loss_streak = max(max_loss_streak, loss_streak)
            
        return max_win_streak, max_loss_streak

    def _calculate_drawdown(self, trades):
        """بیشترین افت سرمایه (Drawdown) را محاسبه می‌کند."""
        if not trades:
            return 0.0
            
        equity_curve = [100000] # شروع با سرمایه فرضی
        for trade in trades:
            pnl_percent = trade.get('pnl_percent', 0)
            new_equity = equity_curve[-1] * (1 + pnl_percent / 100)
            equity_curve.append(new_equity)
        
        peak = equity_curve[0]
        max_drawdown = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            drawdown = (peak - equity) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                
        return max_drawdown * 100 # به درصد

    def generate_report(self, period_days):
        """یک گزارش عملکرد کامل بر اساس دوره زمانی مشخص شده تولید می‌کند."""
        if period_days == 1: title = "روزانه"
        elif period_days == 7: title = "هفتگی"
        else: title = "ماهانه"
        
        trades = self._get_trades_in_period(period_days)
        
        if not trades:
            return f"📊 **گزارش عملکرد {title}**\n\nهیچ معامله‌ای در این دوره ثبت نشده است."
            
        df = pd.DataFrame(trades)
        
        # محاسبات اصلی
        total_trades = len(df)
        wins = len(df[df['pnl_percent'] > 0])
        losses = total_trades - wins
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl_percent = df['pnl_percent'].sum()
        avg_win = df[df['pnl_percent'] > 0]['pnl_percent'].mean()
        avg_loss = df[df['pnl_percent'] < 0]['pnl_percent'].mean()
        
        # جلوگیری از خطای تقسیم بر صفر
        profit_factor = abs(df[df['pnl_percent'] > 0]['pnl_percent'].sum() / df[df['pnl_percent'] < 0]['pnl_percent'].sum()) if df[df['pnl_percent'] < 0]['pnl_percent'].sum() != 0 else float('inf')
        
        max_win_streak, max_loss_streak = self._calculate_streaks(trades)
        max_drawdown = self._calculate_drawdown(trades)

        # ساخت متن گزارش
        report = (
            f"📊 **گزارش عملکرد {title}** `({total_trades} معامله)` 📊\n\n"
            f"**خلاصه کلی:**\n"
            f"▪️ **نرخ برد (Win Rate):** `{win_rate:.2f}%` ({wins} برد / {losses} باخت)\n"
            f"▪️ **سود/زیان خالص:** `{total_pnl_percent:+.2f}%`\n"
            f"▪️ **فاکتور سود (Profit Factor):** `{profit_factor:.2f}`\n\n"
            f"**آمار پیشرفته:**\n"
            f"▫️ میانگین سود در هر برد: `{avg_win:+.2f}%`\n"
            f"▫️ میانگین ضرر در هر باخت: `{avg_loss:.2f}%`\n"
            f"▫️ بیشترین افت سرمایه (Drawdown): `-{max_drawdown:.2f}%`\n"
            f"▫️ رکورد برد متوالی: `{max_win_streak}`\n"
            f"▫️ رکورد باخت متوالی: `{max_loss_streak}`\n\n"
            f"جهت مشاهده جزئیات معاملات، تاریخچه را بررسی کنید."
        )
        
        return report