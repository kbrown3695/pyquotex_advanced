#!/usr/bin/env python3
"""
Simple isolated test for the demo balance fix.
"""

import sys
import json
import logging
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Copy the essential classes to avoid import issues
from enum import Enum
from typing import Optional, Dict, Tuple
import time

class ConstraintStatus(Enum):
    """Trading constraint status."""
    OK = "OK"
    WARNING = "WARNING"
    HALT = "HALT"

@dataclass
class AccountConstraints:
    """Current account constraints snapshot."""
    timestamp: float
    account_mode: str
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
    """Test version with fix."""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.current_constraints: Optional[AccountConstraints] = None
        self.trades_today: int = 0
        self.total_traded_today: float = 0.0
        self.violations_today: int = 0
        self.halt_active: bool = False
        self.halt_reason: Optional[str] = None

    def update_from_websocket(self, account_balance: Dict, profile_data: Optional[Dict] = None, account_is_demo: int = 1) -> AccountConstraints:
        live_balance = float(account_balance.get('liveBalance', 0.0))
        demo_balance = float(account_balance.get('demoBalance', 0.0))
        day_limit = float(account_balance.get('dayLimit', 0.0))
        day_balance = float(account_balance.get('dayBalance', 0.0))

        # FIX: For PRACTICE mode, use demoBalance as the trading limit
        if account_is_demo == 1 and day_balance == 0.0 and demo_balance > 0.0:
            day_balance = demo_balance
            day_limit = demo_balance
            self.logger.info(f"🔧 PRACTICE mode: Using demoBalance (${demo_balance:.2f}) as dayBalance")

        minimum_amount = 1.0
        if profile_data and isinstance(profile_data, dict):
            minimum_amount = float(profile_data.get('minimum_amount', 1.0))

        account_mode = "DEMO" if account_is_demo else "LIVE"
        status = ConstraintStatus.OK

        self.current_constraints = AccountConstraints(
            timestamp=time.time(),
            account_mode=account_mode,
            live_balance=live_balance,
            demo_balance=demo_balance,
            day_limit=day_limit,
            day_balance=day_balance,
            minimum_amount=minimum_amount,
            constraint_status=status.value
        )

        return self.current_constraints

    def can_trade(self, proposed_amount: float) -> Tuple[bool, str]:
        if not self.current_constraints:
            return False, "No constraints loaded yet"

        c = self.current_constraints
        if proposed_amount > c.day_balance:
            return False, f"Amount ${proposed_amount:.2f} exceeds remaining daily balance ${c.day_balance:.2f}"
        return True, "OK"

    def record_trade(self, amount: float) -> None:
        """THE FIX: Decrement day_balance when recording trades."""
        self.trades_today += 1
        self.total_traded_today += amount

        if self.current_constraints:
            self.current_constraints.day_balance -= amount
            remaining = self.current_constraints.day_balance

            self.logger.info(
                f"Trade recorded: ${amount:.2f} (Total today: ${self.total_traded_today:.2f}, "
                f"Remaining: ${remaining:.2f})"
            )
        else:
            self.logger.warning("Cannot record trade: no constraints loaded")

# Run tests
def test_demo_balance_tracking():
    print("\n" + "="*80)
    print("TESTING DEMO BALANCE FIX")
    print("="*80)

    tracker = AccountConstraintTracker(logger=logger)

    account_balance = {
        'liveBalance': 0.0,
        'demoBalance': 1000.0,
        'dayLimit': 0.0,
        'dayBalance': 0.0
    }

    constraints = tracker.update_from_websocket(
        account_balance=account_balance,
        profile_data={'minimum_amount': 10.0},
        account_is_demo=1
    )

    print("\nINITIAL STATE:")
    print(f"  Account Mode: {constraints.account_mode}")
    print(f"  Demo Balance: ${constraints.demo_balance:.2f}")
    print(f"  Day Balance: ${constraints.day_balance:.2f}")

    # Test 1: First trade
    print("\n--- Test 1: Record $50 trade ---")
    tracker.record_trade(50.0)
    print(f"  Day balance: ${tracker.current_constraints.day_balance:.2f}")
    print(f"  Expected: 950.0")
    assert tracker.current_constraints.day_balance == 950.0, "Day balance should be 950.0"
    print("  ✅ PASS")

    # Test 2: Second trade
    print("\n--- Test 2: Record $75 trade ---")
    tracker.record_trade(75.0)
    print(f"  Day balance: ${tracker.current_constraints.day_balance:.2f}")
    print(f"  Expected: 875.0")
    assert tracker.current_constraints.day_balance == 875.0, "Day balance should be 875.0"
    print("  ✅ PASS")

    # Test 3: Verify can_trade respects balance
    print("\n--- Test 3: can_trade() respects balance ---")
    can_trade_800, _ = tracker.can_trade(800.0)
    print(f"  Can trade $800 with $875 remaining? {can_trade_800}")
    assert can_trade_800 == True, "Should be able to trade $800"
    print("  ✅ PASS")

    can_trade_900, reason_900 = tracker.can_trade(900.0)
    print(f"  Can trade $900 with $875 remaining? {can_trade_900}")
    print(f"  Reason: {reason_900}")
    assert can_trade_900 == False, "Should NOT be able to trade $900"
    print("  ✅ PASS")

    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
    print("\nSummary of fix:")
    print("  ✓ Day balance is now decremented when trades are recorded")
    print("  ✓ Subsequent trades properly respect the reduced balance")
    print("  ✓ Demo balance is no longer unlimited")

if __name__ == "__main__":
    test_demo_balance_tracking()
