# Phase 1.5: Signal Aggregator Integration Guide

**Status:** Ready to Start  
**Estimated Time:** 1-2 hours  
**Prerequisite:** Phase 1 ✅ COMPLETE

---

## Goal

Wire binary options features into the existing signal aggregator so that:
1. Every signal includes timing information (time-to-reversal, safe expirations)
2. Confidence is adjusted based on expiration time chosen
3. Frontend displays which expirations are safe to trade
4. Money manager can use safe flags to reject unsafe trades

---

## What Exists

### Current Signal Output (from `ml/aggregation/signal_aggregator.py`)
```python
{
    "side": "BUY",
    "confidence": 0.72,
    "reason": "Strong momentum",
    "method": "ensemble",
    "components": {...},
    "timestamp": 1234567890
}
```

### New Features Available (from `ml/features/binary_options_features.py`)
```python
{
    "momentum_velocity": 0.045,
    "time_to_reversal_seconds": 300,
    "reversal_probability": 0.38,
    "safe_for_1m": False,
    "safe_for_2m": True,
    "safe_for_5m": True,
    "safe_for_15m": True,
    ...
}
```

---

## Integration Steps

### Step 1: Modify `SignalResult` class

**File:** `ml/aggregation/signal_aggregator.py`

**Current Code (around line 11-41):**
```python
class SignalResult:
    def __init__(self, ...):
        self.side = side
        self.confidence = confidence
        self.reason = reason
        ...
```

**Add:**
```python
class SignalResult:
    def __init__(
        self,
        side: str,
        confidence: float,
        reason: str,
        method: str = "ensemble",
        components: Optional[Dict[str, Any]] = None,
        timestamp: Optional[float] = None,
        # NEW FIELDS:
        binary_options_features: Optional[Dict[str, Any]] = None,
        confidence_by_expiration: Optional[Dict[str, float]] = None,
        safe_expirations: Optional[List[str]] = None,
    ):
        self.side = side
        self.confidence = confidence
        self.reason = reason
        self.method = method
        self.components = components or {}
        self.timestamp = timestamp
        
        # NEW:
        self.binary_options_features = binary_options_features or {}
        self.confidence_by_expiration = confidence_by_expiration or {}
        self.safe_expirations = safe_expirations or []
```

### Step 2: Update `to_dict()` method

**Current:**
```python
def to_dict(self) -> Dict[str, Any]:
    return {
        "side": self.side,
        "confidence": round(self.confidence, 3),
        "reason": self.reason,
        ...
    }
```

**Update to:**
```python
def to_dict(self) -> Dict[str, Any]:
    result = {
        "side": self.side,
        "confidence": round(self.confidence, 3),
        "reason": self.reason,
        "method": self.method,
        "components": self.components,
        "timestamp": self.timestamp or time.time(),
    }
    
    # NEW: Add binary options data if available
    if self.binary_options_features:
        result["binary_options"] = {
            "time_to_reversal_seconds": self.binary_options_features.get("time_to_reversal_seconds", 0),
            "reversal_probability": round(self.binary_options_features.get("reversal_probability", 0), 3),
            "momentum_velocity": round(self.binary_options_features.get("momentum_velocity", 0), 6),
            "volatility_percentile": round(self.binary_options_features.get("volatility_percentile", 0), 1),
            "support_level": self.binary_options_features.get("support_level", 0),
            "resistance_level": self.binary_options_features.get("resistance_level", 0),
        }
    
    if self.confidence_by_expiration:
        result["confidence_by_expiration"] = {
            k: round(v, 3) for k, v in self.confidence_by_expiration.items()
        }
    
    if self.safe_expirations:
        result["safe_expirations"] = self.safe_expirations
    
    return result
```

### Step 3: Add Binary Options Enhancement Method

**In `MultiModelAggregator` class:**

