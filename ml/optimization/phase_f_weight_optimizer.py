"""Phase F: Model Weight Optimization & Fine-Tuning

Analyzes and optimizes weights across the 14-model ensemble:
- Phase A (4): DirectionalClassifier, KalmanStateSpaceModel, ExpectedReturnModel, ProbabilityModel
- Phase B (5): GradBoost-Dir, GradBoost-Return, Volatility, Quantile×2
- Phase C (2): RegimeClassifier, HMMRegimeModel
- Phase D (1): RLAgent
- Phase E (2): LSTMModel, TransformerModel

Tasks:
1. Baseline performance analysis
2. Weight scenario testing
3. Optimal weight implementation
4. Confidence threshold tuning
5. Regime-aware weight optimization
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import numpy as np
from datetime import datetime

# Try importing ML modules
try:
    from ml.registry.model_registry import ModelRegistry
    from ml.aggregation.signal_aggregator import MultiModelAggregator, SignalResult
except ImportError as e:
    print(f"Warning: Could not import ML modules: {e}")
    ModelRegistry = None
    MultiModelAggregator = None


class PhaseF_WeightOptimizer:
    """Manages weight optimization across all 14 models."""

    def __init__(self, registry: Optional[ModelRegistry] = None):
        self.registry = registry or ModelRegistry()
        self.baseline_config = self._get_phase_e_baseline()
        self.results = {}

    def _get_phase_e_baseline(self) -> Dict[str, Any]:
        """Phase E weight architecture (baseline for optimization)."""
        return {
            "name": "Phase E Baseline",
            "description": "0.7 × (ensemble 60% + advanced 40%) + 0.3 × deep_learning(LSTM 50% + Transformer 50%)",
            "layer_weights": {
                "ensemble": 0.42,  # 0.6 × 0.7
                "advanced": 0.28,  # 0.4 × 0.7
                "deep_learning": 0.30,  # 0.3
            },
            "advanced_model_weights": {
                "kalman": 0.33,
                "expected_return": 0.25,
                "probability": 0.25,
                "rl_agent": 0.17,
            },
            "deep_learning_weights": {
                "lstm": 0.50,
                "transformer": 0.50,
            },
            "confidence_config": {
                "base_formula": "abs(p_up - 0.5) * 2.0",
                "regime_dampening": True,
                "trending_boost": 0.2,
                "ranging_dampen": 0.3,
                "chaotic_dampen": 0.3,
            },
            "volatility_dampening": {
                "enabled": True,
                "vol_threshold": 0.01,
            },
        }

    def create_weight_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """Create 5-10 weight scenarios for testing."""
        baseline = self.baseline_config["layer_weights"]

        scenarios = {
            "Scenario_1_Equal_Weights": {
                "name": "Equal weights (1/14 each)",
                "description": "All 14 models equally weighted for comparison",
                "layer_weights": {
                    "ensemble": 1/14,
                    "advanced": 4/14,
                    "deep_learning": 2/14,
                },
                "advanced_model_weights": {
                    "kalman": 0.25,
                    "expected_return": 0.25,
                    "probability": 0.25,
                    "rl_agent": 0.25,
                },
                "deep_learning_weights": {
                    "lstm": 0.50,
                    "transformer": 0.50,
                },
            },

            "Scenario_2_Boost_Top_Performers": {
                "name": "Boost top 3 performers",
                "description": "Increase weight on best-performing models (+10% each)",
                "layer_weights": {
                    "ensemble": 0.50,  # up from 0.42 (LSTM often best)
                    "advanced": 0.28,  # stable
                    "deep_learning": 0.22,  # reduced slightly
                },
                "advanced_model_weights": {
                    "kalman": 0.40,      # boosted
                    "expected_return": 0.20,
                    "probability": 0.20,
                    "rl_agent": 0.20,
                },
                "deep_learning_weights": {
                    "lstm": 0.70,        # boosted
                    "transformer": 0.30,
                },
            },

            "Scenario_3_Reduce_Weak_Performers": {
                "name": "Reduce weak performers",
                "description": "Decrease weight on underperforming models (-5% each)",
                "layer_weights": {
                    "ensemble": 0.35,  # reduced
                    "advanced": 0.40,  # increased
                    "deep_learning": 0.25,  # reduced
                },
                "advanced_model_weights": {
                    "kalman": 0.20,
                    "expected_return": 0.30,  # boosted
                    "probability": 0.20,
                    "rl_agent": 0.30,  # boosted
                },
                "deep_learning_weights": {
                    "lstm": 0.40,
                    "transformer": 0.60,  # boosted
                },
            },

            "Scenario_4_Ensemble_Advanced_Deep": {
                "name": "Separate layer weights (50/20/30)",
                "description": "Increase ensemble, reduce advanced, stable deep",
                "layer_weights": {
                    "ensemble": 0.50,
                    "advanced": 0.20,
                    "deep_learning": 0.30,
                },
                "advanced_model_weights": {
                    "kalman": 0.33,
                    "expected_return": 0.25,
                    "probability": 0.25,
                    "rl_agent": 0.17,
                },
                "deep_learning_weights": {
                    "lstm": 0.50,
                    "transformer": 0.50,
                },
            },

            "Scenario_5_Trending_Weights": {
                "name": "Trending market bias",
                "description": "Boost momentum models (ensemble, RLAgent, LSTM)",
                "layer_weights": {
                    "ensemble": 0.50,
                    "advanced": 0.20,
                    "deep_learning": 0.30,
                },
                "advanced_model_weights": {
                    "kalman": 0.15,
                    "expected_return": 0.15,
                    "probability": 0.10,
                    "rl_agent": 0.60,  # Boost RL (learns momentum)
                },
                "deep_learning_weights": {
                    "lstm": 0.65,  # Boost LSTM
                    "transformer": 0.35,
                },
            },

            "Scenario_6_Ranging_Weights": {
                "name": "Ranging market bias",
                "description": "Boost mean-reversion models (Kalman, Probability, Transformer)",
                "layer_weights": {
                    "ensemble": 0.30,
                    "advanced": 0.40,
                    "deep_learning": 0.30,
                },
                "advanced_model_weights": {
                    "kalman": 0.45,      # Boost Kalman (captures mean)
                    "expected_return": 0.15,
                    "probability": 0.30,  # Boost Probability
                    "rl_agent": 0.10,
                },
                "deep_learning_weights": {
                    "lstm": 0.40,
                    "transformer": 0.60,  # Boost Transformer
                },
            },

            "Scenario_7_Chaotic_Conservative": {
                "name": "Chaotic market (conservative)",
                "description": "Mute aggressive models, boost ensemble robustness",
                "layer_weights": {
                    "ensemble": 0.60,   # Boost ensemble
                    "advanced": 0.20,
                    "deep_learning": 0.20,  # Reduce deep learning
                },
                "advanced_model_weights": {
                    "kalman": 0.35,
                    "expected_return": 0.20,
                    "probability": 0.35,  # Boost probability
                    "rl_agent": 0.10,  # Mute RL (risky in chaos)
                },
                "deep_learning_weights": {
                    "lstm": 0.60,
                    "transformer": 0.40,
                },
            },

            "Scenario_8_Deep_Learning_Heavy": {
                "name": "Deep learning emphasis",
                "description": "Increase deep learning models (LSTM + Transformer)",
                "layer_weights": {
                    "ensemble": 0.30,
                    "advanced": 0.20,
                    "deep_learning": 0.50,  # Boost deep learning
                },
                "advanced_model_weights": {
                    "kalman": 0.25,
                    "expected_return": 0.25,
                    "probability": 0.25,
                    "rl_agent": 0.25,
                },
                "deep_learning_weights": {
                    "lstm": 0.50,
                    "transformer": 0.50,
                },
            },

            "Scenario_9_Balanced_Optimization": {
                "name": "Balanced 45/25/30 split",
                "description": "Refined balance: ensemble 45%, advanced 25%, deep 30%",
                "layer_weights": {
                    "ensemble": 0.45,
                    "advanced": 0.25,
                    "deep_learning": 0.30,
                },
                "advanced_model_weights": {
                    "kalman": 0.30,
                    "expected_return": 0.25,
                    "probability": 0.25,
                    "rl_agent": 0.20,
                },
                "deep_learning_weights": {
                    "lstm": 0.55,
                    "transformer": 0.45,
                },
            },

            "Scenario_10_LSTM_Priority": {
                "name": "LSTM prioritized",
                "description": "Boost LSTM due to Phase E success, reduce Transformer",
                "layer_weights": {
                    "ensemble": 0.40,
                    "advanced": 0.30,
                    "deep_learning": 0.30,
                },
                "advanced_model_weights": {
                    "kalman": 0.33,
                    "expected_return": 0.22,
                    "probability": 0.22,
                    "rl_agent": 0.23,
                },
                "deep_learning_weights": {
                    "lstm": 0.70,  # Boost LSTM
                    "transformer": 0.30,  # Reduce Transformer
                },
            },
        }

        return scenarios

    def document_baseline(self) -> str:
        """Generate baseline analysis document."""
        baseline = self.baseline_config
        doc = f"""# Phase F Baseline Analysis

