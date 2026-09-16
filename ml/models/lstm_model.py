"""Long Short-Term Memory (LSTM) model for sequence prediction.

Phase E implementation: 2-layer LSTM for capturing temporal dependencies
in price sequences. Processes (batch, 26, 11) sequence inputs where 26 is
the lookback window and 11 is the number of features.
"""

from typing import Any, Dict, List, Optional
import logging
import warnings
import numpy as np
import joblib

import torch
import torch.nn as nn
import torch.optim as optim

from ml.models.base import BaseTradingModel

logging.getLogger("torch").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")


class LSTMNetwork(nn.Module):
	"""2-layer LSTM network for sequence modeling."""

	def __init__(self, input_dim: int = 11, hidden_dim: int = 64, seq_len: int = 26) -> None:
		super().__init__()
		self.hidden_dim = hidden_dim
		self.seq_len = seq_len

		# 2-layer LSTM with dropout
		self.lstm = nn.LSTM(
			input_size=input_dim,
			hidden_size=hidden_dim,
			num_layers=2,
			dropout=0.3,
			batch_first=True,
		)

		# Dense layers
		self.fc1 = nn.Linear(hidden_dim, 32)
		self.fc2 = nn.Linear(32, 2)  # 2 outputs: [P(SELL), P(BUY)]
		self.relu = nn.ReLU()

	def forward(self, x: torch.Tensor) -> torch.Tensor:
		"""Forward pass: (batch, seq_len, input_dim) -> (batch, 2) logits."""
		# LSTM: (batch, seq_len, input_dim) -> (batch, seq_len, hidden_dim)
		lstm_out, _ = self.lstm(x)

		# Take last hidden state
		last_hidden = lstm_out[:, -1, :]  # (batch, hidden_dim)

		# Dense layers
		x = self.relu(self.fc1(last_hidden))  # (batch, 32)
		logits = self.fc2(x)  # (batch, 2)
		return logits


