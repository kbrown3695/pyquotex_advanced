# Phase F Weight Optimization Scenarios

## Equal weights (1/14 each)
**All 14 models equally weighted for comparison**

### Layer Weights
- ensemble: 7.1%
- advanced: 28.6%
- deep_learning: 14.3%

### Advanced Model Weights
- kalman: 25.0%
- expected_return: 25.0%
- probability: 25.0%
- rl_agent: 25.0%

### Deep Learning Weights
- lstm: 50.0%
- transformer: 50.0%

---
## Boost top 3 performers
**Increase weight on best-performing models (+10% each)**

### Layer Weights
- ensemble: 50.0%
- advanced: 28.0%
- deep_learning: 22.0%

### Advanced Model Weights
- kalman: 40.0%
- expected_return: 20.0%
- probability: 20.0%
- rl_agent: 20.0%

### Deep Learning Weights
- lstm: 70.0%
- transformer: 30.0%

---
## Reduce weak performers
**Decrease weight on underperforming models (-5% each)**

### Layer Weights
- ensemble: 35.0%
- advanced: 40.0%
- deep_learning: 25.0%

### Advanced Model Weights
- kalman: 20.0%
- expected_return: 30.0%
- probability: 20.0%
- rl_agent: 30.0%

### Deep Learning Weights
- lstm: 40.0%
- transformer: 60.0%

---
## Separate layer weights (50/20/30)
**Increase ensemble, reduce advanced, stable deep**

### Layer Weights
- ensemble: 50.0%
- advanced: 20.0%
- deep_learning: 30.0%

### Advanced Model Weights
- kalman: 33.0%
- expected_return: 25.0%
- probability: 25.0%
- rl_agent: 17.0%

### Deep Learning Weights
- lstm: 50.0%
- transformer: 50.0%

---
## Trending market bias
**Boost momentum models (ensemble, RLAgent, LSTM)**

### Layer Weights
- ensemble: 50.0%
- advanced: 20.0%
- deep_learning: 30.0%

### Advanced Model Weights
- kalman: 15.0%
- expected_return: 15.0%
- probability: 10.0%
- rl_agent: 60.0%

### Deep Learning Weights
- lstm: 65.0%
- transformer: 35.0%

---
## Ranging market bias
**Boost mean-reversion models (Kalman, Probability, Transformer)**

### Layer Weights
- ensemble: 30.0%
- advanced: 40.0%
- deep_learning: 30.0%

### Advanced Model Weights
- kalman: 45.0%
- expected_return: 15.0%
- probability: 30.0%
- rl_agent: 10.0%

### Deep Learning Weights
- lstm: 40.0%
- transformer: 60.0%

---
## Chaotic market (conservative)
**Mute aggressive models, boost ensemble robustness**

### Layer Weights
- ensemble: 60.0%
- advanced: 20.0%
- deep_learning: 20.0%

### Advanced Model Weights
- kalman: 35.0%
- expected_return: 20.0%
- probability: 35.0%
- rl_agent: 10.0%

### Deep Learning Weights
- lstm: 60.0%
- transformer: 40.0%

---
## Deep learning emphasis
**Increase deep learning models (LSTM + Transformer)**

### Layer Weights
- ensemble: 30.0%
- advanced: 20.0%
- deep_learning: 50.0%

### Advanced Model Weights
- kalman: 25.0%
- expected_return: 25.0%
- probability: 25.0%
- rl_agent: 25.0%

### Deep Learning Weights
- lstm: 50.0%
- transformer: 50.0%

---
## Balanced 45/25/30 split
**Refined balance: ensemble 45%, advanced 25%, deep 30%**

### Layer Weights
- ensemble: 45.0%
- advanced: 25.0%
- deep_learning: 30.0%

### Advanced Model Weights
- kalman: 30.0%
- expected_return: 25.0%
- probability: 25.0%
- rl_agent: 20.0%

### Deep Learning Weights
- lstm: 55.0%
- transformer: 45.0%

---
## LSTM prioritized
**Boost LSTM due to Phase E success, reduce Transformer**

### Layer Weights
- ensemble: 40.0%
- advanced: 30.0%
- deep_learning: 30.0%

### Advanced Model Weights
- kalman: 33.0%
- expected_return: 22.0%
- probability: 22.0%
- rl_agent: 23.0%

### Deep Learning Weights
- lstm: 70.0%
- transformer: 30.0%

---
