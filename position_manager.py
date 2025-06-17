class PositionManager:
    def __init__(self, state_manager, bot_token, chat_ids, risk_config, active_monitors):
        self.state_manager = state_manager
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.risk_config = risk_config
        self.active_monitors = active_monitors
        self.active_positions = {}
        self.closed_trades = []
        self.lock = threading.Lock()

    def get_open_positions(self):
        with self.lock:
            return list(self.active_positions.values())
            
    def get_daily_performance(self):
        with self.lock:
            today = datetime.now(timezone.utc).date()
            # این تابع فرض می‌کند که close_time یک آبجکت datetime است
            pnl = sum(t.get('pnl_percent', 0) for t in self.closed_trades if t.get('close_time') and hasattr(t['close_time'], 'date') and t['close_time'].date() == today)
            return {
                "daily_profit_percent": pnl,
                "drawdown_limit": self.risk_config.get("DAILY_DRAWDOWN_LIMIT_PERCENT", 3.0)
            }