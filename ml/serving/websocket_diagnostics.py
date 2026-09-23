#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Diagnostics & Recovery
==================================
Identifies why WebSocket is receiving empty ticks and recommends fixes.

Tracks:
- Subscription status per asset
- Message flow patterns
- Recovery attempts
- Broker connectivity issues
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from enum import Enum


class SubscriptionStatus(Enum):
    """Subscription state."""
    ACTIVE = "active"           # Actively receiving data
    STALE = "stale"             # Not receiving updates for >30s
    LOST = "lost"               # Subscription likely dropped
    RECOVERING = "recovering"   # Attempting to resubscribe
    UNKNOWN = "unknown"         # Not enough data


@dataclass
class SubscriptionMetric:
    """Track subscription health for one asset."""
    asset: str
    timeframe: str
    subscription_time: float
    last_data_time: float = 0.0
    messages_received: int = 0
    empty_messages: int = 0
    recovery_attempts: int = 0
    last_recovery_time: Optional[float] = None
    status: SubscriptionStatus = SubscriptionStatus.UNKNOWN

    def update_with_data(self, is_empty: bool = False) -> None:
        """Record a message received."""
        self.messages_received += 1
        if is_empty:
            self.empty_messages += 1
        else:
            self.last_data_time = time.time()
            self.status = SubscriptionStatus.ACTIVE

    def record_recovery(self) -> None:
        """Record that a recovery attempt was made."""
        self.recovery_attempts += 1
        self.last_recovery_time = time.time()
        self.status = SubscriptionStatus.RECOVERING

    def get_staleness_seconds(self) -> float:
        """Get how long since last data."""
        if self.last_data_time == 0:
            return time.time() - self.subscription_time
        return time.time() - self.last_data_time

    def get_empty_percent(self) -> float:
        """Get % of messages that were empty."""
        if self.messages_received == 0:
            return 0
        return (self.empty_messages / self.messages_received) * 100

    def diagnose_status(self) -> str:
        """Diagnose subscription health."""
        staleness = self.get_staleness_seconds()
        empty_pct = self.get_empty_percent()

        if staleness > 120:
            return f"LOST (no data for {staleness:.0f}s)"
        elif staleness > 30:
            return f"STALE ({staleness:.0f}s without updates)"
        elif empty_pct > 50:
            return f"FLOODING (50%+ empty, {self.empty_messages}/{self.messages_received} msgs)"
        elif self.recovery_attempts > 3:
            return f"UNSTABLE ({self.recovery_attempts} recovery attempts)"
        else:
            return f"HEALTHY ({self.get_empty_percent():.0f}% empty)"