**Phase E Weight Architecture (Baseline)**

## Current Weights
- Layer 1 (Ensemble): {baseline['layer_weights']['ensemble']:.1%}
- Layer 2 (Advanced): {baseline['layer_weights']['advanced']:.1%}
- Layer 3 (Deep Learning): {baseline['layer_weights']['deep_learning']:.1%}

## Advanced Model Weights (Normalized)
- Kalman: {baseline['advanced_model_weights']['kalman']:.1%}
- ExpectedReturn: {baseline['advanced_model_weights']['expected_return']:.1%}
- Probability: {baseline['advanced_model_weights']['probability']:.1%}
- RLAgent: {baseline['advanced_model_weights']['rl_agent']:.1%}

## Deep Learning Weights (Normalized)
- LSTM: {baseline['deep_learning_weights']['lstm']:.1%}
- Transformer: {baseline['deep_learning_weights']['transformer']:.1%}

## Confidence Configuration
- Base Formula: {baseline['confidence_config']['base_formula']}
- Regime Dampening Enabled: {baseline['confidence_config']['regime_dampening']}
- Trending Boost: {baseline['confidence_config']['trending_boost']:.1%}
- Ranging Dampen: {baseline['confidence_config']['ranging_dampen']:.1%}
- Chaotic Dampen: {baseline['confidence_config']['chaotic_dampen']:.1%}

