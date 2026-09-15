# Signal Confidence Model

## Overview

Signal confidence is now calculated using a **multi-layer confirmation system** rather than just the raw weighted score. This produces more reliable confidence levels that better reflect signal quality.

---

## Four Confidence Layers

### Layer 1: Oscillator Agreement (0.0 - 1.0)
**How many indicators agree with the signal direction?**

```
Count indicators that align with signal:
  ✓ MACD (histogram direction matches signal)
  ✓ Awesome Oscillator (direction matches signal)
  ✓ EMA Trend (price/MA alignment matches signal)
  ✓ ADX Direction (+DI/-DI matches signal)
  ✓ RSI (overbought/oversold tendency matches signal)

agreement_factor = agree_count / 5
```

**Example:**
- 5/5 agreement = 1.0 factor (multiply confidence by 1.0)
- 3/5 agreement = 0.6 factor (multiply confidence by 0.6)
- 1/5 agreement = 0.2 factor (multiply confidence by 0.2)

**Impact:** If only 1-2 oscillators agree, confidence drops significantly. This prevents false signals from isolated indicators.

---

### Layer 2: Trend Strength Multiplier (0.6 - 1.2)
**How strong is the current trend? (ADX-based)**

```
ADX > 25 → 1.2x multiplier (strong trend = higher confidence)
ADX 20-25 → 1.0x multiplier (moderate trend = normal confidence)
ADX 15-20 → 0.8x multiplier (weak trend = lower confidence)
ADX < 15 → 0.6x multiplier (very weak trend = much lower confidence)
```

**Why:** Strong trends are more reliable than weak ones. Your screenshot showed **ADX=20** (weak trend), so confidence gets 0.8x reduction.

**Example:**
- Strong uptrend (ADX=30) + BUY signal = 1.2x boost
- Choppy market (ADX=12) + BUY signal = 0.6x penalty

---

### Layer 3: RSI Extreme Confirmation (1.0 - 1.1)
**Is RSI confirming overbought/oversold extremes?**

```
BUY signal + RSI > 65 (overbought) → 1.1x multiplier ✓
SELL signal + RSI < 35 (oversold) → 1.1x multiplier ✓
Otherwise → 1.0x multiplier (neutral)
```

**Why:** RSI extremes increase signal reliability.

---

### Layer 4: Momentum Acceleration (1.0 - 1.15)
**Is the momentum accelerating or decelerating?**

```
MACD histogram increasing in absolute value → 1.15x (accelerating)
MACD histogram decreasing in absolute value → 1.0x (decelerating)
First candle with signal → 1.0x (no prior data)
```

**Why:** Accelerating signals are stronger than weakening ones.

---

## Final Confidence Calculation

```
Confidence = min(
    base_score 
    × agreement_factor 
    × trend_strength_factor 
    × rsi_extreme_factor 
    × momentum_factor,
    1.0  # Max 100%
)
```

### Example: Your Screenshot

**Given:**
- Base score: 0.40 (Strong SELL threshold)
- Agreement: 5/5 oscillators aligned = 1.0 factor
- ADX: 20 (weak trend) = 0.8 factor
- RSI: Not extreme = 1.0 factor
- Momentum: Stable = 1.0 factor

**Calculation:**
```
Confidence = 0.40 × 1.0 × 0.8 × 1.0 × 1.0 = 0.32 = 32%
```

But this is BEFORE the oscillator agreement applies! Your actual result was 19% because only some oscillators aligned.

---

## Confidence Interpretation

| Confidence | Interpretation | Action |
|-----------|----------------|--------|
| **80-100%** | Excellent signal | Strong buy/sell, may trade full size |
| **60-79%** | Good signal | Reliable buy/sell, normal size |
| **40-59%** | Fair signal | Moderate buy/sell, smaller size |
| **20-39%** | Weak signal | Low reliability, wait for confirmation |
| **0-19%** | Very weak | Ignore, conflicting signals |

---

## How to Increase Confidence

### 1. Wait for More Oscillator Agreement
- Your current: 19% with mixed signals
- **Solution:** Wait for MACD + AO + Trend to all align
- Example: 5/5 agreement → 100% → 80% factor increase

### 2. Trade Only in Strong Trends
- Only enter signals when ADX > 25
- Weak trends (ADX < 20) get 0.6x penalty
- Strong trends (ADX > 25) get 1.2x boost

### 3. Use RSI Extremes
- BUY only when RSI overbought (> 65)
- SELL only when RSI oversold (< 35)
- Adds 1.1x multiplier to confidence

### 4. Catch Accelerating Momentum
- Best signals come with accelerating MACD histogram
- Strengthens signal by 1.15x

---

## Real Examples

### High Confidence Signal (80%+)
```
ADX: 28 (strong trend, 1.2x)
MACD: +0.35 histogram, increasing (accelerating, 1.15x)
Awesome: +0.42 (bullish momentum)
RSI: 72 (overbought, 1.1x)
EMA: Price above both EMA12 and EMA26 ✓
Agreement: 5/5 indicators aligned ✓

Confidence = 0.60 × 1.0 × 1.2 × 1.1 × 1.15 = 87% ✓✓✓
→ STRONG BUY - High reliability
```

### Medium Confidence Signal (40-60%)
```
ADX: 18 (weak trend, 0.8x)
MACD: -0.08 histogram
Awesome: -0.15 (slight bearish)
RSI: 45 (neutral)
Trend: Mixed
Agreement: 3/5 indicators aligned

Confidence = 0.35 × 0.6 × 0.8 × 1.0 × 1.0 = 17% 
→ WEAK SELL - Low reliability, wait for confirmation
```

### Your Current Signal (19%)
```
ADX: 20 (borderline weak, 0.8x)
MACD: Negative histogram
Awesome: Negative oscillator
RSI: 43% (neutral)
Agreement: Partial alignment

Confidence = 0.25 × 0.5 × 0.8 × 1.0 × 1.0 = 10-20%
→ WEAK SELL - Mixed signals, needs confirmation
```

---

## Customizing Confidence Weights

Edit `ml_signals.py` to adjust multiplier thresholds:

```python
# Make it easier to get high confidence:
if adx > 20:  # Lower from 25
    trend_strength_factor = 1.2

# Or require more agreement:
agreement_factor = (agree_count - 1) / 4  # Require at least 2/5
```

---

## Signal Reason Format

Now includes agreement count:
```
"Strong SELL | ADX=20 (-DI), MACD DOWN, AO DOWN | Agree:5/5"
         ↑                                            ↑
     Signal strength                          Oscillator alignment
```

**Agree:5/5** = All oscillators aligned (highest confidence factor)
**Agree:3/5** = Most oscillators aligned (medium factor)
**Agree:1/5** = Isolated signal (low factor, risky)

---

## Best Practices

✓ **Wait for ADX > 25** before trading signals
✓ **Look for 4-5/5 agreement** minimum
✓ **Catch RSI extremes** for +10% confidence boost
✓ **Use accelerating momentum** (1.15x boost)
✓ **Avoid weak trend trades** (reject ADX < 15)

❌ **Don't trade** confidence < 40% without confirmation
❌ **Don't ignore** ADX strength (it's 30% of the score)
❌ **Don't trade alone** on one oscillator

---

## Testing Your Signal

To test with your real data:
```bash
python test_oscillators.py
```

The output now shows:
- Confidence percentage
- Agreement count (X/5)
- Individual factor contributions
- Detailed reason

---

*Implementation: 2026-09-15*
*Model: Multi-layer confidence with 4 confirmation layers*
*Version: 2.0 (upgraded from single-score model)*
