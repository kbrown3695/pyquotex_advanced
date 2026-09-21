"""Money Management for Binary Options.

Implements Kelly Criterion for position sizing and account risk management.
Ensures long-term profitability and prevents ruin.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class MoneyManagementConfig:
    """Configuration for money management system."""

    account_balance: float  # Current account balance
    win_rate: float = 0.57  # Historical or expected win rate
    payout_ratio: float = 0.85  # Binary options: earn 85% on win
    loss_ratio: float = 1.0  # Binary options: lose 100% on loss

    max_risk_per_trade: float = 0.05  # Max 5% of account per trade
    max_daily_loss_percent: float = 0.10  # Stop trading if lose >10% in a day
    max_consecutive_losses: int = 5  # Reduce sizing after N losses
    kelly_fraction: float = 1.0  # 1.0 = full Kelly, 0.5 = half Kelly (safer)

    min_confidence_to_trade: float = 0.10  # Don't trade signals below this


@dataclass
class TradeRecord:
    """Record of a single trade."""

    timestamp: datetime
    asset: str
    side: str  # 'BUY' or 'SELL'
    amount_risked: float
    expiration_seconds: int
    signal_confidence: float

    result: Optional[bool] = None  # True = won, False = lost
    pnl: Optional[float] = None  # Profit/loss amount
    note: Optional[str] = None


@dataclass
class AccountStatus:
    """Current account status and daily metrics."""

    balance: float
    daily_pnl: float = 0.0
    trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0
    consecutive_losses: int = 0
    last_trade_time: Optional[datetime] = None

    def win_rate_today(self) -> float:
        """Calculate win rate for today's trades."""
        if self.trades_today == 0:
            return 0.0
        return self.wins_today / self.trades_today


