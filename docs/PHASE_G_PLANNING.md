# Phase G: Advanced Ensemble Techniques & Adaptive Optimization

**Status**: PLANNING  
**Prerequisites**: Phase F complete (14 models with optimized weights)  
**Estimated Duration**: 4-8 hours total (4 sub-phases)  
**Goal**: Enhance signal quality through ensemble voting, weight smoothing, online learning, and multi-timeframe aggregation

---

## Overview

Phase G extends Phase F's weight optimization with 4 advanced techniques:

| Phase | Focus | Benefit | Complexity |
|-------|-------|---------|-----------|
| **G1** | Ensemble voting across regime-specific models | Consensus-based signal quality | Medium |
| **G2** | Kalman filter for weight smoothing | Reduce weight jitter/noise | Low |
| **G3** | Online learning for weight adaptation | Self-tuning to market changes | High |
| **G4** | Multi-timeframe signal aggregation | Cross-timeframe confirmation | High |

---

## Phase G1: Ensemble Voting Across Regime Models

### Problem Statement
Phase F uses regime-specific weights, but signals can flip rapidly between regimes. Ensemble voting provides consensus validation.

### Solution
Create an **ensemble voting system** where:
1. Each regime (trending/ranging/chaotic) generates its own signal independently
2. Signals vote on the final prediction (BUY/SELL/NEUTRAL)
3. Confidence increases with consensus; decreases with disagreement

### Implementation Details

**New Class: `RegimeEnsembleVoter`**

```python
class RegimeEnsembleVoter:
    """Ensemble voting across regime-specific model configurations."""
    
    def __init__(self, base_aggregator: MultiModelAggregator):
        self.base_aggregator = base_aggregator
        self.regime_votes = {}  # Track voting history
        
    def vote(self, model_outputs: Dict, kalman_regime: Tuple) -> SignalResult:
        """
        Run all 5 regime configurations in parallel:
        1. Trending UP weights
        2. Trending DOWN weights  
        3. Ranging weights
        4. Chaotic weights
        5. Default weights (neutral baseline)
        
        Returns signal based on majority vote + consensus confidence.
        """
        # Generate 5 signals (one per regime config)
        signals = {}
        for regime_key in ["trending_up", "trending_down", "ranging", "chaotic", "default"]:
            signal = self.base_aggregator.aggregate(
                **model_outputs,
                kalman_regime=kalman_regime,
                override_regime_key=regime_key  # Force use of this regime
            )
            signals[regime_key] = signal
        
        # Count votes (BUY=1, SELL=-1, NEUTRAL=0)
        votes = [1 if s.side == "BUY" else -1 if s.side == "SELL" else 0 
                 for s in signals.values()]
        vote_sum = sum(votes)
        
        # Determine final side based on majority
        final_side = "BUY" if vote_sum >= 1 else "SELL" if vote_sum <= -1 else "NEUTRAL"
        
        # Consensus confidence: higher agreement = higher confidence
        consensus_strength = abs(vote_sum) / 5.0  # 0.0 to 1.0
        avg_confidence = np.mean([s.confidence for s in signals.values()])
        
        # Boost confidence if consensus, dampen if disagreement
        final_confidence = avg_confidence * (0.5 + consensus_strength)
        
        return SignalResult(
            side=final_side,
            confidence=final_confidence,
            reason=f"Ensemble vote {vote_sum}/5; consensus {consensus_strength:.0%}",
            method="ensemble_voting",
            components={
                "votes": {k: v.side for k, v in signals.items()},
                "confidences": {k: v.confidence for k, v in signals.items()},
                "consensus": consensus_strength,
            }
        )
```

### Use Cases

**Strong Signal** (5/5 agreement):
- All regimes agree → confidence +25%
- Example: Trending trending_up, ranging, chaotic all say BUY
- Confidence multiplier: 1.5x

**Mixed Signal** (3/5 agreement):
- Majority agrees, some disagree → confidence -5%
- Example: trending_up, trending_down, default say BUY; ranging, chaotic say SELL
- Confidence multiplier: 0.95x