class WebSocketDiagnostics:
    """
    Diagnose WebSocket connection issues.

    Identifies patterns in empty ticks and recommends recovery strategies.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize diagnostics.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.subscriptions: Dict[str, SubscriptionMetric] = {}
        self.broker_ping_times: List[float] = []
        self.connection_events: List[tuple] = []  # (timestamp, event_type, asset)
        self.last_diagnostic_log = 0.0

    def register_subscription(self, asset: str, timeframe: str = "1m") -> None:
        """Register a new WebSocket subscription.

        Args:
            asset: Asset symbol
            timeframe: Candle timeframe
        """
        key = f"{asset}_{timeframe}"
        if key not in self.subscriptions:
            self.subscriptions[key] = SubscriptionMetric(
                asset=asset,
                timeframe=timeframe,
                subscription_time=time.time()
            )
            self.logger.debug(f"Registered subscription: {key}")

    def record_message(self, asset: str, timeframe: str, is_empty: bool) -> None:
        """Record a WebSocket message.

        Args:
            asset: Asset symbol
            timeframe: Candle timeframe
            is_empty: True if message was empty/invalid
        """
        key = f"{asset}_{timeframe}"
        if key not in self.subscriptions:
            self.register_subscription(asset, timeframe)

        self.subscriptions[key].update_with_data(is_empty)

    def record_recovery_attempt(self, asset: str, timeframe: str) -> None:
        """Record that recovery was attempted.

        Args:
            asset: Asset symbol
            timeframe: Candle timeframe
        """
        key = f"{asset}_{timeframe}"
        if key not in self.subscriptions:
            self.register_subscription(asset, timeframe)

        self.subscriptions[key].record_recovery()
        self.connection_events.append((time.time(), "recovery_attempt", asset))

    def record_ping(self, latency_ms: float) -> None:
        """Record broker ping latency.

        Args:
            latency_ms: Ping round-trip time in milliseconds
        """
        self.broker_ping_times.append(latency_ms)
        if len(self.broker_ping_times) > 100:
            self.broker_ping_times.pop(0)

    def get_problematic_subscriptions(self) -> List[str]:
        """Get list of subscriptions with issues.

        Returns:
            List of problematic subscription keys
        """
        problematic = []
        for key, metric in self.subscriptions.items():
            staleness = metric.get_staleness_seconds()
            empty_pct = metric.get_empty_percent()

            # Criteria for "problematic"
            if staleness > 30 or empty_pct > 30 or metric.recovery_attempts > 2:
                problematic.append(key)

        return problematic

    def get_broker_health(self) -> Dict:
        """Analyze broker connectivity health.

        Returns:
            Dict with broker health indicators
        """
        if not self.broker_ping_times:
            return {"status": "unknown", "message": "No ping data yet"}

        avg_latency = sum(self.broker_ping_times) / len(self.broker_ping_times)
        max_latency = max(self.broker_ping_times)
        recent_latencies = self.broker_ping_times[-10:]
        avg_recent = sum(recent_latencies) / len(recent_latencies)

        if avg_latency > 5000:
            status = "critical"
            message = f"Broker latency very high: {avg_latency:.0f}ms"
        elif avg_recent > 2000:
            status = "degraded"
            message = f"Recent latency spikes: {avg_recent:.0f}ms"
        elif avg_latency > 1000:
            status = "warning"
            message = f"Elevated latency: {avg_latency:.0f}ms"
        else:
            status = "healthy"
            message = f"Normal latency: {avg_latency:.0f}ms"

        return {
            "status": status,
            "message": message,
            "avg_latency_ms": round(avg_latency, 1),
            "max_latency_ms": max_latency,
            "recent_avg_ms": round(avg_recent, 1)
        }

    def get_diagnostic_report(self) -> Dict:
        """Get comprehensive diagnostic report.

        Returns:
            Dict with all diagnostic information
        """
        problematic = self.get_problematic_subscriptions()
        broker_health = self.get_broker_health()

        subscription_details = {}
        for key, metric in self.subscriptions.items():
            subscription_details[key] = {
                "asset": metric.asset,
                "timeframe": metric.timeframe,
                "messages_received": metric.messages_received,
                "empty_messages": metric.empty_messages,
                "empty_percent": round(metric.get_empty_percent(), 1),
                "staleness_seconds": round(metric.get_staleness_seconds(), 1),
                "recovery_attempts": metric.recovery_attempts,
                "status": metric.status.value,
                "diagnosis": metric.diagnose_status()
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "total_subscriptions": len(self.subscriptions),
            "problematic_subscriptions": len(problematic),
            "problematic": problematic,
            "subscriptions": subscription_details,
            "broker_health": broker_health,
            "recommendations": self._get_recommendations(problematic, broker_health)
        }

    def _get_recommendations(self, problematic: List[str], broker_health: Dict) -> List[str]:
        """Generate recommendations based on diagnosis.

        Args:
            problematic: List of problematic subscriptions
            broker_health: Broker health report

        Returns:
            List of recommended actions
        """
        recommendations = []

        # Broker-level issues
        if broker_health.get("status") == "critical":
            recommendations.append("🔴 CRITICAL: Broker connection unstable. Check broker status page.")
            recommendations.append("    → Latency > 5s suggests broker API is down or overloaded")
            recommendations.append("    → Consider reducing # of subscriptions")
        elif broker_health.get("status") == "degraded":
            recommendations.append("🟡 Broker experiencing high latency. Consider pausing new trades.")

        # Subscription-level issues
        for key in problematic:
            metric = self.subscriptions[key]

            if metric.get_staleness_seconds() > 120:
                recommendations.append(
                    f"❌ {metric.asset} ({metric.timeframe}): Lost connection. "
                    f"Resubscribe or check if broker still supports this pair."
                )
            elif metric.get_empty_percent() > 70:
                recommendations.append(
                    f"⚠️  {metric.asset} ({metric.timeframe}): {metric.get_empty_percent():.0f}% empty messages. "
                    f"May indicate data format mismatch."
                )
            elif metric.recovery_attempts > 3:
                recommendations.append(
                    f"🔄 {metric.asset} ({metric.timeframe}): Multiple recovery attempts. "
                    f"Consider full reconnect instead of resubscription."
                )

        # Network-level fixes
        if len(problematic) == len(self.subscriptions):
            recommendations.append("🌐 All subscriptions problematic. Check network connectivity.")
            recommendations.append("    → Can you ping broker? `ping quotex.com` or check in browser")
            recommendations.append("    → Check firewall/proxy settings")

        if not recommendations:
            recommendations.append("✅ No issues detected. System healthy.")

        return recommendations

    def log_diagnostic(self, force: bool = False) -> None:
        """Log diagnostic information at intervals.

        Args:
            force: Force logging even if recently logged
        """
        now = time.time()
        if not force and (now - self.last_diagnostic_log) < 60:
            return  # Only log every 60s max

        report = self.get_diagnostic_report()

        # Log summary
        self.logger.info(
            f"📊 WebSocket Diagnostics: {report['total_subscriptions']} subscriptions, "
            f"{report['problematic_subscriptions']} problematic"
        )

        # Log problematic subscriptions
        for key in report['problematic']:
            metric = self.subscriptions[key]
            self.logger.warning(f"   ⚠️  {key}: {metric.diagnose_status()}")

        # Log broker health
        broker = report['broker_health']
        self.logger.info(f"   🌐 Broker: {broker['status'].upper()} - {broker['message']}")

        # Log recommendations
        if report['recommendations']:
            self.logger.info("📋 Recommendations:")
            for rec in report['recommendations'][:3]:  # Top 3 recommendations
                self.logger.info(f"   {rec}")

        self.last_diagnostic_log = now

    def export_diagnostic_report(self, filepath: str) -> None:
        """Export diagnostic report to JSON file.

        Args:
            filepath: Path to save report
        """
        import json

        report = self.get_diagnostic_report()

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Diagnostic report exported to {filepath}")


__all__ = ["WebSocketDiagnostics", "SubscriptionMetric", "SubscriptionStatus"]