```python
from ml.features.binary_options_features import BinaryOptionsFeatureEngineer

class MultiModelAggregator:
    def __init__(self, ...):
        # existing code...
        self.bo_engineer = BinaryOptionsFeatureEngineer()
    
    def enrich_signal_with_binary_options(
        self, 
        signal: SignalResult, 
        candles: List[Dict]
    ) -> SignalResult:
        """Enrich signal with binary options timing features.
        
        Args:
            signal: Base signal from ensemble models
            candles: Recent candle history
        
        Returns:
            Signal with binary options features added
        """
        try:
            # Extract binary options features
            bo_features = self.bo_engineer.extract(candles)
            
            # Calculate expiration-optimized confidence
            confidence_by_expiration = {
                "1m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 60),
                "2m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 120),
                "5m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 300),
                "15m": self._adjust_confidence_for_expiration(signal.confidence, bo_features, 900),
            }
            
            # Determine safe expirations
            safe_expirations = [
                "1m" if bo_features.safe_for_1m else None,
                "2m" if bo_features.safe_for_2m else None,
                "5m" if bo_features.safe_for_5m else None,
                "15m" if bo_features.safe_for_15m else None,
            ]
            safe_expirations = [e for e in safe_expirations if e]
            
            # Create new signal result with BO features
            enriched_signal = SignalResult(
                side=signal.side,
                confidence=signal.confidence,
                reason=signal.reason,
                method=signal.method,
                components=signal.components,
                timestamp=signal.timestamp,
                binary_options_features={
                    "time_to_reversal_seconds": bo_features.time_to_reversal_seconds,
                    "reversal_probability": bo_features.reversal_probability,
                    "momentum_velocity": bo_features.momentum_velocity,
                    "volatility_percentile": bo_features.volatility_percentile,
                    "support_level": bo_features.support_level,
                    "resistance_level": bo_features.resistance_level,
                },
                confidence_by_expiration=confidence_by_expiration,
                safe_expirations=safe_expirations,
            )
            
            return enriched_signal
            
        except Exception as e:
            # If BO feature extraction fails, return original signal
            import logging
            logging.warning(f"Binary options enrichment failed: {e}")
            return signal
    
    def _adjust_confidence_for_expiration(
        self, 
        base_confidence: float, 
        bo_features, 
        expiration_seconds: int
    ) -> float:
        """Adjust confidence based on reversal risk for expiration time.
        
        Args:
            base_confidence: Model confidence (0-1)
            bo_features: Binary options features
            expiration_seconds: Expiration time in seconds (60, 120, 300, 900)
        
        Returns:
            Adjusted confidence for this expiration time
        """
        # If reversal likely before expiration, reduce confidence
        time_to_reversal = bo_features.time_to_reversal_seconds
        reversal_prob = bo_features.reversal_probability
        
        if time_to_reversal < expiration_seconds:
            # Reversal risk within expiration window
            # Reduce confidence by reversal probability
            adjusted = base_confidence * (1.0 - reversal_prob * 0.5)
        else:
            # Reversal unlikely before expiration
            # Keep confidence, maybe slightly boost
            adjusted = base_confidence * (1.0 + bo_features.time_of_day_weight * 0.1)
        
        return max(0.3, min(0.95, adjusted))  # Clamp to reasonable range
```

### Step 4: Wire Into Signal Generation Pipeline

**Find:** `ml/aggregation/signal_aggregator.py` - `aggregate()` method

**Current (approx line 100+):**
```python
def aggregate(self, ...):
    # Calculate ensemble signal
    ensemble_signal = ...
    
    return ensemble_signal  # Returns SignalResult
```

**Update to:**
```python
def aggregate(self, components: Dict, candles: List[Dict], ...):
    # Calculate ensemble signal (existing code)
    ensemble_signal = ...
    
    # NEW: Enrich with binary options features
    enriched_signal = self.enrich_signal_with_binary_options(
        ensemble_signal, 
        candles
    )
    
    return enriched_signal
```

