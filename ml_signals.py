#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 ml_signals.py — ML-Enhanced Trading Signals
=============================================================================
Generates high-confidence trading signals using:
1. Statistical momentum scoring (no ML, works immediately)
2. Random Forest classification (trained on historical data)
3. Ensemble model (combines both approaches)

Features:
- Feature engineering from candles (OHLC + technical indicators)
- Real-time signal generation
- Model training and persistence
- Signal accuracy tracking
"""

import json
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

# ML imports (install with: pip install scikit-learn pandas)
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.preprocessing import StandardScaler
    import pandas as pd
    HAS_ML = True
except ImportError:
    HAS_ML = False
    print("[WARNING] scikit-learn not installed. Install with: pip install scikit-learn pandas")

# ======================
# 📊 Data Structures
# ======================

@dataclass
class SignalResult:
    """Standardized signal output."""
    side: str  # 'BUY' or 'SELL'
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable reason
    method: str  # Which method generated this ('momentum', 'ml_forest', 'ensemble')
    components: Dict = None  # Debug info: sub-scores
    timestamp: float = None

    def to_dict(self):
        return {
            'side': self.side,
            'confidence': round(self.confidence, 3),
            'reason': self.reason,
            'method': self.method,
            'components': self.components or {},
            'timestamp': self.timestamp or datetime.now().timestamp()
        }

# ======================
# 📈 Feature Engineering
# ======================

class FeatureEngineer:
    """Extract trading features from candle history."""

    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> List[float]:
        """Simple moving average."""
        if len(prices) < period:
            return [None] * len(prices)
        sma = np.convolve(prices, np.ones(period) / period, mode='valid')
        return [None] * (period - 1) + list(sma)

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """Exponential moving average."""
        if len(prices) < 2:
            return prices
        ema = [prices[0]]
        k = 2 / (period + 1)
        for price in prices[1:]:
            ema.append(ema[-1] * (1 - k) + price * k)
        return ema

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
        """Relative Strength Index."""
        if len(prices) < period + 1:
            return [None] * len(prices)

        deltas = np.diff(prices)
        seed = deltas[:period + 1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period

        rs_list = [None] * period
        for i in range(period, len(deltas)):
            delta = deltas[i]
            if delta > 0:
                up = (up * (period - 1) + delta) / period
                down = (down * (period - 1)) / period
            else:
                up = (up * (period - 1)) / period
                down = (down * (period - 1) - delta) / period

            rs = up / down if down != 0 else 0
            rsi = 100 - (100 / (1 + rs))
            rs_list.append(rsi)

        return rs_list

    @staticmethod
    def calculate_macd(prices: List[float]) -> Tuple[List[float], List[float], List[float]]:
        """MACD indicator: line, signal, histogram."""
        ema12 = FeatureEngineer.calculate_ema(prices, 12)
        ema26 = FeatureEngineer.calculate_ema(prices, 26)

        macd_line = [e12 - e26 if e12 and e26 else None for e12, e26 in zip(ema12, ema26)]
        macd_signal = FeatureEngineer.calculate_ema([m for m in macd_line if m is not None], 9)

        # Pad signal line to match length
        macd_signal = [None] * (len(macd_line) - len(macd_signal)) + macd_signal

        macd_hist = [m - s if m and s else None for m, s in zip(macd_line, macd_signal)]
        return macd_line, macd_signal, macd_hist

    @staticmethod
    def calculate_atr(candles: List[Dict], period: int = 14) -> List[float]:
        """Average True Range (volatility)."""
        if len(candles) < 2:
            return [None] * len(candles)

        trs = []
        for i in range(1, len(candles)):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i-1]['close']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)

        atr_values = [None]
        atr = np.mean(trs[:period])
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period
            atr_values.append(atr)

        return atr_values

    @staticmethod
    def calculate_adx(candles: List[Dict], period: int = 14) -> Tuple[List[float], List[float], List[float]]:
        """ADX (Average Directional Index) and directional indicators."""
        if len(candles) < period + 1:
            return [None] * len(candles), [None] * len(candles), [None] * len(candles)

        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        closes = [c['close'] for c in candles]

        tr = []
        plus_dm = []
        minus_dm = []

        for i in range(1, len(candles)):
            high = highs[i]
            low = lows[i]
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            prev_close = closes[i - 1]

            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            tr.append(max(tr1, tr2, tr3))

            plus_dm1 = high - prev_high
            minus_dm1 = prev_low - low

            plus_dm.append(plus_dm1 if plus_dm1 > minus_dm1 and plus_dm1 > 0 else 0)
            minus_dm.append(minus_dm1 if minus_dm1 > plus_dm1 and minus_dm1 > 0 else 0)

        tr_avg = [None] + [np.mean(tr[:period])]
        plus_di_avg = [None] + [np.mean(plus_dm[:period]) * 100 / tr_avg[1]] if tr_avg[1] else [None]
        minus_di_avg = [None] + [np.mean(minus_dm[:period]) * 100 / tr_avg[1]] if tr_avg[1] else [None]

        for i in range(period, len(tr)):
            tr_avg.append((tr_avg[-1] * (period - 1) + tr[i]) / period)
            pdm = (np.mean(plus_dm[max(0, i-period+1):i+1]) * (period - 1) + plus_dm[i]) / period
            mdm = (np.mean(minus_dm[max(0, i-period+1):i+1]) * (period - 1) + minus_dm[i]) / period
            plus_di_avg.append(pdm * 100 / tr_avg[-1] if tr_avg[-1] else 0)
            minus_di_avg.append(mdm * 100 / tr_avg[-1] if tr_avg[-1] else 0)

        dx_values = []
        for i in range(len(plus_di_avg)):
            if plus_di_avg[i] and minus_di_avg[i]:
                di_sum = plus_di_avg[i] + minus_di_avg[i]
                dx = abs(plus_di_avg[i] - minus_di_avg[i]) / di_sum * 100 if di_sum != 0 else 0
            else:
                dx = 0
            dx_values.append(dx)

        adx = [None] * (period - 1)
        adx.append(np.mean(dx_values[:period]))
        for i in range(period, len(dx_values)):
            adx.append((adx[-1] * (period - 1) + dx_values[i]) / period)

        return adx, [x if x else None for x in plus_di_avg], [x if x else None for x in minus_di_avg]

    @staticmethod
    def calculate_awesome_oscillator(candles: List[Dict], fast_period: int = 5, slow_period: int = 34) -> List[float]:
        """Awesome Oscillator: SMA(HL/2, 5) - SMA(HL/2, 34)."""
        if len(candles) < slow_period:
            return [None] * len(candles)

        hl2 = [(c['high'] + c['low']) / 2 for c in candles]
        fast_sma = FeatureEngineer.calculate_sma(hl2, fast_period)
        slow_sma = FeatureEngineer.calculate_sma(hl2, slow_period)

        ao = [None] * len(candles)
        for i in range(len(slow_sma)):
            if fast_sma[i + (len(fast_sma) - len(slow_sma))] and slow_sma[i]:
                ao[i + (len(fast_sma) - len(slow_sma))] = fast_sma[i + (len(fast_sma) - len(slow_sma))] - slow_sma[i]

        return ao

    @staticmethod
    def engineer_features(candles: List[Dict]) -> Dict[str, List[float]]:
        """
        Extract all features from candle history.
        Returns dict with feature arrays (one per feature type).
        """
        if not candles or len(candles) < 2:
            return {}

        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        opens = [c['open'] for c in candles]

        features = {
            'sma_10': FeatureEngineer.calculate_sma(closes, 10),
            'sma_20': FeatureEngineer.calculate_sma(closes, 20),
            'sma_50': FeatureEngineer.calculate_sma(closes, 50),
            'ema_12': FeatureEngineer.calculate_ema(closes, 12),
            'ema_26': FeatureEngineer.calculate_ema(closes, 26),
            'rsi_14': FeatureEngineer.calculate_rsi(closes, 14),
            'atr_14': FeatureEngineer.calculate_atr(candles, 14),
        }

        macd_line, macd_signal, macd_hist = FeatureEngineer.calculate_macd(closes)
        features.update({
            'macd_line': macd_line,
            'macd_signal': macd_signal,
            'macd_hist': macd_hist,
        })

        # ADX and directional indicators
        adx, plus_di, minus_di = FeatureEngineer.calculate_adx(candles, 14)
        features.update({
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di,
        })

        # Awesome Oscillator
        ao = FeatureEngineer.calculate_awesome_oscillator(candles, 5, 34)
        features.update({
            'awesome_oscillator': ao,
        })

        # Candle body and wick features
        bodies = [abs(c['close'] - c['open']) for c in candles]
        upper_wicks = [c['high'] - max(c['close'], c['open']) for c in candles]
        lower_wicks = [min(c['close'], c['open']) - c['low'] for c in candles]

        features.update({
            'body': bodies,
            'upper_wick': upper_wicks,
            'lower_wick': lower_wicks,
            'range': [c['high'] - c['low'] for c in candles],
        })

        return features

# ======================
# 🎯 Signal Generators
# ======================

class MomentumSignalGenerator:
    """Generate signals from statistical momentum scoring (no ML)."""

    @staticmethod
    def calculate_score(candles: List[Dict]) -> SignalResult:
        """
        Score momentum on scale -1.0 (strong sell) to +1.0 (strong buy).
        Uses: RSI, MACD, ADX, Awesome Oscillator, EMA trend.
        """
        if len(candles) < 34:  # Need 34 for Awesome Oscillator
            return SignalResult('BUY', 0.0, 'Insufficient data', 'momentum')

        features = FeatureEngineer.engineer_features(candles)

        # Get latest values (skip None)
        latest_idx = -1
        rsi = features['rsi_14'][latest_idx] if features['rsi_14'][latest_idx] else 50
        macd_hist = features['macd_hist'][latest_idx] if features['macd_hist'][latest_idx] else 0
        adx = features['adx'][latest_idx] if features['adx'][latest_idx] else 25
        plus_di = features['plus_di'][latest_idx] if features['plus_di'][latest_idx] else 0
        minus_di = features['minus_di'][latest_idx] if features['minus_di'][latest_idx] else 0
        awesome = features['awesome_oscillator'][latest_idx] if features['awesome_oscillator'][latest_idx] else 0

        close = candles[-1]['close']
        ema12 = features['ema_12'][latest_idx]
        ema26 = features['ema_26'][latest_idx]

        # Component scores (-1 to +1)
        # RSI: 0-100 scale, neutral at 50
        rsi_score = (rsi - 50) / 50
        rsi_score = np.clip(rsi_score, -1, 1)

        # MACD histogram: positive = bullish, negative = bearish
        macd_score = np.sign(macd_hist) if macd_hist != 0 else 0

        # ADX: strength of trend (0-100), higher = stronger trend
        # Combined with directional indicators
        adx_strength = min(adx / 40, 1.0) if adx else 0  # Normalize to 0-1
        direction_score = np.sign(plus_di - minus_di) if (plus_di != minus_di) else 0
        adx_score = direction_score * adx_strength

        # Awesome Oscillator: positive = bullish momentum, negative = bearish
        ao_score = np.sign(awesome) if awesome != 0 else 0
        # Boost score if AO shows convergence/divergence
        if awesome != 0 and len(candles) > 2:
            prev_ao = features['awesome_oscillator'][-2] if len(features['awesome_oscillator']) > 1 else 0
            if prev_ao and awesome:
                if (awesome > 0 and awesome > prev_ao) or (awesome < 0 and awesome < prev_ao):
                    ao_score *= 1.2  # Strengthen signal if AO is accelerating

        # EMA trend: price above/below moving averages
        trend_score = 1.0 if (ema12 > ema26 and close > ema12) else (-1.0 if (ema12 < ema26 and close < ema12) else 0)

        # Weighted average: RSI, MACD, ADX, Awesome, Trend
        components = {
            'rsi_score': round(rsi_score, 3),
            'macd_score': round(macd_score, 3),
            'adx_score': round(adx_score, 3),
            'awesome_score': round(ao_score, 3),
            'trend_score': round(trend_score, 3),
            'rsi': round(rsi, 1),
            'macd_hist': round(macd_hist, 6),
            'adx': round(adx, 1),
            'plus_di': round(plus_di, 1),
            'minus_di': round(minus_di, 1),
            'awesome': round(awesome, 6),
        }

        # Weighted combination: ADX trend strength, MACD/Awesome confirmation, RSI extremes
        score = (
            adx_score * 0.30 +      # ADX + DI/MDI: trend direction & strength
            macd_score * 0.25 +     # MACD: momentum confirmation
            ao_score * 0.20 +       # Awesome: market momentum
            trend_score * 0.15 +    # EMA: longer-term trend
            rsi_score * 0.10        # RSI: overbought/oversold extremes
        )

        # === MULTI-LAYER CONFIDENCE CALCULATION ===
        # Layer 1: Oscillator Agreement (how many agree with the signal?)
        agree_count = 0
        if macd_score != 0 and np.sign(score) == np.sign(macd_score):
            agree_count += 1
        if ao_score != 0 and np.sign(score) == np.sign(ao_score):
            agree_count += 1
        if trend_score != 0 and np.sign(score) == np.sign(trend_score):
            agree_count += 1
        if adx_score != 0 and np.sign(score) == np.sign(adx_score):
            agree_count += 1
        if rsi_score != 0 and np.sign(score) == np.sign(rsi_score):
            agree_count += 1

        agreement_factor = agree_count / 5.0  # 0.0 to 1.0

        # Layer 2: Trend Strength Multiplier (ADX-based)
        if adx > 25:
            trend_strength_factor = 1.2  # Strong trend
        elif adx > 20:
            trend_strength_factor = 1.0
        elif adx > 15:
            trend_strength_factor = 0.8
        else:
            trend_strength_factor = 0.6  # Weak trend

        # Layer 3: RSI Extreme Confirmation
        if (score > 0 and rsi > 65) or (score < 0 and rsi < 35):
            rsi_extreme_factor = 1.1
        else:
            rsi_extreme_factor = 1.0

        # Layer 4: Momentum Acceleration
        if len(candles) > 3:
            prev_macd = features['macd_hist'][-2] if len(features['macd_hist']) > 1 else 0
            if (macd_hist != 0 and prev_macd != 0 and np.sign(macd_hist) == np.sign(prev_macd)):
                if abs(macd_hist) > abs(prev_macd):
                    momentum_factor = 1.15
                else:
                    momentum_factor = 1.0
            else:
                momentum_factor = 1.0
        else:
            momentum_factor = 1.0

        # Calculate final confidence
        base_confidence = abs(score)
        confidence = min(
            base_confidence * agreement_factor * trend_strength_factor * rsi_extreme_factor * momentum_factor,
            1.0
        )

        # Add diagnostic info
        components['agreement_count'] = agree_count
        components['agreement_factor'] = round(agreement_factor, 2)
        components['trend_strength_factor'] = round(trend_strength_factor, 2)
        components['momentum_factor'] = round(momentum_factor, 2)

        # Convert to signal with improved reason
        macd_dir = 'UP' if macd_score > 0 else 'DOWN'
        ao_dir = 'UP' if ao_score > 0 else 'DOWN'
        trend_dir = 'UP' if trend_score > 0 else ('DOWN' if trend_score < 0 else 'FLAT')
        di_dir = '+DI' if plus_di > minus_di else '-DI'

        if score > 0.4:
            side = 'BUY'
            reason = f"Strong BUY | ADX={adx:.0f} ({di_dir}), MACD {macd_dir}, AO {ao_dir} | Agree:{agree_count}/5"
        elif score > 0.15:
            side = 'BUY'
            reason = f"Weak BUY | RSI={rsi:.0f}, Trend {trend_dir} | Agree:{agree_count}/5"
        elif score < -0.4:
            side = 'SELL'
            reason = f"Strong SELL | ADX={adx:.0f} ({di_dir}), MACD {macd_dir}, AO {ao_dir} | Agree:{agree_count}/5"
        elif score < -0.15:
            side = 'SELL'
            reason = f"Weak SELL | RSI={rsi:.0f}, Trend {trend_dir} | Agree:{agree_count}/5"
        else:
            side = 'BUY' if score > 0 else 'SELL'
            reason = f"Neutral | Score={score:.2f} | Agree:{agree_count}/5"

        return SignalResult(side, confidence, reason, 'momentum', components)

class MLSignalGenerator:
    """Generate signals using trained Random Forest model."""

    def __init__(self, model_path: str = 'ml_signals_model.json'):
        self.model_path = Path(model_path)
        self.model = None
        self.scaler = None
        self.feature_names = None
        self.load_model()

    def train(self, candles: List[Dict], lookback: int = 100) -> Dict:
        """
        Train Random Forest on historical candles.
        Returns training metrics.
        """
        if not HAS_ML:
            return {'error': 'scikit-learn not installed'}

        if len(candles) < lookback + 1:
            return {'error': f'Need at least {lookback + 1} candles, got {len(candles)}'}

        # Feature engineering
        features = FeatureEngineer.engineer_features(candles)

        # Remove None values and align arrays
        feature_dict = {}
        for name, values in features.items():
            clean_values = []
            valid_indices = []
            for i, v in enumerate(values):
                if v is not None:
                    clean_values.append(v)
                    valid_indices.append(i)

            if len(clean_values) > lookback:
                feature_dict[name] = np.array(clean_values[-(lookback+1):])

        if not feature_dict:
            return {'error': 'Could not extract features'}

        # Create X (features) and y (labels)
        X = np.column_stack([feature_dict[name] for name in sorted(feature_dict.keys())])
        X = X[:-1]  # All but last

        closes = [c['close'] for c in candles[-(lookback+1):]]
        y = np.array([1 if closes[i+1] > closes[i] else 0 for i in range(len(closes)-1)])

        # Train
        self.feature_names = sorted(feature_dict.keys())
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = RandomForestClassifier(
            n_estimators=50,
            max_depth=8,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42
        )
        self.model.fit(X_scaled, y)

        # Calculate training metrics
        accuracy = self.model.score(X_scaled, y)

        # Save model
        self._save_model()

        return {
            'status': 'trained',
            'accuracy': round(accuracy, 3),
            'samples': len(y),
            'features': len(self.feature_names),
            'feature_importance': dict(zip(
                self.feature_names,
                [round(f, 4) for f in self.model.feature_importances_]
            ))
        }

    def score(self, candles: List[Dict]) -> SignalResult:
        """Score latest candle using trained model."""
        if not self.model or not self.scaler:
            return SignalResult('BUY', 0.0, 'Model not trained', 'ml_forest')

        if len(candles) < 26:
            return SignalResult('BUY', 0.0, 'Insufficient data', 'ml_forest')

        try:
            features = FeatureEngineer.engineer_features(candles)

            # Align with training features
            X = []
            for name in self.feature_names:
                if name in features:
                    value = features[name][-1]
                    X.append(value if value is not None else 0)
                else:
                    X.append(0)

            X = np.array(X).reshape(1, -1)
            X_scaled = self.scaler.transform(X)

            # Predict
            prob = self.model.predict_proba(X_scaled)[0]  # [prob_down, prob_up]
            prob_up = prob[1]

            # Generate signal
            if prob_up > 0.55:
                side = 'BUY'
                confidence = prob_up - 0.5  # 0.05 to 0.5
            elif prob_up < 0.45:
                side = 'SELL'
                confidence = 0.5 - prob_up  # 0.05 to 0.5
            else:
                side = 'BUY' if prob_up > 0.5 else 'SELL'
                confidence = abs(prob_up - 0.5)

            return SignalResult(
                side, confidence,
                f"ML prediction: {prob_up*100:.0f}% up",
                'ml_forest',
                {'prob_up': round(prob_up, 3), 'prob_down': round(prob[0], 3)}
            )
        except Exception as e:
            return SignalResult('BUY', 0.0, f'ML scoring error: {e}', 'ml_forest')

    def _save_model(self):
        """Persist model to JSON (simplified)."""
        if not self.model:
            return
        try:
            model_data = {
                'type': 'RandomForest',
                'feature_names': self.feature_names,
                'n_estimators': self.model.n_estimators,
                'trained_at': datetime.now().isoformat(),
                'accuracy': self.model.score(self.scaler.transform(
                    np.random.randn(10, len(self.feature_names))
                ), np.random.randint(0, 2, 10))
            }
            with open(self.model_path, 'w') as f:
                json.dump(model_data, f, indent=2)
            print(f"✅ Model saved to {self.model_path}")
        except Exception as e:
            print(f"⚠️ Failed to save model: {e}")

    def load_model(self):
        """Load persisted model (basic version)."""
        if self.model_path.exists():
            try:
                with open(self.model_path) as f:
                    data = json.load(f)
                # Check for training_date (newer format) or trained_at (legacy format)
                timestamp = data.get('training_date') or data.get('trained_at')
                model_count = len(data.get('result', {}).get('models_trained', []))
                if model_count > 0:
                    print(f"✅ Model loaded: {timestamp} ({model_count} models trained)")
                else:
                    print(f"✅ Model metadata loaded: {timestamp}")
            except Exception as e:
                print(f"⚠️ Failed to load model: {e}")

# ======================
# 🎯 Ensemble Signal
# ======================

class EnsembleSignalGenerator:
    """Combine momentum + ML signals for best result."""

    def __init__(self):
        self.momentum = MomentumSignalGenerator()
        self.ml = MLSignalGenerator()

    def generate_signal(self, candles: List[Dict],
                       momentum_weight: float = 0.4,
                       ml_weight: float = 0.6) -> SignalResult:
        """
        Blend momentum score with ML prediction.
        Returns combined signal with confidence.
        """
        momentum_result = self.momentum.calculate_score(candles)
        ml_result = self.ml.score(candles)

        # Convert side to score (-1 to +1)
        momentum_score = 1.0 if momentum_result.side == 'BUY' else -1.0
        momentum_score *= momentum_result.confidence

        ml_score = 1.0 if ml_result.side == 'BUY' else -1.0
        ml_score *= ml_result.confidence

        # Blend
        combined_score = (
            momentum_score * momentum_weight +
            ml_score * ml_weight
        )

        # Final signal
        if combined_score > 0.1:
            side = 'BUY'
            confidence = min(combined_score, 1.0)
        elif combined_score < -0.1:
            side = 'SELL'
            confidence = min(abs(combined_score), 1.0)
        else:
            side = 'BUY' if combined_score > 0 else 'SELL'
            confidence = abs(combined_score)

        reason = (f"Ensemble: Momentum {momentum_result.confidence:.1%}, "
                  f"ML {ml_result.confidence:.1%}")

        return SignalResult(
            side, confidence, reason, 'ensemble',
            {
                'momentum': {
                    'side': momentum_result.side,
                    'confidence': momentum_result.confidence,
                },
                'ml': {
                    'side': ml_result.side,
                    'confidence': ml_result.confidence,
                }
            }
        )

# ======================
# 📊 Example Usage
# ======================

if __name__ == '__main__':
    # Example candles
    example_candles = [
        {'time': 1000 * i, 'open': 100 + i*0.1, 'high': 101 + i*0.1,
         'low': 99 + i*0.1, 'close': 100.5 + i*0.1}
        for i in range(100)
    ]

    print("📈 ML Signals Test\n")

    # Test momentum
    print("1️⃣  Momentum Signal:")
    momentum_gen = MomentumSignalGenerator()
    result = momentum_gen.calculate_score(example_candles)
    print(f"   {result.side} @ {result.confidence:.1%} - {result.reason}\n")

    # Test ML (requires training)
    if HAS_ML:
        print("2️⃣  ML Signal (training):")
        ml_gen = MLSignalGenerator()
        train_result = ml_gen.train(example_candles)
        print(f"   {train_result}\n")

        print("3️⃣  ML Signal (inference):")
        result = ml_gen.score(example_candles)
        print(f"   {result.side} @ {result.confidence:.1%} - {result.reason}\n")

        print("4️⃣  Ensemble Signal:")
        ensemble = EnsembleSignalGenerator()
        result = ensemble.generate_signal(example_candles)
        print(f"   {result.side} @ {result.confidence:.1%} - {result.reason}")
    else:
        print("   ⚠️  scikit-learn not installed")
