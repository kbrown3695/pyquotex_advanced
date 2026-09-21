#!/usr/bin/env python3
"""
Feature extraction from Quotex data for bot training

Shows how to convert raw candle data into ML-ready features
"""

import numpy as np
import pandas as pd
from collections import deque
from datetime import datetime


class QuotexFeatureExtractor:
    """Extract ML features from Quotex candle data"""

    def __init__(self, lookback_period=50):
        """
        Args:
            lookback_period: Number of previous candles to use for indicators
        """
        self.lookback_period = lookback_period
        self.candles = deque(maxlen=lookback_period)

    def add_candle(self, timestamp, open_price, high, low, close, volume):
        """Add a new candle to the buffer"""
        self.candles.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        })

    def extract_price_features(self):
        """Extract technical indicator features from candles"""

        if len(self.candles) < 20:
            return None  # Need minimum data

        closes = np.array([c['close'] for c in self.candles])
        opens = np.array([c['open'] for c in self.candles])
        highs = np.array([c['high'] for c in self.candles])
        lows = np.array([c['low'] for c in self.candles])
        volumes = np.array([c['volume'] for c in self.candles])

        features = {}

        # === TREND INDICATORS ===
        features['SMA_10'] = self.simple_moving_average(closes, 10)
        features['SMA_20'] = self.simple_moving_average(closes, 20)
        features['EMA_12'] = self.exponential_moving_average(closes, 12)

        # Price above/below moving average
        features['price_above_SMA20'] = 1.0 if closes[-1] > features['SMA_20'] else 0.0
        features['SMA_10_above_SMA20'] = 1.0 if features['SMA_10'] > features['SMA_20'] else 0.0

        # === MOMENTUM INDICATORS ===
        features['RSI_14'] = self.calculate_rsi(closes, 14)

        # MACD
        macd, signal, histogram = self.calculate_macd(closes)
        features['MACD'] = macd
        features['MACD_Signal'] = signal
        features['MACD_Histogram'] = histogram

        # Rate of Change
        features['ROC_12'] = self.rate_of_change(closes, 12)

        # === VOLATILITY INDICATORS ===
        features['ATR_14'] = self.average_true_range(highs, lows, closes, 14)
        features['Bollinger_High'], features['Bollinger_Mid'], features['Bollinger_Low'] = \
            self.bollinger_bands(closes, 20, 2)

        # Standard deviation
        features['Std_Dev_20'] = np.std(closes[-20:])

        # === PRICE ACTION ===
        features['close_open_ratio'] = (closes[-1] - opens[-1]) / opens[-1]
        features['high_low_ratio'] = (highs[-1] - lows[-1]) / lows[-1]
        features['close_position'] = (closes[-1] - lows[-1]) / (highs[-1] - lows[-1])  # 0-1

        # Compare to previous candle
        features['higher_high'] = 1.0 if highs[-1] > highs[-2] else 0.0
        features['lower_low'] = 1.0 if lows[-1] < lows[-2] else 0.0
        features['close_above_open'] = 1.0 if closes[-1] > opens[-1] else 0.0

        # === VOLUME ===
        features['Volume_SMA_10'] = np.mean(volumes[-10:])
        features['Volume_Ratio'] = volumes[-1] / features['Volume_SMA_10'] if features['Volume_SMA_10'] > 0 else 1.0

        # === TREND STRENGTH ===
        features['consecutive_up'] = self.count_consecutive_up(closes)
        features['consecutive_down'] = self.count_consecutive_down(closes)

        return features

    def extract_account_features(self, account_balance, daily_limit, win_rate, trades_count):
        """Extract account/risk management features"""

        features = {}

        # Account state
        features['balance'] = account_balance
        features['daily_remaining'] = daily_limit
        features['account_utilization'] = 1.0 - (daily_limit / 1000.0) if daily_limit > 0 else 0

        # Risk metrics
        features['risk_per_trade'] = account_balance * 0.02  # Standard 2% risk
        features['account_heat'] = trades_count / 10.0  # How many trades in last hour?

        # Performance metrics
        features['win_rate'] = win_rate if win_rate >= 0 else 0.5  # Default 50% if unknown
        features['is_winning_streak'] = 1.0 if win_rate > 0.55 else 0.0

        return features

    def extract_context_features(self, timestamp):
        """Extract time/context features"""

        features = {}

        # Time features
        features['hour_of_day'] = timestamp.hour / 24.0  # 0-1
        features['day_of_week'] = timestamp.weekday() / 7.0  # 0-1
        features['day_of_month'] = timestamp.day / 31.0  # 0-1

        # Market session (roughly)
        hour = timestamp.hour
        if 7 <= hour < 12:
            features['market_session'] = 0  # Asian/European morning
        elif 12 <= hour < 17:
            features['market_session'] = 1  # European afternoon
        elif 17 <= hour < 22:
            features['market_session'] = 2  # US session
        else:
            features['market_session'] = 3  # Night/low volume

        # Trading hours (0 if outside, 1 if inside)
        features['is_high_volume_hours'] = 1.0 if 7 <= hour < 22 else 0.0

        return features

    def extract_all_features(self, account_balance, daily_limit, win_rate,
                            trades_count, timestamp):
        """Extract and combine all features"""

        price_features = self.extract_price_features()
        if price_features is None:
            return None

        account_features = self.extract_account_features(
            account_balance, daily_limit, win_rate, trades_count
        )

        context_features = self.extract_context_features(timestamp)

        # Combine all
        all_features = {**price_features, **account_features, **context_features}

        return all_features

    # ========== TECHNICAL INDICATOR IMPLEMENTATIONS ==========

    @staticmethod
    def simple_moving_average(prices, period):
        """Calculate SMA"""
        if len(prices) < period:
            return prices[-1]
        return np.mean(prices[-period:])

    @staticmethod
    def exponential_moving_average(prices, period):
        """Calculate EMA"""
        if len(prices) < period:
            return prices[-1]

        ema = [prices[0]]
        k = 2 / (period + 1)

        for price in prices[1:]:
            ema.append(price * k + ema[-1] * (1 - k))

        return ema[-1]

    @staticmethod
    def calculate_rsi(prices, period=14):
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return 50

        deltas = np.diff(prices[-period-1:])
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period

        rs = up / down if down != 0 else 0
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_macd(prices, fast=12, slow=26, signal=9):
        """Calculate MACD, Signal, Histogram"""
        if len(prices) < slow:
            return 0, 0, 0

        ema_fast = QuotexFeatureExtractor.exponential_moving_average(prices, fast)
        ema_slow = QuotexFeatureExtractor.exponential_moving_average(prices, slow)

        macd = ema_fast - ema_slow

        # Simplified signal line (just use another EMA)
        signal_line = (macd + 0) / 2  # Simplified for example

        histogram = macd - signal_line

        return macd, signal_line, histogram

    @staticmethod
    def rate_of_change(prices, period=12):
        """Calculate Rate of Change"""
        if len(prices) < period + 1:
            return 0

        roc = ((prices[-1] - prices[-period-1]) / prices[-period-1]) * 100
        return roc

    @staticmethod
    def average_true_range(highs, lows, closes, period=14):
        """Calculate Average True Range"""
        if len(closes) < period + 1:
            return highs[-1] - lows[-1]

        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)

        atr = np.mean(tr_list[-period:])
        return atr

    @staticmethod
    def bollinger_bands(prices, period=20, std_dev=2):
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return prices[-1], prices[-1], prices[-1]

        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])

        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)

        return upper, sma, lower

    @staticmethod
    def count_consecutive_up(prices):
        """Count consecutive up candles"""
        count = 0
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] > prices[i-1]:
                count += 1
            else:
                break
        return count

    @staticmethod
    def count_consecutive_down(prices):
        """Count consecutive down candles"""
        count = 0
        for i in range(len(prices) - 1, 0, -1):
            if prices[i] < prices[i-1]:
                count += 1
            else:
                break
        return count


