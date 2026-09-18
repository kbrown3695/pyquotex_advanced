"""Risk Management for Binary Options Trading.

Tracks account-level risk, prevents ruin-level losses,
and enforces trading limits based on account status.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, time
import json


@dataclass
class RiskLimits:
    """Account-level risk limit configuration."""

    max_daily_loss_percent: float = 0.10  # Stop trading if lose >10% in a day
    max_weekly_loss_percent: float = 0.20  # Weekly drawdown limit
    max_account_drawdown_percent: float = 0.25  # Max drawdown from peak

    max_consecutive_losses: int = 5  # Reduce sizing after N losses
    cooldown_minutes_after_loss_streak: int = 30  # Pause after loss streak

    risk_free_hours: Tuple[int, int] = (0, 6)  # Don't trade 12am-6am
    high_risk_hours: Tuple[int, int] = (14, 16)  # Use smaller sizes 2pm-4pm

    max_trades_per_hour: int = 10  # Prevent overtrading
    max_trades_per_day: int = 50  # Daily trade limit


@dataclass
class DailyMetrics:
    """Daily risk tracking metrics."""

    date: str
    starting_balance: float
    current_balance: float
    daily_pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    consecutive_losses: int = 0
    peak_balance: float = 0.0

    def daily_loss_percent(self) -> float:
        """Calculate daily loss as percentage of starting balance."""
        if self.starting_balance == 0:
            return 0.0
        loss = self.starting_balance - self.current_balance
        return loss / self.starting_balance if loss > 0 else 0.0

    def drawdown_from_peak(self) -> float:
        """Calculate drawdown from daily peak."""
        if self.peak_balance == 0:
            return 0.0
        drawdown = self.peak_balance - self.current_balance
        return drawdown / self.peak_balance if drawdown > 0 else 0.0

    def win_rate(self) -> float:
        """Calculate win rate for the day."""
        if self.trades == 0:
            return 0.0
        return self.wins / self.trades


class BinaryOptionsRiskManager:
    """Manages account-level risk and enforces trading limits."""

    def __init__(self, limits: RiskLimits):
        """Initialize risk manager.

        Args:
            limits: RiskLimits configuration
        """
        self.limits = limits
        self.daily_metrics: Dict[str, DailyMetrics] = {}
        self.hourly_trade_counts: Dict[str, int] = {}
        self.last_loss_time: Optional[datetime] = None
        self.peak_balance: float = 0.0
        self.initial_balance: Optional[float] = None

    def initialize_session(self, starting_balance: float) -> None:
        """Initialize a trading session with starting balance.

        Args:
            starting_balance: Account balance at session start
        """
        self.initial_balance = starting_balance
        self.peak_balance = starting_balance
        self._get_or_create_daily_metrics(starting_balance)

    def can_trade_now(self) -> Tuple[bool, str]:
        """Check if trading is allowed at this moment.

        Returns:
            (can_trade, reason)
        """
        now = datetime.now()

        # Check risk-free hours (don't trade late night)
        if self._is_risk_free_hour(now):
            return False, f"Risk-free hours: {self.limits.risk_free_hours[0]}-{self.limits.risk_free_hours[1]}am"

        # Check hourly trade limit
        hourly_key = now.strftime("%Y-%m-%d %H:00")
        if self.hourly_trade_counts.get(hourly_key, 0) >= self.limits.max_trades_per_hour:
            return False, f"Hourly trade limit ({self.limits.max_trades_per_hour}) reached"

        # Check daily trade limit
        daily_key = now.strftime("%Y-%m-%d")
        metrics = self.daily_metrics.get(daily_key)
        if metrics and metrics.trades >= self.limits.max_trades_per_day:
            return False, f"Daily trade limit ({self.limits.max_trades_per_day}) reached"

        # Check daily loss limit
        if metrics and metrics.daily_loss_percent() >= self.limits.max_daily_loss_percent:
            return False, f"Daily loss limit ({self.limits.max_daily_loss_percent:.1%}) reached"

        # Check loss streak cooldown
        if self._is_in_loss_streak_cooldown(now):
            mins = self.limits.cooldown_minutes_after_loss_streak
            return False, f"In loss streak cooldown ({mins} minute pause)"

        return True, "OK"

    def get_time_based_risk_adjustment(self) -> float:
        """Get position size adjustment based on time of day.

        Returns 1.0 for normal hours, <1.0 for high-risk hours.
        """
        now = datetime.now()
        hour = now.hour

        # High risk hours use smaller positions
        if self.limits.high_risk_hours[0] <= hour < self.limits.high_risk_hours[1]:
            return 0.75  # 25% smaller positions during 2-4pm

        return 1.0  # Normal sizing

    def record_trade_result(
        self,
        balance_before: float,
        balance_after: float,
        won: bool
    ) -> None:
        """Record the result of a trade.

        Args:
            balance_before: Account balance before trade
            balance_after: Account balance after trade
            won: Whether the trade won or lost
        """
        now = datetime.now()
        daily_key = now.strftime("%Y-%m-%d")
        hourly_key = now.strftime("%Y-%m-%d %H:00")

        pnl = balance_after - balance_before

        # Update daily metrics
        metrics = self._get_or_create_daily_metrics(balance_before)
        metrics.current_balance = balance_after
        metrics.daily_pnl += pnl
        metrics.trades += 1
        if won:
            metrics.wins += 1
            metrics.consecutive_losses = 0
        else:
            metrics.losses += 1
            metrics.consecutive_losses += 1
            self.last_loss_time = now

        # Update peak balance for drawdown calculation
        if balance_after > self.peak_balance:
            self.peak_balance = balance_after
            metrics.peak_balance = self.peak_balance

        # Track hourly trades
        self.hourly_trade_counts[hourly_key] = self.hourly_trade_counts.get(hourly_key, 0) + 1

    def get_account_status(self) -> Dict:
        """Get current account risk status."""
        now = datetime.now()
        daily_key = now.strftime("%Y-%m-%d")
        metrics = self.daily_metrics.get(daily_key)

        if not metrics:
            return {
                'status': 'no_data',
                'daily_pnl': 0.0,
                'daily_loss_percent': 0.0,
                'account_drawdown': 0.0,
            }

        account_drawdown = 0.0
        if self.initial_balance and self.initial_balance > 0:
            account_drawdown = max(0, (self.initial_balance - metrics.current_balance) / self.initial_balance)

        status = 'normal'
        if metrics.daily_loss_percent() > self.limits.max_daily_loss_percent * 0.8:
            status = 'warning'
        if account_drawdown > self.limits.max_account_drawdown_percent * 0.8:
            status = 'warning'

        return {
            'status': status,
            'current_balance': metrics.current_balance,
            'daily_pnl': metrics.daily_pnl,
            'daily_loss_percent': metrics.daily_loss_percent(),
            'account_drawdown': account_drawdown,
            'trades_today': metrics.trades,
            'win_rate_today': metrics.win_rate(),
            'consecutive_losses': metrics.consecutive_losses,
        }

    def _get_or_create_daily_metrics(self, balance: float) -> DailyMetrics:
        """Get or create daily metrics for today."""
        now = datetime.now()
        daily_key = now.strftime("%Y-%m-%d")

        if daily_key not in self.daily_metrics:
            self.daily_metrics[daily_key] = DailyMetrics(
                date=daily_key,
                starting_balance=balance,
                current_balance=balance,
                peak_balance=balance,
            )

        return self.daily_metrics[daily_key]

    def _is_risk_free_hour(self, dt: datetime) -> bool:
        """Check if current time is in risk-free hours."""
        hour = dt.hour
        start, end = self.limits.risk_free_hours
        return start <= hour < end

    def _is_in_loss_streak_cooldown(self, dt: datetime) -> bool:
        """Check if we're in cooldown after loss streak."""
        if not self.last_loss_time:
            return False

        current_metrics = self._get_or_create_daily_metrics(0)
        if current_metrics.consecutive_losses < self.limits.max_consecutive_losses:
            return False

        elapsed_minutes = (dt - self.last_loss_time).total_seconds() / 60
        return elapsed_minutes < self.limits.cooldown_minutes_after_loss_streak


__all__ = [
    'BinaryOptionsRiskManager',
    'RiskLimits',
    'DailyMetrics',
]
