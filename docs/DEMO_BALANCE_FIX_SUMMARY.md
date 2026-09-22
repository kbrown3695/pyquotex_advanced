# Demo Balance Bug Fix

## Issue

Automated trades were not properly constrained by the demo account balance in PRACTICE mode. This allowed unlimited trades to be executed against the demo balance.

## Root Cause

In `ml/trading/account_constraint_tracker.py`, the `record_trade()` method was not updating the `day_balance` when recording executed trades:

```python
# OLD CODE - Missing day_balance decrement
def record_trade(self, amount: float) -> None:
    self.trades_today += 1
    self.total_traded_today += amount
    # day_balance was NEVER decremented!
```

### Why This Matters for Demo Mode

1. **PRACTICE mode limitation**: Quotex doesn't send updated `dayBalance` values in PRACTICE mode (see lines 114-121 in account_constraint_tracker.py)
2. **Workaround in place**: The code auto-fills `dayBalance = demoBalance` when in PRACTICE mode
3. **The bug**: Since `day_balance` was never decremented after trades, the available balance remained at the full demo_balance amount
4. **Result**: Unlimited trades were possible against the demo balance

## Solution

Updated `record_trade()` method to decrement `day_balance`:

```python
# FIXED CODE
def record_trade(self, amount: float) -> None:
    self.trades_today += 1
    self.total_traded_today += amount

    if self.current_constraints:
        self.current_constraints.day_balance -= amount  # ← FIX: Decrement available balance
        remaining = self.current_constraints.day_balance

        self.logger.info(
            f"Trade recorded: ${amount:.2f} (Total today: ${self.total_traded_today:.2f}, "
            f"Remaining: ${remaining:.2f})"
        )
```

## Impact

### Before Fix
- Trade 1: $50 - day_balance remains $1000
- Trade 2: $75 - day_balance remains $1000  
- Trade 3: $100 - day_balance remains $1000
- **Result**: Unlimited trades possible

### After Fix
- Trade 1: $50 - day_balance becomes $950
- Trade 2: $75 - day_balance becomes $875
- Trade 3: $100 - day_balance becomes $775
- **Result**: Trades properly constrained to available demo balance

## Testing

Run the test to verify the fix:

```bash
python test_demo_balance_simple.py
```

All tests pass, confirming:
1. ✅ Day balance is decremented after each trade
2. ✅ `can_trade()` properly rejects trades exceeding remaining balance
3. ✅ Demo balance is now properly constrained

## Files Changed

- `ml/trading/account_constraint_tracker.py` - Fixed `record_trade()` method

## Files Added for Testing

- `test_demo_balance_simple.py` - Isolated test to verify the fix
- `test_demo_balance_fix.py` - Full integration test (requires full module imports)
- `DEMO_BALANCE_FIX_SUMMARY.md` - This documentation
