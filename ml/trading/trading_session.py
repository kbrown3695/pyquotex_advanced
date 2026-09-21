"""Trading Session Management for Binary Options.

Integrates money management and risk management to provide
trading recommendations and account tracking.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from ml.trading.money_manager import (
    BinaryOptionsMoneyManager,
    MoneyManagementConfig,
    TradeRecord,
)
from ml.trading.risk_manager import (
    BinaryOptionsRiskManager,
    RiskLimits,
)

logger = logging.getLogger(__name__)


@dataclass
class TradeRecommendation:
    """Recommendation for whether and how to trade a signal."""

    should_trade: bool
    position_size: float
    reasons: list[str]  # Reasons for or against trading

    money_manager_reason: str = ""
    risk_manager_reason: str = ""
    kelly_fraction: float = 0.0


class BinaryOptionsTradingSession:
    """Manages a trading session with money and risk management."""

    def __init__(
        self,
        starting_balance: float,
        money_config: Optional[MoneyManagementConfig] = None,
        risk_config: Optional[RiskLimits] = None,
    ):
        """Initialize trading session.

        Args:
            starting_balance: Starting account balance
            money_config: Money management configuration
            risk_config: Risk management configuration
        """
        self.starting_balance = starting_balance

        # Initialize money manager
        if money_config is None:
            money_config = MoneyManagementConfig(account_balance=starting_balance)
        self.money_manager = BinaryOptionsMoneyManager(money_config)

        # Initialize risk manager
        if risk_config is None:
            risk_config = RiskLimits()
        self.risk_manager = BinaryOptionsRiskManager(risk_config)
        self.risk_manager.initialize_session(starting_balance)

        logger.info(f"Trading session initialized with balance: ${starting_balance:.2f}")

    def update_balance(self, new_balance: float) -> None:
        """Update session with actual account balance from broker.

        Args:
            new_balance: Updated balance from Quotex
        """
        self.starting_balance = new_balance

        # Update money manager
        if self.money_manager and hasattr(self.money_manager, 'config'):
            self.money_manager.config.account_balance = new_balance

        # Update risk manager
        if self.risk_manager and hasattr(self.risk_manager, '_update_session_balance'):
            self.risk_manager._update_session_balance(new_balance)

        logger.info(f"Trading session balance updated: ${new_balance:.2f}")

    def get_trade_recommendation(
        self,
        signal_confidence: float,
        asset: str = "DEFAULT",
        expiration_seconds: int = 300,
    ) -> TradeRecommendation:
        """Get recommendation for whether to trade a signal.

        Args:
            signal_confidence: Model confidence (0-1)
            asset: Asset being traded
            expiration_seconds: Trade expiration time in seconds

        Returns:
            TradeRecommendation with sizing and reasons
        """
        reasons = []

        # Check risk manager first
        can_trade, risk_reason = self.risk_manager.can_trade_now()
        if not can_trade:
            return TradeRecommendation(
                should_trade=False,
                position_size=0.0,
                reasons=[risk_reason],
                risk_manager_reason=risk_reason,
            )

        # Get position size from money manager
        position_size, money_reason = self.money_manager.get_position_size(signal_confidence)

        if position_size <= 0:
            return TradeRecommendation(
                should_trade=False,
                position_size=0.0,
                reasons=[money_reason],
                money_manager_reason=money_reason,
            )

        # Apply time-based risk adjustment
        time_adjustment = self.risk_manager.get_time_based_risk_adjustment()
        adjusted_size = position_size * time_adjustment

        reasons = [
            f"✓ Risk manager: {risk_reason}",
            f"✓ Money manager: {money_reason}",
        ]

        if time_adjustment < 1.0:
            reasons.append(f"⚠ Time-based reduction: {time_adjustment:.1%}")

        kelly = self.money_manager.calculate_kelly_fraction()

        return TradeRecommendation(
            should_trade=True,
            position_size=adjusted_size,
            reasons=reasons,
            money_manager_reason=money_reason,
            risk_manager_reason=risk_reason,
            kelly_fraction=kelly,
        )

    def execute_trade(
        self,
        asset: str,
        side: str,
        position_size: float,
        signal_confidence: float,
        expiration_seconds: int = 300,
        result: Optional[bool] = None,
    ) -> None:
        """Record a trade execution.

        Args:
            asset: Asset being traded
            side: 'BUY' or 'SELL'
            position_size: Amount risked in dollars
            signal_confidence: Model confidence
            expiration_seconds: Trade expiration time
            result: True if won, False if lost, None if pending
        """
        trade = TradeRecord(
            timestamp=datetime.now(),
            asset=asset,
            side=side,
            amount_risked=position_size,
            expiration_seconds=expiration_seconds,
            signal_confidence=signal_confidence,
            result=result,
        )

        self.money_manager.record_trade(trade)

        # If trade result is known, update risk manager
        if result is not None:
            current_balance = self.money_manager.account_status.balance
            balance_before = current_balance - (position_size * self.money_manager.config.payout_ratio if result else -position_size)
            self.risk_manager.record_trade_result(
                balance_before=balance_before,
                balance_after=current_balance,
                won=result,
            )

            logger.info(
                f"Trade recorded: {asset} {side} ${position_size:.2f} "
                f"(conf={signal_confidence:.2f}) - {'WIN' if result else 'LOSS'}"
            )

    def get_session_summary(self) -> Dict:
        """Get comprehensive session summary."""
        money_summary = self.money_manager.get_summary()
        risk_status = self.risk_manager.get_account_status()

        return {
            'money_manager': money_summary,
            'risk_status': risk_status,
            'session_summary': {
                'starting_balance': self.starting_balance,
                'current_balance': self.money_manager.account_status.balance,
                'total_pnl': self.money_manager.account_status.balance - self.starting_balance,
                'roi': ((self.money_manager.account_status.balance - self.starting_balance) / self.starting_balance * 100) if self.starting_balance > 0 else 0,
            }
        }


__all__ = [
    'BinaryOptionsTradingSession',
    'TradeRecommendation',
]
