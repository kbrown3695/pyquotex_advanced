"""Reinforcement Learning Agent model using REINFORCE policy gradient.

Phase D implementation: 2-layer MLP with policy gradient training.
Learns to predict BUY/SELL actions from market state features.
"""

from typing import Any, Dict, List, Optional
import logging
import warnings
import numpy as np
import joblib

import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical

from ml.models.base import BaseTradingModel

logging.getLogger("torch").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")


class RLPolicyNetwork(nn.Module):
    """2-layer MLP policy network for action selection."""

    def __init__(self, input_dim: int = 13, hidden_dim: int = 64) -> None:
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, 2)  # 2 actions: BUY (1), SELL (0)
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass: x -> hidden -> logits."""
        x = self.relu(self.fc1(x))
        logits = self.fc2(x)
        return logits


class RLAgent(BaseTradingModel):
    """Reinforcement Learning Agent with REINFORCE policy gradient.

    Supervised training mode: learns to align with other models' predictions.
    Uses policy gradient (REINFORCE) to maximize probability of correct actions.
    """

    def __init__(
        self,
        input_dim: int = 13,
        hidden_dim: int = 64,
        learning_rate: float = 0.01,
        device: str = "cpu",
    ) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.learning_rate = learning_rate
        self.device = device
        self.network: Optional[RLPolicyNetwork] = None
        self.optimizer: Optional[optim.Adam] = None
        self._feature_names: Optional[list] = None
        self._metadata: Dict[str, Any] = {}
        self._training_history: List[float] = []

        self._initialize_network()

    def _initialize_network(self) -> None:
        """Initialize the policy network and optimizer."""
        self.network = RLPolicyNetwork(self.input_dim, self.hidden_dim).to(self.device)
        self.optimizer = optim.Adam(self.network.parameters(), lr=self.learning_rate)

    def train(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train policy network using REINFORCE on labeled data.

        Args:
            X: Feature matrix (n_samples, input_dim)
            y: Target labels (n_samples,) where 0=SELL, 1=BUY

        Training approach:
        - Convert labels to actions
        - Forward pass through network to get logits
        - Sample from categorical distribution (policy)
        - Compute policy loss: -log(P(action)) for correct action
        - Backprop to maximize P(correct action)
        """
        self.network.train()

        # Convert numpy to torch
        X_tensor = torch.from_numpy(X).float().to(self.device)
        y_tensor = torch.from_numpy(y).long().to(self.device)

        # Training loop
        epochs = min(100, max(10, len(X) // 8))  # Auto-scale epochs
        batch_size = min(32, max(8, len(X) // 4))

        for epoch in range(epochs):
            epoch_loss = 0.0
            n_batches = 0

            for i in range(0, len(X_tensor), batch_size):
                X_batch = X_tensor[i : i + batch_size]
                y_batch = y_tensor[i : i + batch_size]

                # Forward pass
                self.optimizer.zero_grad()
                logits = self.network(X_batch)
                probs = torch.softmax(logits, dim=1)

                # Policy loss: -log P(correct_action)
                correct_action_probs = probs[range(len(probs)), y_batch]
                loss = -torch.log(correct_action_probs + 1e-8).mean()

                # Backprop
                loss.backward()
                self.optimizer.step()

                epoch_loss += loss.item()
                n_batches += 1

            avg_loss = epoch_loss / max(n_batches, 1)
            self._training_history.append(avg_loss)

        self.network.eval()

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels (deterministic argmax)."""
        proba = self.predict_proba(X)
        return np.argmax(proba, axis=1)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities: shape (n_samples, 2), P(BUY) = [:, 1]."""
        self.network.eval()

        with torch.no_grad():
            X_tensor = torch.from_numpy(X).float().to(self.device)
            logits = self.network(X_tensor)
            probs = torch.softmax(logits, dim=1)
            return probs.cpu().numpy()

    def get_params(self) -> Dict[str, Any]:
        """Get model hyperparameters."""
        return {
            "input_dim": self.input_dim,
            "hidden_dim": self.hidden_dim,
            "learning_rate": self.learning_rate,
            "device": self.device,
        }

    def get_metadata(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {
            "model_type": "rl_agent",
            "algorithm": "REINFORCE",
            "params": self.get_params(),
            "feature_names": self._feature_names,
            "training_epochs": len(self._training_history),
            "final_loss": self._training_history[-1] if self._training_history else None,
        }

    def get_feature_importances(self) -> np.ndarray:
        """Return weights from first layer as feature importance proxy."""
        if self.network is None:
            return np.array([])
        with torch.no_grad():
            weights = self.network.fc1.weight.data.cpu().numpy()
            importances = np.abs(weights).mean(axis=0)
            return importances / importances.sum() if importances.sum() > 0 else importances

    def set_feature_names(self, feature_names: list) -> None:
        """Set feature names for metadata."""
        self._feature_names = feature_names

    def save(self, path: str) -> None:
        """Save model to disk using joblib."""
        joblib.dump(
            {
                "network_state": self.network.state_dict() if self.network else None,
                "input_dim": self.input_dim,
                "hidden_dim": self.hidden_dim,
                "learning_rate": self.learning_rate,
                "feature_names": self._feature_names,
                "metadata": self._metadata,
                "training_history": self._training_history,
            },
            path,
        )

    @classmethod
    def load(cls, path: str) -> "RLAgent":
        """Load model from disk."""
        data = joblib.load(path)
        instance = cls(
            input_dim=data.get("input_dim", 13),
            hidden_dim=data.get("hidden_dim", 64),
            learning_rate=data.get("learning_rate", 0.01),
        )
        if data.get("network_state"):
            instance.network.load_state_dict(data["network_state"])
        instance._feature_names = data.get("feature_names")
        instance._metadata = data.get("metadata", {})
        instance._training_history = data.get("training_history", [])
        return instance


__all__: List[str] = ["RLAgent", "RLPolicyNetwork"]