class BinaryOptionsMoneyManager:
    """Manages position sizing and account risk for binary options."""

    def __init__(self, config: MoneyManagementConfig):
        """Initialize money manager.

        Args:
            config: MoneyManagementConfig with account and risk parameters
        """
        self.config = config
        self.account_status = AccountStatus(balance=config.account_balance)
        self.trade_history: list[TradeRecord] = []
        self.daily_reset_time = datetime.now()

    def calculate_kelly_fraction(self) -> float:
        """Calculate Kelly Criterion optimal fraction.

        Formula for binary options:
        Kelly% = (p × b - q) / b
        where:
            p = win_rate
            b = payout_ratio (e.g., 0.85 for 85% payout)
            q = 1 - p (loss probability)

        For Quotex (85% payout, 100% loss):
        Kelly% = (0.57 × 0.85 - 0.43) / 0.85
               = (0.4845 - 0.43) / 0.85
               = 0.128 (12.8% of account)

        We apply kelly_fraction factor to be more conservative:
        Final = Kelly% × kelly_fraction (default 0.5 = half Kelly)
        """
        p = self.config.win_rate
        b = self.config.payout_ratio
        q = 1 - p

        # Kelly Criterion formula
        kelly_percent = (p * b - q) / b if b > 0 else 0

        # Ensure non-negative
        kelly_percent = max(0, kelly_percent)

        # Apply kelly_fraction for safety (0.5 = half Kelly, less aggressive)
        final_kelly = kelly_percent * self.config.kelly_fraction

        return float(final_kelly)

    def get_position_size(self, signal_confidence: float) -> Tuple[float, str]:
        """Calculate position size for a trade.

        Args:
            signal_confidence: Model confidence (0-1)

        Returns:
            (position_size_dollars, sizing_reason)
        """
        # Check if we should trade at all
        if signal_confidence < self.config.min_confidence_to_trade:
            reason = f"Confidence {signal_confidence:.2f} below threshold {self.config.min_confidence_to_trade}"
            return 0.0, reason

        # Check daily loss limit
        if self._is_daily_loss_limit_reached():
            return 0.0, "Daily loss limit reached - no more trades today"

        # Base position size from Kelly Criterion
        kelly_fraction = self.calculate_kelly_fraction()
        base_size = self.config.account_balance * kelly_fraction

        # Adjust for signal confidence
        # Higher confidence = larger position (up to base size)
        # Lower confidence = smaller position (scales down)
        confidence_adjusted = base_size * signal_confidence

        # Apply max risk per trade limit
        max_risk = self.config.account_balance * self.config.max_risk_per_trade
        position_size = min(confidence_adjusted, max_risk)

        # Apply consecutive loss reduction
        loss_reduction = self._get_consecutive_loss_reduction()
        position_size *= loss_reduction

        reason_parts = [
            f"Kelly={kelly_fraction:.1%}",
            f"Confidence={signal_confidence:.2f}",
            f"Account={self.config.account_balance:.2f}",
        ]

        if loss_reduction < 1.0:
            reason_parts.append(f"Loss-reduction={loss_reduction:.1%}")

        reason = " | ".join(reason_parts)
        return float(position_size), reason

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a trade in history.

        Args:
            trade: TradeRecord with trade details
        """
        self.trade_history.append(trade)

        # Update daily stats
        if self._is_new_day():
            self._reset_daily_stats()

        self.account_status.last_trade_time = trade.timestamp
        self.account_status.trades_today += 1

        # Update balance and stats if trade result is known
        if trade.result is not None:
            if trade.result:  # Won
                pnl = trade.amount_risked * self.config.payout_ratio
                self.account_status.wins_today += 1
                self.account_status.consecutive_losses = 0
            else:  # Lost
                pnl = -trade.amount_risked
                self.account_status.losses_today += 1
                self.account_status.consecutive_losses += 1

            self.account_status.balance += pnl
            self.account_status.daily_pnl += pnl
            self.config.account_balance = self.account_status.balance

    def get_account_status(self) -> AccountStatus:
        """Get current account status."""
        return AccountStatus(
            balance=self.account_status.balance,
            daily_pnl=self.account_status.daily_pnl,
            trades_today=self.account_status.trades_today,
            wins_today=self.account_status.wins_today,
            losses_today=self.account_status.losses_today,
            consecutive_losses=self.account_status.consecutive_losses,
            last_trade_time=self.account_status.last_trade_time,
        )

    def get_summary(self) -> Dict:
        """Get comprehensive account summary."""
        total_trades = len(self.trade_history)

        # Calculate overall win rate
        completed_trades = [t for t in self.trade_history if t.result is not None]
        wins = sum(1 for t in completed_trades if t.result)
        losses = sum(1 for t in completed_trades if not t.result)
        overall_wr = wins / total_trades if total_trades > 0 else 0.0

        # Calculate ROI
        initial_balance = self.config.account_balance  # Note: this might be wrong if we're mid-session
        # TODO: track initial balance separately
        roi = 0.0  # Placeholder

        return {
            'current_balance': self.account_status.balance,
            'daily_pnl': self.account_status.daily_pnl,
            'total_trades': total_trades,
            'wins': wins,
            'losses': losses,
            'win_rate': round(overall_wr, 4),
            'daily_status': {
                'trades_today': self.account_status.trades_today,
                'wins_today': self.account_status.wins_today,
                'losses_today': self.account_status.losses_today,
                'win_rate_today': self.account_status.win_rate_today(),
                'consecutive_losses': self.account_status.consecutive_losses,
            },
            'kelly_settings': {
                'win_rate': self.config.win_rate,
                'payout_ratio': self.config.payout_ratio,
                'kelly_fraction': self.calculate_kelly_fraction(),
                'kelly_fraction_multiplier': self.config.kelly_fraction,
            },
        }

    def _is_daily_loss_limit_reached(self) -> bool:
        """Check if we've hit daily loss limit."""
        if self.account_status.daily_pnl < 0:
            loss_percent = abs(self.account_status.daily_pnl) / self.config.account_balance
            if loss_percent >= self.config.max_daily_loss_percent:
                return True
        return False

    def _get_consecutive_loss_reduction(self) -> float:
        """Get position size reduction due to consecutive losses.

        After N consecutive losses, reduce position size to manage risk.
        """
        if self.account_status.consecutive_losses >= self.config.max_consecutive_losses:
            # After 5 losses, reduce to 50% of normal
            return 0.5
        elif self.account_status.consecutive_losses >= 3:
            # After 3 losses, reduce to 75% of normal
            return 0.75
        return 1.0  # No reduction

    def _is_new_day(self) -> bool:
        """Check if it's a new trading day."""
        now = datetime.now()
        return now.date() != self.daily_reset_time.date()

    def _reset_daily_stats(self) -> None:
        """Reset daily statistics."""
        self.daily_reset_time = datetime.now()
        self.account_status.daily_pnl = 0.0
        self.account_status.trades_today = 0
        self.account_status.wins_today = 0
        self.account_status.losses_today = 0
        # Don't reset consecutive_losses - it spans days


__all__ = [
    'BinaryOptionsMoneyManager',
    'MoneyManagementConfig',
    'TradeRecord',
    'AccountStatus',
]