class LSTMModel(BaseTradingModel):
	"""LSTM-based trading model for sequence prediction.

	Processes sequences of 26 candles with 11 features each to predict
	the next price direction (BUY/SELL).
	"""

	def __init__(
		self,
		input_dim: int = 11,
		hidden_dim: int = 64,
		seq_len: int = 26,
		learning_rate: float = 0.01,
		device: str = "cpu",
	) -> None:
		self.input_dim = input_dim
		self.hidden_dim = hidden_dim
		self.seq_len = seq_len
		self.learning_rate = learning_rate
		self.device = device
		self.network: Optional[LSTMNetwork] = None
		self.optimizer: Optional[optim.Adam] = None
		self._feature_names: Optional[list] = None
		self._metadata: Dict[str, Any] = {}
		self._training_history: List[float] = []

		self._initialize_network()

	def _initialize_network(self) -> None:
		"""Initialize the LSTM network and optimizer."""
		self.network = LSTMNetwork(self.input_dim, self.hidden_dim, self.seq_len).to(self.device)
		self.optimizer = optim.Adam(self.network.parameters(), lr=self.learning_rate)

	def _build_sequences(self, X: np.ndarray, seq_len: int = 26) -> torch.Tensor:
		"""Build sequences from flat feature matrix.

		Args:
			X: Feature matrix (n_samples, input_dim) with flat features
			seq_len: Length of sequences to build (default 26)

		Returns:
			Tensor of shape (n_sequences, seq_len, input_dim)
		"""
		sequences = []

		# If X is already shaped as (n, seq_len, input_dim), use it directly
		if len(X.shape) == 3 and X.shape[1] == seq_len:
			return torch.from_numpy(X).float()

		# Otherwise, treat X as flat features and build sliding window sequences
		# This handles the case where features are extracted independently
		# For LSTM, we need to reshape historical features into sequences
		if len(X) >= seq_len:
			# Take the last seq_len samples as a single sequence
			seq = X[-seq_len:]
			sequences.append(seq)
		elif len(X) > 0:
			# Pad shorter sequences with the first row
			padding = np.tile(X[0:1], (seq_len - len(X), 1))
			seq = np.vstack([padding, X])
			sequences.append(seq)

		if sequences:
			return torch.from_numpy(np.array(sequences)).float()
		else:
			# Fallback: create a zero sequence
			return torch.zeros((1, seq_len, self.input_dim)).float()

	def train(self, X: np.ndarray, y: np.ndarray) -> None:
		"""Train LSTM network on labeled sequence data.

		Args:
			X: Feature matrix (n_samples, input_dim) or (n_samples, seq_len, input_dim)
			y: Target labels (n_samples,) where 0=SELL, 1=BUY

		Training approach:
		- Build sequences of length 26 from features
		- Forward pass through LSTM
		- Compute cross-entropy loss
		- Backprop to minimize loss
		"""
		self.network.train()

		# Build sequences from flat features
		X_seq = self._build_sequences(X, self.seq_len)

		# If we have fewer sequences than samples, replicate the sequence for training
		# This handles the case where we can only build one sequence from all data
		if len(X_seq) < len(y):
			n_replicate = max(1, len(y) // len(X_seq))
			X_seq = X_seq.repeat(n_replicate, 1, 1)
			y_subset = y[:len(X_seq)]
		else:
			y_subset = y

		# Ensure tensor and label have same length
		min_len = min(len(X_seq), len(y_subset))
		X_seq = X_seq[:min_len].to(self.device)
		y_tensor = torch.from_numpy(y_subset[:min_len]).long().to(self.device)

		# Training loop
		epochs = min(50, max(10, len(y_subset) // 8))
		batch_size = max(4, len(y_subset) // 4)

		for epoch in range(epochs):
			epoch_loss = 0.0
			n_batches = 0

			for i in range(0, len(X_seq), batch_size):
				X_batch = X_seq[i : i + batch_size]
				y_batch = y_tensor[i : i + batch_size]

				# Forward pass
				self.optimizer.zero_grad()
				logits = self.network(X_batch)
				loss = nn.CrossEntropyLoss()(logits, y_batch)

				# Backward pass with gradient clipping
				loss.backward()
				torch.nn.utils.clip_grad_norm_(self.network.parameters(), max_norm=1.0)
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
			X_seq = self._build_sequences(X, self.seq_len).to(self.device)
			logits = self.network(X_seq)
			probs = torch.softmax(logits, dim=1)
			return probs.cpu().numpy()

	def get_params(self) -> Dict[str, Any]:
		"""Get model hyperparameters."""
		return {
			"input_dim": self.input_dim,
			"hidden_dim": self.hidden_dim,
			"seq_len": self.seq_len,
			"learning_rate": self.learning_rate,
			"device": self.device,
		}

	def get_metadata(self) -> Dict[str, Any]:
		"""Get model metadata."""
		return {
			"model_type": "lstm",
			"architecture": "2-layer LSTM",
			"params": self.get_params(),
			"feature_names": self._feature_names,
			"training_epochs": len(self._training_history),
			"final_loss": self._training_history[-1] if self._training_history else None,
		}

	def get_feature_importances(self) -> np.ndarray:
		"""Return approximated feature importances from LSTM weights."""
		if self.network is None:
			return np.array([])

		with torch.no_grad():
			# Get LSTM input weights (first layer, first direction)
			lstm_weights = self.network.lstm.weight_ih_l0.data.cpu().numpy()
			# Sum across hidden states (each of 4 gates)
			importances = np.abs(lstm_weights).reshape(-1, self.input_dim).sum(axis=0)
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
				"seq_len": self.seq_len,
				"learning_rate": self.learning_rate,
				"feature_names": self._feature_names,
				"metadata": self._metadata,
				"training_history": self._training_history,
			},
			path,
		)

	@classmethod
	def load(cls, path: str) -> "LSTMModel":
		"""Load model from disk."""
		data = joblib.load(path)
		instance = cls(
			input_dim=data.get("input_dim", 11),
			hidden_dim=data.get("hidden_dim", 64),
			seq_len=data.get("seq_len", 26),
			learning_rate=data.get("learning_rate", 0.01),
		)
		if data.get("network_state"):
			instance.network.load_state_dict(data["network_state"])
		instance._feature_names = data.get("feature_names")
		instance._metadata = data.get("metadata", {})
		instance._training_history = data.get("training_history", [])
		return instance


__all__: List[str] = ["LSTMModel", "LSTMNetwork"]