# ========== EXAMPLE USAGE ==========

def example_feature_extraction():
    """Demonstrate feature extraction from Quotex data"""

    extractor = QuotexFeatureExtractor(lookback_period=50)

    # Simulate Quotex candle data (from wss_message)
    print("📊 EXTRACTING FEATURES FROM QUOTEX DATA\n")
    print("="*70)

    # Sample candles (timestamp, open, high, low, close, volume)
    sample_candles = [
        (1695830400, 1.0850, 1.0855, 1.0848, 1.0852, 1000),
        (1695830460, 1.0852, 1.0858, 1.0851, 1.0856, 1200),
        (1695830520, 1.0856, 1.0860, 1.0854, 1.0858, 950),
        (1695830580, 1.0858, 1.0862, 1.0856, 1.0860, 1100),
        (1695830640, 1.0860, 1.0865, 1.0859, 1.0863, 1300),
        # ... more candles would follow
    ]

    # Add some dummy data to build up history
    for i in range(50):
        base_price = 1.0850
        noise = np.random.randn() * 0.0005
        close = base_price + noise

        extractor.add_candle(
            timestamp=1695830400 + (i * 60),
            open_price=close - noise * 0.5,
            high=close + abs(noise),
            low=close - abs(noise),
            close=close,
            volume=1000 + np.random.randint(-200, 200)
        )

    # Extract features
    features = extractor.extract_all_features(
        account_balance=10000,
        daily_limit=1000,
        win_rate=0.58,
        trades_count=3,
        timestamp=datetime.now()
    )

    if features:
        print("✅ EXTRACTED FEATURES:\n")

        # Group by category
        categories = {
            'Price Trends': ['SMA_10', 'SMA_20', 'EMA_12', 'price_above_SMA20'],
            'Momentum': ['RSI_14', 'MACD', 'ROC_12'],
            'Volatility': ['ATR_14', 'Std_Dev_20', 'high_low_ratio'],
            'Account': ['balance', 'account_utilization', 'win_rate'],
            'Context': ['hour_of_day', 'market_session', 'is_high_volume_hours'],
        }

        for category, feature_names in categories.items():
            print(f"\n{category}:")
            for name in feature_names:
                if name in features:
                    value = features[name]
                    print(f"  {name:25} = {value:10.4f}")

        print("\n" + "="*70)
        print(f"Total features extracted: {len(features)}")

        # Show as DataFrame for ML
        print("\n📊 As Pandas DataFrame (ready for ML):")
        df = pd.DataFrame([features])
        print(df.to_string())

        return features
    else:
        print("⚠️ Not enough data to extract features (need at least 20 candles)")


if __name__ == "__main__":
    example_feature_extraction()