### Step 5: Update Call Sites

**Find all places that call `aggregator.aggregate()`**

Usually in: `ml_signals.py` or similar

**Before:**
```python
signal = aggregator.aggregate(components)
```

**After:**
```python
signal = aggregator.aggregate(components, candles=recent_candles)
```

---

## Testing Phase 1.5 Integration

### Unit Test

```python
# test_signal_aggregator_bo.py
def test_signal_enrichment_with_bo_features():
    aggregator = MultiModelAggregator()
    
    # Create sample uptrend candles
    candles = create_uptrend_candles(100)
    
    # Create base signal
    base_signal = SignalResult(
        side="BUY",
        confidence=0.72,
        reason="Momentum test"
    )
    
    # Enrich with BO features
    enriched = aggregator.enrich_signal_with_binary_options(
        base_signal, 
        candles
    )
    
    # Verify enrichment
    assert enriched.binary_options_features is not None
    assert "time_to_reversal_seconds" in enriched.binary_options_features
    assert len(enriched.safe_expirations) > 0
    assert all(isinstance(c, float) for c in enriched.confidence_by_expiration.values())
    
    print(enriched.to_dict())
    # Should show:
    # {
    #     "side": "BUY",
    #     "confidence": 0.72,
    #     "confidence_by_expiration": {"1m": 0.68, "2m": 0.70, "5m": 0.72, "15m": 0.71},
    #     "safe_expirations": ["2m", "5m", "15m"],
    #     "binary_options": {
    #         "time_to_reversal_seconds": 320,
    #         "reversal_probability": 0.25,
    #         ...
    #     }
    # }
```

### Manual Testing

1. Start the app: `python main.py`
2. Open developer console: F12
3. Check signal output in Network tab
4. Verify BO features appear in signal JSON
5. Verify confidence varies by expiration
6. Verify safe_expirations matches expectations

---

## Expected Output

### Frontend Display

```
EUR/USD at 1.2050

BUY Signal (72% confidence)

⏱ Reversal in: 5-6 minutes
📊 Momentum: 0.045 pips/sec (accelerating)
📈 Volatility: 62nd percentile (high)
🎯 Support: 1.1950 | Resistance: 1.2050

Safe Expirations:
  ❌ 1m (68% confidence) - Reversal risk
  ✅ 2m (70% confidence) - Good
  ✅ 5m (72% confidence) - Best
  ✅ 15m (71% confidence) - Good

Recommended: 5m expiration
```

---

## Rollback Plan

If integration breaks:
1. Comment out `enrich_signal_with_binary_options()` call
2. Signals will return to old format (still valid)
3. Binary options features remain available for Phase 2

---

## Success Criteria

- [ ] Signal includes `binary_options` field with timing data
- [ ] `confidence_by_expiration` varies based on reversal time
- [ ] `safe_expirations` lists only low-risk expirations
- [ ] Unit test passes
- [ ] Manual testing shows correct values
- [ ] No performance regression (<1ms overhead)
- [ ] Handles edge cases (stable prices, reverse data, etc)

---

## Time Estimate

- Copy/modify signal classes: 20-30 min
- Implement enrichment method: 30-45 min
- Wire into pipeline: 15-20 min
- Testing & debug: 30-45 min
- **Total: 1.5-2 hours**

---

## Next After Phase 1.5

Once integration complete:
- **Phase 2:** Money management system (2-3 hours)
- **Phase 3:** Backtesting framework (2-3 hours)

---

**Ready to code:** When you run `get_signal()`, it will include:
```json
{
    "side": "BUY",
    "confidence": 0.72,
    "confidence_by_expiration": {
        "1m": 0.68,
        "2m": 0.70,
        "5m": 0.72,
        "15m": 0.71
    },
    "safe_expirations": ["2m", "5m", "15m"],
    "binary_options": {
        "time_to_reversal_seconds": 320,
        "reversal_probability": 0.25
    }
}
```