**Unclear Signal** (doesn't meet majority):
- Close vote → emit NEUTRAL
- Example: 2 BUY, 3 SELL → marginal signal
- Emit NEUTRAL (0% confidence) to avoid noise

### Files to Create
- `ml/aggregation/regime_ensemble_voter.py` — voting logic
- `docs/OPTIMIZATION_ensemble_voting_results.md` — voting statistics

### Success Metrics
- ✅ Reduce false signals by filtering weak consensus (< 60% agreement)
- ✅ Increase win rate on high-consensus signals (≥ 80% agreement)
- ✅ Maintain signal generation rate (no excessive neutrals)

---

## Phase G2: Kalman Filter for Weight Smoothing

### Problem Statement
Phase F regime switching can change weights abruptly when regime boundary crosses:
- Market: TRENDING → RANGING (weights flip suddenly)
- Effect: Rapid confidence changes, potential whipsaws

### Solution
Use a **Kalman filter** to smooth weight transitions:
1. Treat regime weights as state variables
2. Predict next weight based on regime trend
3. Observe actual regime classification
4. Smooth predictions: avoid sudden jumps

### Implementation Details

**New Class: `KalmanWeightSmoother`**

```python
class KalmanWeightSmoother:
    """Smooths regime weight transitions using Kalman filtering."""
    
    def __init__(self, process_noise=0.01, measurement_noise=0.05):
        """
        Args:
            process_noise: How much weights naturally drift (lower = smoother)
            measurement_noise: How noisy regime classification is
        """
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        
        # State: [ensemble_weight, advanced_weight, deep_weight]
        self.state = np.array([0.45, 0.25, 0.30])  # Start at Phase F defaults
        self.covariance = np.eye(3) * 0.01  # Small initial uncertainty
        
    def smooth(self, regime_key: str, raw_weights: np.ndarray) -> np.ndarray:
        """
        Apply Kalman filter to smooth regime weight transitions.
        
        Args:
            regime_key: Current regime classification
            raw_weights: Desired weights from regime config
            
        Returns:
            Smoothed weights
        """
        # Predict: weights stay roughly same (slow drift)
        predicted_state = self.state.copy()
        predicted_cov = self.covariance + np.eye(3) * self.process_noise
        
        # Measure: observe actual regime weights
        measured_weights = np.array(raw_weights)
        
        # Kalman gain: how much to trust measurement vs prediction
        kalman_gain = predicted_cov / (predicted_cov + self.measurement_noise)
        
        # Update: blend prediction and measurement
        self.state = predicted_state + kalman_gain * (measured_weights - predicted_state)
        self.covariance = (np.eye(3) - kalman_gain) * predicted_cov
        
        # Renormalize (weights must sum to 1)
        return self.state / self.state.sum()
```

### Use Cases

**Smooth Transition** (regime boundary):
- t=100: TRENDING (weights: 50/20/30)
- t=101: Regime border, now RANGING (desired: 30/40/30)
- t=101 smoothed: 48/25/27 (most weights, some ranging)
- t=102 smoothed: 45/32/23 (more ranging)
- t=103+ smoothed: 30/40/30 (full ranging)
- Result: 3 samples to transition smoothly

**Noisy Regime Classification**:
- Market flickers between RANGING ↔ CHAOTIC rapidly
- Kalman filter ignores noise, keeps weights stable
- Prevents whipsaw signals from regime jitter

### Files to Create
- `ml/optimization/kalman_weight_smoother.py` — smoothing logic
- Update `signal_aggregator.py` to use smoother

### Success Metrics
- ✅ Reduce weight jitter (variance in weights < 0.05)
- ✅ Maintain responsiveness (lag < 1 sample for real regime changes)
- ✅ Fewer whipsaw trades at regime boundaries

---

## Phase G3: Online Learning for Weight Adaptation

### Problem Statement
Phase F weights are static (45/25/30 default + regime overrides). Markets change over time:
- Model effectiveness drifts
- New patterns emerge
- Historic tuning becomes stale

### Solution
Implement **online learning** to adapt weights over time:
1. Track each model's recent win rate
2. Gradually increase weight of winners
3. Gradually decrease weight of losers
4. Stay close to Phase F baseline (avoid overfitting)

### Implementation Details

**New Class: `OnlineLearningOptimizer`**

```python
class OnlineLearningOptimizer:
    """Adapts model weights based on live trading performance."""
    
    def __init__(self, baseline_weights: Dict[str, float], learning_rate=0.005):
        """
        Args:
            baseline_weights: Phase F weights to start from
            learning_rate: How fast to adapt (0-1, low=conservative)
        """
        self.baseline = baseline_weights.copy()
        self.current_weights = baseline_weights.copy()
        self.learning_rate = learning_rate
        
        # Performance tracking
        self.model_wins = {}      # {model_name: win_count}
        self.model_losses = {}    # {model_name: loss_count}
        self.trades_evaluated = 0
    
    def update_performance(self, trade_result: Dict) -> None:
        """
        Called after each trade closes.
        
        Args:
            trade_result: {
                "side": "BUY/SELL",
                "entry_price": 1.2345,
                "exit_price": 1.2346,
                "profit": 0.0001,
                "components": {...}  # From signal
            }
        """
        is_win = trade_result["profit"] > 0
        
        # Credit winning models, blame losing models
        for model_name, component in trade_result.get("components", {}).items():
            if model_name not in self.model_wins:
                self.model_wins[model_name] = 0
                self.model_losses[model_name] = 0
            
            if is_win:
                self.model_wins[model_name] += 1
            else:
                self.model_losses[model_name] += 1
        
        self.trades_evaluated += 1
        
        # Adapt weights every 10 trades
        if self.trades_evaluated % 10 == 0:
            self._adapt_weights()
    
    def _adapt_weights(self) -> None:
        """Adjust weights based on win rates."""
        if self.trades_evaluated < 20:
            return  # Need minimum sample size
        
        # Calculate win rate for each model
        win_rates = {}
        for model_name in self.model_wins:
            wins = self.model_wins[model_name]
            losses = self.model_losses[model_name]
            total = wins + losses
            if total > 0:
                win_rates[model_name] = wins / total
        
        # Adjust weights toward winners, away from losers
        for model_name, current_weight in self.current_weights.items():
            win_rate = win_rates.get(model_name, 0.5)
            
            # Delta: how much to move toward baseline or boost
            if win_rate > 0.55:
                # Winner: increase weight
                target = current_weight * (1 + self.learning_rate)
            elif win_rate < 0.45:
                # Loser: decrease weight
                target = current_weight * (1 - self.learning_rate)
            else:
                # Neutral: keep current
                target = current_weight
            
            # Bound to ±20% of baseline
            min_weight = self.baseline[model_name] * 0.8
            max_weight = self.baseline[model_name] * 1.2
            
            self.current_weights[model_name] = np.clip(target, min_weight, max_weight)
        
        # Renormalize
        total = sum(self.current_weights.values())
        for model_name in self.current_weights:
            self.current_weights[model_name] /= total
```

### Use Cases

**Model Drift Over Time**:
- Phase F: Ensemble weight 45% (works great first week)
- Week 2: Market changes, ensemble effectiveness drops to 42% win rate
- Online learning: Ensemble weight gradually reduces to 43%
- Week 3: Learns ensemble is weak, reduces to 41%
- Week 4: Market changes again, ensemble becomes strong, increases to 46%

**Seasonal Patterns**:
- Market behavior changes every quarter
- Online learning adapts automatically
- No manual retraining needed

### Files to Create
- `ml/optimization/online_learning_optimizer.py` — learning logic
- `ml/serving/online_learning_manager.py` — integration with signal service
- Update `engine.py` to track trade results

### Success Metrics
- ✅ Win rate improves by ≥2% after 200 trades with online learning
- ✅ Weight variance stays within ±20% of baseline (no overfitting)
- ✅ Fast adaptation to market changes (lag < 50 trades)

---

## Phase G4: Multi-Timeframe Signal Aggregation

### Problem Statement
Current system uses only 1-minute candles. Missing patterns on other timeframes:
- 5-minute: Trend confirmation
- 15-minute: Major regime (daily equivalent)
- 1-minute: Entry timing
- Multi-timeframe: Filter false signals, confirm real moves

### Solution
Aggregate signals from **3 timeframes** (1m, 5m, 15m):
1. Generate signals independently on each timeframe
2. Require alignment for high-confidence trades
3. Use longer timeframes to filter noise

### Implementation Details

**New Class: `MultiTimeframeAggregator`**

```python
class MultiTimeframeAggregator:
    """Aggregates signals across 1m, 5m, 15m timeframes."""
    
    def __init__(self, signal_service):
        """
        Args:
            signal_service: MLSignalService instance
        """
        self.signal_service = signal_service
        self.candle_store = signal_service.candle_store
        
        # Signal history per timeframe
        self.signals_1m = []
        self.signals_5m = []
        self.signals_15m = []
    
    def aggregate(self, asset: str, kalman_regime: Tuple) -> SignalResult:
        """
        Generate signals on 1m, 5m, 15m and aggregate.
        
        Args:
            asset: Asset name
            kalman_regime: Current regime (1m-based)
            
        Returns:
            Multi-timeframe signal
        """
        # Get candles for each timeframe
        candles_1m = self.candle_store.get_candles(asset, "1m", 100)
        candles_5m = self.candle_store.aggregate(asset, "1m", "5m", 20)
        candles_15m = self.candle_store.aggregate(asset, "1m", "15m", 15)
        
        # Generate signals
        signal_1m = self.signal_service.generate_signal(asset, candles_1m)
        signal_5m = self._generate_signal_from_candles(asset, candles_5m, "5m")
        signal_15m = self._generate_signal_from_candles(asset, candles_15m, "15m")
        
        # Aggregate by alignment
        return self._combine_timeframes(signal_1m, signal_5m, signal_15m)
    
    def _combine_timeframes(self, s1m: SignalResult, s5m: SignalResult, 
                            s15m: SignalResult) -> SignalResult:
        """Combine signals with alignment scoring."""
        
        # Count agreement (BUY=1, SELL=-1)
        agreement_score = (
            (1 if s1m.side == "BUY" else -1 if s1m.side == "SELL" else 0) +
            (1 if s5m.side == "BUY" else -1 if s5m.side == "SELL" else 0) +
            (1 if s15m.side == "BUY" else -1 if s15m.side == "SELL" else 0)
        ) / 3.0  # -1 to +1
        
        # Determine final signal
        final_side = "BUY" if agreement_score >= 0.33 else \
                     "SELL" if agreement_score <= -0.33 else \
                     "NEUTRAL"
        
        # Confidence: 1m base + alignment bonus
        avg_confidence = (s1m.confidence + s5m.confidence + s15m.confidence) / 3
        alignment_bonus = abs(agreement_score) * 0.3  # Up to +30% for full alignment
        final_confidence = avg_confidence * (1 + alignment_bonus)
        
        return SignalResult(
            side=final_side,
            confidence=final_confidence,
            reason=f"Multi-timeframe: 1m={s1m.side}, 5m={s5m.side}, 15m={s15m.side}",
            method="multi_timeframe",
            components={
                "1m": {"side": s1m.side, "confidence": s1m.confidence},
                "5m": {"side": s5m.side, "confidence": s5m.confidence},
                "15m": {"side": s15m.side, "confidence": s15m.confidence},
                "alignment": agreement_score,
            }
        )
```

### Use Cases

**True Trend** (aligned across timeframes):
- 1m: BUY (0.65 confidence)
- 5m: BUY (0.72 confidence)
- 15m: BUY (0.68 confidence)
- Result: BUY with 0.75 confidence (68% base + 22% alignment bonus)

**Noise vs Trend**:
- 1m: BUY (0.52 confidence) ← noisy signal
- 5m: SELL (0.60 confidence) ← disagree
- 15m: SELL (0.65 confidence) ← disagree
- Result: SELL with 0.62 confidence (58% base + reweight)

**Entry Timing**:
- 15m: Uptrend (SELL signals are noise)
- 5m: Pullback starting
- 1m: Pin bar at support
- Result: BUY (1m entry timing + 5m pullback + 15m trend = high confidence)

### Files to Create
- `ml/aggregation/multi_timeframe_aggregator.py` — MTF logic
- `ml/data/timeframe_aggregator.py` (enhance existing) — OHLC aggregation
- Update `candle_store.py` to support caching aggregated candles

### Success Metrics
- ✅ Reduce false signals by 15-20% (filter noise)
- ✅ Maintain signal generation (min 1 signal per 50 candles)
- ✅ Win rate on aligned signals ≥ 10% higher than misaligned
- ✅ No additional training time (aggregate candles, reuse models)

---

## Implementation Order & Prioritization

### Recommended Sequence

**Phase G1** (FIRST - Low risk, high ROI):
- Complexity: Medium
- Risk: Low (voting doesn't change weights)
- ROI: Reduces false signals by 10-15%
- Time: 1-2 hours

**Phase G4** (SECOND - Natural fit after G1):
- Complexity: High
- Risk: Medium (requires candle aggregation)
- ROI: Reduces false signals by 15-20%
- Time: 2-3 hours

**Phase G2** (THIRD - Refinement):
- Complexity: Low
- Risk: Low (smoother only affects weight transitions)
- ROI: Reduces whipsaws at regime boundaries
- Time: 1 hour

**Phase G3** (FOURTH - Advanced):
- Complexity: High
- Risk: High (adapts weights, requires careful tuning)
- ROI: Long-term adaptation (weeks to show benefit)
- Time: 2-3 hours

### Parallel Implementation Possible

G1 and G2 can be done in parallel (independent)  
G3 can start after G1 (voting provides trade labels)  
G4 can start after G2 (multi-timeframe needs stable weights)

---

## Success Criteria

### Phase G1: Ensemble Voting
- ✅ Voting logic implemented and tested
- ✅ Consensus scoring reduces false signals by ≥10%
- ✅ Strong signals (4-5/5 votes) have ≥10% better win rate

### Phase G2: Weight Smoothing
- ✅ Kalman filter smooths regime transitions
- ✅ Weight variance < 0.05 (stable)
- ✅ No regression in signal quality

### Phase G3: Online Learning
- ✅ Win rate improves after 200 trades
- ✅ Weights stay within ±20% of baseline
- ✅ Adapts to seasonal changes (observed over 2+ weeks)

### Phase G4: Multi-Timeframe
- ✅ Signals generated on 1m, 5m, 15m
- ✅ Aggregation reduces false signals by ≥15%
- ✅ Aligned signals have better outcomes than misaligned

---

## Architecture Diagram

```
Phase G Ensemble
==================

Model Predictions (14 models from Phase A-E)
    ↓
[Phase F Signal Aggregator]
    ↓
    ├─ [G1 Ensemble Voter] ← Parallel voting
    │   └─ 5 regime signals → Consensus
    │
    ├─ [G2 Kalman Smoother] ← Weight smoothing
    │   └─ Smooth transitions
    │
    ├─ [G3 Online Learner] ← Performance tracking
    │   └─ Adapt weights over time
    │
    └─ [G4 Multi-Timeframe] ← Candle aggregation
        ├─ 1m candles → Signal
        ├─ 5m candles → Signal
        ├─ 15m candles → Signal
        └─ Aggregate → Final signal
    
    ↓
[Final Signal] → UI / Trading Engine
```

---

## Resource Requirements

| Phase | CPU | Memory | Disk | Latency |
|-------|-----|--------|------|---------|
| G1 | +20% (5 signals) | +50MB | +0 | +50ms |
| G2 | +0% (matrix ops) | +5MB | +0 | +0ms |
| G3 | +5% (tracking) | +10MB | +5MB (logs) | +0ms |
| G4 | +30% (candles) | +100MB | +50MB (cache) | +100ms |
| **Total** | **+55%** | **+165MB** | **+55MB** | **+150ms** |

Current: ~200ms latency → ~350ms with Phase G (still acceptable)

---

## Session Checklist for Phase G

- [ ] Phase F complete and live (14 models active)
- [ ] Read PHASE_F_IMPLEMENTATION.md for context
- [ ] Review signal_aggregator.py Phase F weights
- [ ] Decide: G1 first or G4 first?
- [ ] Create G1 implementation (ensemble voter)
- [ ] Test G1 on backtest data
- [ ] Create G4 implementation (multi-timeframe)
- [ ] Test G4 on backtest data
- [ ] Create G2 implementation (Kalman smoother)
- [ ] Create G3 implementation (online learning)
- [ ] Integrate all 4 into signal pipeline
- [ ] Documentation and commit

---

## Notes

- All Phase G features are **optional** (Phase F fully functional alone)
- Phase G1 + G4 give best ROI for effort
- Phase G3 requires live trading data (backtest can't validate)
- Phase G is optimization-focused, not feature-adding
- Keep git history clean (one commit per G-phase)

Good luck! 🚀
