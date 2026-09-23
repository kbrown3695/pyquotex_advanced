#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: WebSocket Health Monitor
==================================
Monitors WebSocket connection quality and data freshness.
Detects stale candles, connection issues, and message latency problems.

Features:
- Real-time message latency tracking
- Stale candle detection (missing expected updates)
- Connection state monitoring
- Data quality alerts
- Automatic reconnection recommendations
"""

import time
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple, Set
from enum import Enum
from collections import defaultdict


class ConnectionHealth(Enum):
    """WebSocket connection health status."""
    EXCELLENT = "EXCELLENT"  # Latency < 100ms, no stale data
    GOOD = "GOOD"             # Latency < 500ms, occasional staleness
    DEGRADED = "DEGRADED"     # Latency > 500ms or frequent staleness
    CRITICAL = "CRITICAL"     # Frequent disconnects, very stale data
    UNKNOWN = "UNKNOWN"        # Not enough data


@dataclass
class CandleHealthMetric:
    """Health metric for a specific candle/asset/period."""
    asset: str
    period: int
    last_update_time: float
    expected_update_interval: float  # Period in seconds
    updates_received: int = 0
    stale_count: int = 0
    update_latency_ms: float = 0.0

    def is_stale(self, current_time: float, staleness_threshold: float = 1.5) -> bool:
        """Check if candle data is stale.

        Args:
            current_time: Current timestamp
            staleness_threshold: Multiple of expected interval (1.5 = 50% late)

        Returns:
            True if data is stale
        """
        time_since_update = current_time - self.last_update_time
        stale_threshold = self.expected_update_interval * staleness_threshold
        return time_since_update > stale_threshold

    def get_staleness_percent(self, current_time: float) -> float:
        """Get how stale the data is as percentage of expected interval."""
        time_since_update = current_time - self.last_update_time
        percent = (time_since_update / self.expected_update_interval) * 100
        return min(percent, 999.0)  # Cap at 999%


@dataclass
class HealthSnapshot:
    """Snapshot of overall WebSocket health."""
    timestamp: float
    connection_health: str
    message_latency_ms: float
    stale_assets: int
    total_subscribed: int
    consecutive_stale_events: int
    avg_staleness_percent: float
    last_message_received: float
    estimated_uptime_percent: float
    alerts: list  # List of alert messages


class WebSocketHealthMonitor:
    """
    Monitors WebSocket connection and data quality.

    Tracks:
    - Individual candle freshness per asset/period
    - Overall message latency
    - Connection stability
    - Data quality issues
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize health monitor.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # Per-asset/period tracking
        self.candle_metrics: Dict[Tuple[str, int], CandleHealthMetric] = {}

        # Latency tracking
        self.message_latencies: list = []  # Rolling window of latencies
        self.MAX_LATENCY_HISTORY = 100

        # Connection tracking
        self.last_message_time: float = time.time()
        self.connection_open_time: float = time.time()
        self.connection_interruptions: int = 0
        self.consecutive_stale_events: int = 0

        # Thresholds for alerts
        self.LATENCY_WARNING_MS = 500
        self.LATENCY_CRITICAL_MS = 1000
        self.STALE_ASSETS_WARNING = 2

        # Active alerts
        self.active_alerts: Set[str] = set()

    def register_subscription(self, asset: str, period: int) -> None:
        """Register a new candle subscription.

        Args:
            asset: Asset symbol (e.g., 'EURUSD_otc')
            period: Candle period in seconds (60, 300, etc.)
        """
        key = (asset, period)
        if key not in self.candle_metrics:
            self.candle_metrics[key] = CandleHealthMetric(
                asset=asset,
                period=period,
                last_update_time=time.time(),
                expected_update_interval=float(period)
            )
            self.logger.debug(f"Registered subscription: {asset} {period}s")

    def record_candle_update(self, asset: str, period: int, latency_ms: float = 0.0) -> None:
        """Record a candle update from WebSocket.

        Args:
            asset: Asset symbol
            period: Candle period in seconds
            latency_ms: Message latency in milliseconds
        """
        key = (asset, period)
        if key not in self.candle_metrics:
            self.register_subscription(asset, period)

        metric = self.candle_metrics[key]
        current_time = time.time()

        # Check if was stale before this update
        was_stale = metric.is_stale(current_time)
        if was_stale:
            metric.stale_count += 1
            self.consecutive_stale_events += 1
        else:
            self.consecutive_stale_events = 0

        # Update metrics
        metric.last_update_time = current_time
        metric.updates_received += 1
        metric.update_latency_ms = latency_ms

        # Track latency
        self.message_latencies.append(latency_ms)
        if len(self.message_latencies) > self.MAX_LATENCY_HISTORY:
            self.message_latencies.pop(0)

        self.last_message_time = current_time

    def get_health_status(self) -> HealthSnapshot:
        """Get overall health status snapshot.

        Returns:
            HealthSnapshot with current health metrics
        """
        current_time = time.time()

        # Calculate stale count
        stale_count = sum(
            1 for metric in self.candle_metrics.values()
            if metric.is_stale(current_time)
        )

        # Calculate average latency
        avg_latency = sum(self.message_latencies) / len(self.message_latencies) if self.message_latencies else 0

        # Calculate average staleness
        staleness_values = []
        for metric in self.candle_metrics.values():
            staleness_values.append(metric.get_staleness_percent(current_time))
        avg_staleness = sum(staleness_values) / len(staleness_values) if staleness_values else 0

        # Determine overall health
        health = self._determine_health(avg_latency, stale_count, self.consecutive_stale_events)

        # Generate alerts
        alerts = self._generate_alerts(avg_latency, stale_count)

        # Estimate uptime
        uptime_percent = self._calculate_uptime()

        return HealthSnapshot(
            timestamp=current_time,
            connection_health=health.value,
            message_latency_ms=avg_latency,
            stale_assets=stale_count,
            total_subscribed=len(self.candle_metrics),
            consecutive_stale_events=self.consecutive_stale_events,
            avg_staleness_percent=avg_staleness,
            last_message_received=current_time - self.last_message_time,
            estimated_uptime_percent=uptime_percent,
            alerts=alerts
        )

    def _determine_health(self, avg_latency: float, stale_count: int, consecutive_stale: int) -> ConnectionHealth:
        """Determine overall connection health.

        Args:
            avg_latency: Average message latency in milliseconds
            stale_count: Number of stale asset/period combinations
            consecutive_stale: Consecutive stale events count

        Returns:
            ConnectionHealth status
        """
        if not self.candle_metrics:
            return ConnectionHealth.UNKNOWN

        total = len(self.candle_metrics)
        stale_percent = (stale_count / total * 100) if total > 0 else 0

        # FIXED: More lenient CRITICAL threshold to reduce false positives
        # Only mark CRITICAL if very bad conditions persist
        if avg_latency > self.LATENCY_CRITICAL_MS or stale_percent > 75 or consecutive_stale > 20:
            return ConnectionHealth.CRITICAL

        # Degraded conditions: temporary staleness is ok
        if avg_latency > self.LATENCY_WARNING_MS or stale_percent > 40:
            return ConnectionHealth.DEGRADED

        # Good conditions: most assets fresh
        if avg_latency < 100 and stale_count == 0:
            return ConnectionHealth.EXCELLENT

        return ConnectionHealth.GOOD

    def _generate_alerts(self, avg_latency: float, stale_count: int) -> list:
        """Generate alert messages based on current conditions.

        Args:
            avg_latency: Average message latency
            stale_count: Number of stale subscriptions

        Returns:
            List of alert messages
        """
        alerts = []

        # Latency alert
        if avg_latency > self.LATENCY_CRITICAL_MS:
            alerts.append(f"🔴 CRITICAL: Latency {avg_latency:.0f}ms (>1000ms)")
            self.active_alerts.add("high_latency")
        elif avg_latency > self.LATENCY_WARNING_MS:
            alerts.append(f"🟡 WARNING: High latency {avg_latency:.0f}ms (>500ms)")
            self.active_alerts.add("high_latency")
        else:
            self.active_alerts.discard("high_latency")

        # Stale data alert
        if stale_count > 0:
            percent = (stale_count / len(self.candle_metrics) * 100) if self.candle_metrics else 0
            alerts.append(f"🟡 WARNING: {stale_count}/{len(self.candle_metrics)} assets stale ({percent:.0f}%)")
            self.active_alerts.add("stale_data")
        else:
            self.active_alerts.discard("stale_data")

        # Consecutive stale events
        if self.consecutive_stale_events > 5:
            alerts.append(f"🟠 ALERT: {self.consecutive_stale_events} consecutive stale events")
            self.active_alerts.add("consecutive_stale")
        else:
            self.active_alerts.discard("consecutive_stale")

        # Connection interruption
        if self.connection_interruptions > 5:
            alerts.append(f"🔴 CRITICAL: {self.connection_interruptions} reconnections")
            self.active_alerts.add("reconnections")

        return alerts

    def _calculate_uptime(self) -> float:
        """Calculate estimated uptime percentage.

        Returns:
            Uptime percentage (0-100)
        """
        if not self.candle_metrics:
            return 100.0

        # Based on stale events and interruptions
        total_subscriptions = len(self.candle_metrics)
        total_stale_events = sum(m.stale_count for m in self.candle_metrics.values())

        # Simple calculation: penalize for stale events and reconnects
        penalty = (total_stale_events * 0.1) + (self.connection_interruptions * 5)
        uptime = max(0, 100 - penalty)

        return min(uptime, 100.0)

    def check_data_quality(self, min_health: ConnectionHealth = ConnectionHealth.GOOD) -> Tuple[bool, str]:
        """Check if data quality is acceptable for trading.

        Args:
            min_health: Minimum health level required

        Returns:
            Tuple of (data_ok: bool, reason: str)
        """
        health = self.get_health_status()
        current_health = ConnectionHealth[health.connection_health]

        # Map health to numeric value
        health_levels = {
            ConnectionHealth.EXCELLENT: 4,
            ConnectionHealth.GOOD: 3,
            ConnectionHealth.DEGRADED: 2,
            ConnectionHealth.CRITICAL: 1,
            ConnectionHealth.UNKNOWN: 0
        }

        current_level = health_levels.get(current_health, 0)
        min_level = health_levels.get(min_health, 3)

        if current_level < min_level:
            reason = f"Data quality {current_health.value} below required {min_health.value}"
            return False, reason

        return True, "Data quality acceptable"

    def record_disconnection(self) -> None:
        """Record a WebSocket disconnection event."""
        self.connection_interruptions += 1
        self.consecutive_stale_events = 0
        self.logger.warning(f"Disconnection recorded (total: {self.connection_interruptions})")

    def get_detailed_status(self) -> Dict:
        """Get detailed health status for logging/debugging.

        Returns:
            Dictionary with complete health information
        """
        health = self.get_health_status()

        # Per-asset details
        asset_details = {}
        for (asset, period), metric in self.candle_metrics.items():
            key = f"{asset}_{period}s"
            asset_details[key] = {
                "updates": metric.updates_received,
                "stale_count": metric.stale_count,
                "latency_ms": metric.update_latency_ms,
                "staleness_percent": metric.get_staleness_percent(health.timestamp)
            }

        return {
            "timestamp": health.timestamp,
            "overall_health": health.connection_health,
            "avg_latency_ms": health.message_latency_ms,
            "stale_assets": health.stale_assets,
            "total_subscribed": health.total_subscribed,
            "uptime_percent": health.estimated_uptime_percent,
            "consecutive_stale_events": health.consecutive_stale_events,
            "reconnections": self.connection_interruptions,
            "active_alerts": list(self.active_alerts),
            "asset_details": asset_details,
            "alerts": health.alerts
        }

    def export_health_log(self, filepath: str) -> None:
        """Export health status to file for analysis.

        Args:
            filepath: Path to save health log
        """
        import json

        health = self.get_detailed_status()

        with open(filepath, 'w') as f:
            json.dump(health, f, indent=2)

        self.logger.info(f"Health log exported to {filepath}")