## Volatility Dampening
- Enabled: {baseline['volatility_dampening']['enabled']}
- Vol Threshold: {baseline['volatility_dampening']['vol_threshold']}

## Models Included (14 Total)
- Phase A (4): DirectionalClassifier, KalmanStateSpaceModel, ExpectedReturnModel, ProbabilityModel
- Phase B (5): GradBoost-Dir, GradBoost-Return, VolatilityModel, QuantileModel×2
- Phase C (2): RegimeClassifier, HMMRegimeModel
- Phase D (1): RLAgent
- Phase E (2): LSTMModel, TransformerModel

---
"""
        return doc

    def document_scenarios(self) -> str:
        """Generate scenarios documentation."""
        scenarios = self.create_weight_scenarios()
        doc = "# Phase F Weight Optimization Scenarios\n\n"

        for key, scenario in scenarios.items():
            doc += f"## {scenario['name']}\n"
            doc += f"**{scenario['description']}**\n\n"
            doc += "### Layer Weights\n"
            for layer, weight in scenario['layer_weights'].items():
                doc += f"- {layer}: {weight:.1%}\n"
            doc += "\n### Advanced Model Weights\n"
            for model, weight in scenario['advanced_model_weights'].items():
                doc += f"- {model}: {weight:.1%}\n"
            doc += "\n### Deep Learning Weights\n"
            for model, weight in scenario['deep_learning_weights'].items():
                doc += f"- {model}: {weight:.1%}\n"
            doc += "\n---\n"

        return doc

    def save_analysis(self, output_dir: str = "docs") -> None:
        """Save analysis documents."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        # Save baseline
        baseline_doc = self.document_baseline()
        baseline_path = output_path / "ANALYSIS_baseline_phase_e.md"
        with open(baseline_path, 'w') as f:
            f.write(baseline_doc)
        print(f"[+] Baseline analysis saved to {baseline_path}")

        # Save scenarios
        scenarios_doc = self.document_scenarios()
        scenarios_path = output_path / "OPTIMIZATION_weight_scenarios.md"
        with open(scenarios_path, 'w') as f:
            f.write(scenarios_doc)
        print(f"[+] Scenarios documentation saved to {scenarios_path}")

        # Save scenarios as JSON for programmatic use
        scenarios = self.create_weight_scenarios()
        scenarios_json_path = output_path / "weight_scenarios.json"
        with open(scenarios_json_path, 'w') as f:
            json.dump(scenarios, f, indent=2)
        print(f"[+] Weight scenarios JSON saved to {scenarios_json_path}")


def main():
    """Run Phase F analysis."""
    print("[*] Phase F: Model Weight Optimization & Fine-Tuning")
    print("=" * 60)

    optimizer = PhaseF_WeightOptimizer()

    print("\n[*] Creating weight optimization scenarios...")
    scenarios = optimizer.create_weight_scenarios()
    print(f"[+] Created {len(scenarios)} test scenarios")

    print("\n[*] Generating analysis documentation...")
    optimizer.save_analysis()

    print("\n[+] Phase F Analysis Complete!")
    print("\n[*] Next Steps:")
    print("1. Review ANALYSIS_baseline_phase_e.md")
    print("2. Review OPTIMIZATION_weight_scenarios.md")
    print("3. Run backtests for each scenario")
    print("4. Compare results and select optimal weights")
    print("5. Implement optimal weights in signal_aggregator.py")
    print("6. Fine-tune confidence thresholds")


if __name__ == "__main__":
    main()
