# Phase F Baseline Analysis

**Phase E Weight Architecture (Baseline)**

## Current Weights
- Layer 1 (Ensemble): 42.0%
- Layer 2 (Advanced): 28.0%
- Layer 3 (Deep Learning): 30.0%

## Advanced Model Weights (Normalized)
- Kalman: 33.0%
- ExpectedReturn: 25.0%
- Probability: 25.0%
- RLAgent: 17.0%

## Deep Learning Weights (Normalized)
- LSTM: 50.0%
- Transformer: 50.0%

## Confidence Configuration
- Base Formula: abs(p_up - 0.5) * 2.0
- Regime Dampening Enabled: True
- Trending Boost: 20.0%
- Ranging Dampen: 30.0%
- Chaotic Dampen: 30.0%

## Volatility Dampening
- Enabled: True
- Vol Threshold: 0.01

## Models Included (14 Total)
- Phase A (4): DirectionalClassifier, KalmanStateSpaceModel, ExpectedReturnModel, ProbabilityModel
- Phase B (5): GradBoost-Dir, GradBoost-Return, VolatilityModel, QuantileModel×2
- Phase C (2): RegimeClassifier, HMMRegimeModel
- Phase D (1): RLAgent
- Phase E (2): LSTMModel, TransformerModel

---
