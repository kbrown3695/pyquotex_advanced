#!/usr/bin/env python3
"""
Test for the demo balance fix.
Verifies that day_balance is properly decremented when trades are recorded.
"""

import logging
from ml.trading.account_constraint_tracker import AccountConstraintTracker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_demo_balance_tracking():
    """Test that day_balance decrements properly when trades are recorded."""

    # Initialize tracker
    tracker = AccountConstraintTracker(logger=logger)

    # Simulate initial WebSocket update (DEMO mode)
    account_balance = {
        'liveBalance': 0.0,
        'demoBalance': 1000.0,
        'dayLimit': 0.0,
        'dayBalance': 0.0  # This should be auto-filled from demoBalance
    }

    constraints = tracker.update_from_websocket(
        account_balance=account_balance,
        profile_data={'minimum_amount': 10.0},
        account_is_demo=1
    )

    print("\n" + "="*80)
    print("INITIAL STATE (DEMO MODE)")
    print("="*80)
    print(f"Account Mode: {constraints.account_mode}")
    print(f"Demo Balance: ${constraints.demo_balance:.2f}")
    print(f"Day Balance: ${constraints.day_balance:.2f}")
    print(f"Minimum Amount: ${constraints.minimum_amount:.2f}")

    # Verify initial state
    assert constraints.account_mode == "DEMO"
    assert constraints.demo_balance == 1000.0
    assert constraints.day_balance == 1000.0, f"Expected day_balance=1000.0, got {constraints.day_balance}"

    # Test 1: Record first trade
    print("\n" + "="*80)
    print("TEST 1: Record First Trade ($50)")
    print("="*80)

    tracker.record_trade(50.0)

    print(f"Total traded today: ${tracker.total_traded_today:.2f}")
    print(f"Day balance after trade: ${tracker.current_constraints.day_balance:.2f}")
    print(f"Can trade $100? {tracker.can_trade(100.0)}")

    assert tracker.total_traded_today == 50.0
    assert tracker.current_constraints.day_balance == 950.0, \
        f"Expected day_balance=950.0, got {tracker.current_constraints.day_balance}"

    # Test 2: Record second trade
    print("\n" + "="*80)
    print("TEST 2: Record Second Trade ($75)")
    print("="*80)

    tracker.record_trade(75.0)

    print(f"Total traded today: ${tracker.total_traded_today:.2f}")
    print(f"Day balance after trade: ${tracker.current_constraints.day_balance:.2f}")
    print(f"Can trade $100? {tracker.can_trade(100.0)}")

    assert tracker.total_traded_today == 125.0
    assert tracker.current_constraints.day_balance == 875.0, \
        f"Expected day_balance=875.0, got {tracker.current_constraints.day_balance}"

    # Test 3: Verify can_trade respects reduced balance
    print("\n" + "="*80)
    print("TEST 3: Verify can_trade() Respects Reduced Balance")
    print("="*80)

    can_trade_800, reason_800 = tracker.can_trade(800.0)
    print(f"Can trade $800? {can_trade_800} ({reason_800})")
    assert not can_trade_800, "Should not be able to trade $800 when only $875 remains"

    can_trade_875, reason_875 = tracker.can_trade(875.0)
    print(f"Can trade $875? {can_trade_875} ({reason_875})")
    assert can_trade_875, "Should be able to trade $875"

    can_trade_900, reason_900 = tracker.can_trade(900.0)
    print(f"Can trade $900? {can_trade_900} ({reason_900})")
    assert not can_trade_900, "Should not be able to trade $900 when only $875 remains"

    # Test 4: Record more trades until limit
    print("\n" + "="*80)
    print("TEST 4: Trade Until Balance Nearly Depleted")
    print("="*80)

    tracker.record_trade(870.0)

    print(f"Total traded today: ${tracker.total_traded_today:.2f}")
    print(f"Day balance after trade: ${tracker.current_constraints.day_balance:.2f}")
    print(f"Can trade $20? {tracker.can_trade(20.0)}")

    assert tracker.total_traded_today == 995.0
    assert tracker.current_constraints.day_balance == 5.0, \
        f"Expected day_balance=5.0, got {tracker.current_constraints.day_balance}"

    can_trade_20, _ = tracker.can_trade(20.0)
    assert not can_trade_20, "Should not be able to trade $20 when only $5 remains"

    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
    print("\nSummary:")
    print(f"  - Day balance properly decremented after each trade")
    print(f"  - can_trade() respects the reduced balance")
    print(f"  - Automated trades now properly constrained by demo balance")

if __name__ == "__main__":
    test_demo_balance_tracking()
