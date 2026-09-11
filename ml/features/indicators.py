"""Technical indicator calculations for feature engineering."""

from typing import List, Tuple
import numpy as np


def sma(prices: List[float], period: int) -> List[float]:
    """Simple moving average."""
    if len(prices) < period:
        return [None] * len(prices)
    sma_vals = np.convolve(prices, np.ones(period) / period, mode='valid')
    return [None] * (period - 1) + list(sma_vals)


def ema(prices: List[float], period: int) -> List[float]:
    """Exponential moving average."""
    if len(prices) < 2:
        return prices
    ema_vals = [prices[0]]
    k = 2 / (period + 1)
    for price in prices[1:]:
        ema_vals.append(ema_vals[-1] * (1 - k) + price * k)
    return ema_vals


def rsi(prices: List[float], period: int = 14) -> List[float]:
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
        rsi_val = 100 - (100 / (1 + rs))
        rs_list.append(rsi_val)

    # Pad to match input length
    while len(rs_list) < len(prices):
        rs_list.append(None)

    return rs_list


def macd(prices: List[float]) -> Tuple[List[float], List[float], List[float]]:
    """MACD indicator: line, signal, histogram."""
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)

    macd_line = [e12 - e26 if e12 and e26 else None for e12, e26 in zip(ema12, ema26)]
    macd_signal = ema([m for m in macd_line if m is not None], 9)

    # Pad signal line to match length
    macd_signal = [None] * (len(macd_line) - len(macd_signal)) + macd_signal

    macd_hist = [m - s if m and s else None for m, s in zip(macd_line, macd_signal)]
    return macd_line, macd_signal, macd_hist


def atr(candles: List[dict], period: int = 14) -> List[float]:
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

    atr_vals = [None]
    atr_val = np.mean(trs[:period])
    for tr in trs[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
        atr_vals.append(atr_val)

    # Pad to match input candles length
    while len(atr_vals) < len(candles):
        atr_vals.append(None)

    return atr_vals


def bollinger_percent_b(prices: List[float], period: int = 20, num_std: float = 2.0) -> List[float]:
    """Bollinger Bands %B: (close - lower_band) / (upper_band - lower_band)."""
    if len(prices) < period:
        return [None] * len(prices)

    sma_vals = sma(prices, period)
    result = []

    for i in range(len(prices)):
        if sma_vals[i] is None:
            result.append(None)
            continue

        # Calculate rolling std for this window
        start = max(0, i - period + 1)
        window_prices = prices[start:i + 1]

        if len(window_prices) < period:
            result.append(None)
            continue

        std_dev = np.std(window_prices)
        upper_band = sma_vals[i] + num_std * std_dev
        lower_band = sma_vals[i] - num_std * std_dev

        if upper_band == lower_band:
            percent_b = 0.5
        else:
            percent_b = (prices[i] - lower_band) / (upper_band - lower_band)

        # Clip to [-1, 2] range as per dollar's convention
        percent_b = np.clip(percent_b, -1, 2)
        result.append(percent_b)

    return result
