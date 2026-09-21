#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: Account Constraint Tracker
====================================
Monitors and enforces daily trading limits, account balance constraints,
and minimum trade amounts to prevent over-trading and account violations.

Features:
- Real-time dayLimit/dayBalance monitoring from WebSocket
- Automatic trading halt when limits exceeded
- Account mode detection (demo vs live)
- Minimum trade amount validation
- Constraint violation logging for compliance
- Position sizing adjustment based on available balance
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Tuple
from enum import Enum


class AccountMode(Enum):
    """Account trading mode."""
    DEMO = "PRACTICE"
    LIVE = "LIVE"


class ConstraintStatus(Enum):
    """Trading constraint status."""
    OK = "OK"
    WARNING = "WARNING"
    HALT = "HALT"


@dataclass
class AccountConstraints:
    """Current account constraints snapshot."""
    timestamp: float
    account_mode: str  # "DEMO" or "LIVE"
    live_balance: float
    demo_balance: float
    day_limit: float
    day_balance: float
    minimum_amount: float
    trades_today: int = 0
    total_traded_today: float = 0.0
    constraint_status: str = ConstraintStatus.OK.value
    halt_reason: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class AccountConstraintTracker:
    """
    Monitors account constraints and prevents invalid trading.

    Constraints enforced:
    1. dayLimit: Maximum daily trading volume
    2. dayBalance: Remaining daily budget
    3. minimum_amount: Minimum trade size (from profile)
    4. Account mode: Demo/Live separation
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize constraint tracker.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # Current constraint state
        self.current_constraints: Optional[AccountConstraints] = None

        # Tracking
        self.trades_today: int = 0
        self.total_traded_today: float = 0.0
        self.violations_today: int = 0
        self.halt_active: bool = False
        self.halt_reason: Optional[str] = None

        # History for debugging
        self.constraint_history: list = []
        self.MAX_HISTORY = 1000

    def update_from_websocket(
        self,
        account_balance: Dict,
        profile_data: Optional[Dict] = None,
        account_is_demo: int = 1
    ) -> AccountConstraints:
        """Update constraints from WebSocket account data.

        Args:
            account_balance: Dict with keys: liveBalance, demoBalance, dayLimit, dayBalance
            profile_data: Optional profile dict with minimum_amount
            account_is_demo: 1 for demo, 0 for live

        Returns:
            Current AccountConstraints snapshot
        """
        import time

        live_balance = float(account_balance.get('liveBalance', 0.0))
        demo_balance = float(account_balance.get('demoBalance', 0.0))
        day_limit = float(account_balance.get('dayLimit', 0.0))
        day_balance = float(account_balance.get('dayBalance', 0.0))

        # Profile minimum
        minimum_amount = 1.0
        if profile_data and isinstance(profile_data, dict):
            minimum_amount = float(profile_data.get('minimum_amount', 1.0))

        # Determine account mode
        account_mode = AccountMode.DEMO.value if account_is_demo else AccountMode.LIVE.value

        # Determine constraint status
        status, halt_reason = self._evaluate_constraints(
            day_limit, day_balance, minimum_amount, live_balance, demo_balance, account_mode
        )

        # Create constraints snapshot
        self.current_constraints = AccountConstraints(
            timestamp=time.time(),
            account_mode=account_mode,
            live_balance=live_balance,
            demo_balance=demo_balance,
            day_limit=day_limit,
            day_balance=day_balance,
            minimum_amount=minimum_amount,
            trades_today=self.trades_today,
            total_traded_today=self.total_traded_today,
            constraint_status=status.value,
            halt_reason=halt_reason
        )

        # Track halt state
        self.halt_active = status == ConstraintStatus.HALT
        self.halt_reason = halt_reason

        # Log if status changed
        self._log_constraint_change()

        # Store in history
        self.constraint_history.append(self.current_constraints.to_dict())
        if len(self.constraint_history) > self.MAX_HISTORY:
            self.constraint_history.pop(0)

        return self.current_constraints

    def _evaluate_constraints(
        self,
        day_limit: float,
        day_balance: float,
        minimum_amount: float,
        live_balance: float,
        demo_balance: float,
        account_mode: str
    ) -> Tuple[ConstraintStatus, Optional[str]]:
        """Evaluate if trading is allowed based on constraints.

        Returns:
            Tuple of (ConstraintStatus, halt_reason)
        """
        # Check 1: Day balance exhausted
        if day_limit > 0 and day_balance <= 0:
            return ConstraintStatus.HALT, "Daily limit exhausted (dayBalance=0)"

        # Check 2: Insufficient balance for minimum trade
        if day_balance < minimum_amount:
            return ConstraintStatus.HALT, f"Insufficient balance for minimum trade (${day_balance:.2f} < ${minimum_amount:.2f})"

        # Check 3: Day balance < 2x minimum (warning, not halt)
        if day_balance < (minimum_amount * 2):
            return ConstraintStatus.WARNING, f"Low balance approaching limit (${day_balance:.2f})"

        # Check 4: Live account with zero balance
        if account_mode == AccountMode.LIVE.value and live_balance <= 0:
            return ConstraintStatus.HALT, "Live account has no balance"

        # Check 5: Demo account with zero balance
        if account_mode == AccountMode.DEMO.value and demo_balance <= 0:
            return ConstraintStatus.HALT, "Demo account has no balance"

        return ConstraintStatus.OK, None

    def can_trade(self, proposed_amount: float) -> Tuple[bool, str]:
        """Check if a trade is allowed.

        Args:
            proposed_amount: Amount proposed for trade

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        if not self.current_constraints:
            return False, "No constraints loaded yet"

        c = self.current_constraints

        # Check 1: Halt status active
        if self.halt_active:
            return False, f"Trading halted: {self.halt_reason}"

        # Check 2: Proposed amount violates minimum
        if proposed_amount < c.minimum_amount:
            return False, f"Amount ${proposed_amount:.2f} below minimum ${c.minimum_amount:.2f}"

        # Check 3: Proposed amount exceeds day balance
        if proposed_amount > c.day_balance:
            return False, f"Amount ${proposed_amount:.2f} exceeds remaining daily balance ${c.day_balance:.2f}"

        # Check 4: Proposed amount would exceed day limit
        if c.day_limit > 0 and (self.total_traded_today + proposed_amount) > c.day_limit:
            remaining = c.day_limit - self.total_traded_today
            return False, f"Amount would exceed daily limit (${remaining:.2f} remaining)"

        return True, "OK"

    def get_max_trade_amount(self) -> float:
        """Get maximum allowed trade amount based on current constraints.

        Returns:
            Maximum trade amount in dollars
        """
        if not self.current_constraints:
            return 0.0

        c = self.current_constraints

        if self.halt_active:
            return 0.0

        # Minimum trade amount
        max_amount = c.minimum_amount

        # Limited by day balance
        if c.day_balance > 0:
            max_amount = min(max_amount, c.day_balance)
        else:
            return 0.0

        # Limited by day limit
        if c.day_limit > 0:
            remaining_limit = c.day_limit - self.total_traded_today
            max_amount = min(max_amount, remaining_limit)

        return max_amount

    def record_trade(self, amount: float) -> None:
        """Record a completed trade for tracking purposes.

        Args:
            amount: Trade amount in dollars
        """
        self.trades_today += 1
        self.total_traded_today += amount

        self.logger.info(
            f"Trade recorded: ${amount:.2f} (Total today: ${self.total_traded_today:.2f}, "
            f"Remaining: ${self.current_constraints.day_balance - amount:.2f})"
        )

    def _log_constraint_change(self) -> None:
        """Log constraint status changes."""
        if not self.current_constraints:
            return

        c = self.current_constraints
        status = c.constraint_status

        if status == ConstraintStatus.HALT.value:
            self.violations_today += 1
            self.logger.warning(
                f"🚫 TRADING HALT: {c.halt_reason} | "
                f"Mode={c.account_mode} DayBalance=${c.day_balance:.2f} DayLimit=${c.day_limit:.2f}"
            )
        elif status == ConstraintStatus.WARNING.value:
            self.logger.warning(
                f"⚠️  CONSTRAINT WARNING: {c.halt_reason} | "
                f"Mode={c.account_mode} DayBalance=${c.day_balance:.2f}"
            )

    def get_status(self) -> Dict:
        """Get current constraint status.

        Returns:
            Dict with constraint status, account info, and trading limits
        """
        if not self.current_constraints:
            return {"error": "No constraints loaded"}

        c = self.current_constraints
        return {
            "timestamp": c.timestamp,
            "account_mode": c.account_mode,
            "constraint_status": c.constraint_status,
            "halt_reason": c.halt_reason,
            "balances": {
                "live": c.live_balance,
                "demo": c.demo_balance,
                "day_balance": c.day_balance,
                "day_limit": c.day_limit
            },
            "trading_today": {
                "trades": c.trades_today,
                "total": c.total_traded_today,
                "violations": self.violations_today
            },
            "limits": {
                "minimum_amount": c.minimum_amount,
                "max_trade_allowed": self.get_max_trade_amount(),
                "can_trade": not self.halt_active
            }
        }

    def reset_daily_tracking(self) -> None:
        """Reset daily trade tracking (typically called at market open)."""
        self.trades_today = 0
        self.total_traded_today = 0.0
        self.violations_today = 0
        self.halt_active = False
        self.halt_reason = None
        self.logger.info("Daily tracking reset")

    def export_history(self, filepath: str) -> None:
        """Export constraint history to file for compliance audit.

        Args:
            filepath: Path to save history JSON
        """
        with open(filepath, 'w') as f:
            json.dump({
                "exported_at": datetime.now().isoformat(),
                "total_violations": self.violations_today,
                "total_trades": self.trades_today,
                "total_traded": self.total_traded_today,
                "history": self.constraint_history
            }, f, indent=2)
        self.logger.info(f"Constraint history exported to {filepath}")
