#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: Automated Trading Manager
===================================
Bridges constraint tracker, health monitor, and automated trader.
Handles:
- Loading selected pairs from JSON
- Registering pairs with health monitor
- Coordinating signal generation for selected pairs
- Real-time balance updates to frontend
- Trade execution with constraint enforcement
"""

import json
import logging
import time
from typing import List, Dict, Optional, Callable
from pathlib import Path
from dataclasses import dataclass

from ml.trading.account_constraint_tracker import AccountConstraintTracker
from ml.serving.websocket_health_monitor import WebSocketHealthMonitor, ConnectionHealth
from ml.trading.automated_trader import AutomatedTrader, TradeSignal
from ml.config import settings


@dataclass
class TradingPairStatus:
    """Status of a single trading pair."""
    display_name: str  # e.g., "CHF/JPY"
    internal_name: str  # e.g., "CHFJPY" or "CHFJPY_otc"
    is_active: bool
    last_signal_time: float = 0.0
    last_signal_confidence: float = 0.0
    signals_today: int = 0
    trades_executed: int = 0


class AutoTradingManager:
    """
    Manages automated trading for selected pairs.

    Responsibilities:
    1. Load selected pairs from JSON
    2. Register pairs with health monitor
    3. Coordinate signal generation for these pairs
    4. Execute trades with constraint enforcement
    5. Provide real-time status to frontend
    """

    def __init__(
        self,
        constraint_tracker: AccountConstraintTracker,
        health_monitor: WebSocketHealthMonitor,
        automated_trader: AutomatedTrader,
        pairs_file: str = "selected_signal_pairs.json",
        logger: Optional[logging.Logger] = None
    ):
        """Initialize auto trading manager.

        Args:
            constraint_tracker: Constraint enforcement
            health_monitor: Data quality monitoring
            automated_trader: Trade execution
            pairs_file: Path to selected pairs JSON
            logger: Optional logger instance
        """
        self.constraint_tracker = constraint_tracker
        self.health_monitor = health_monitor
        self.automated_trader = automated_trader
        self.pairs_file = pairs_file
        self.logger = logger or logging.getLogger(__name__)

        # Pair management
        self.selected_pairs: List[str] = []  # Display names from JSON
        self.pair_status: Dict[str, TradingPairStatus] = {}
        self.internal_pair_map: Dict[str, str] = {}  # display -> internal mapping

        # Automation state
        self.is_enabled: bool = False
        self.start_time: float = time.time()

        # Load pairs on init
        self.load_selected_pairs()

    def load_selected_pairs(self) -> bool:
        """Load selected pairs from JSON file.

        Returns:
            True if successfully loaded
        """
        try:
            if not Path(self.pairs_file).exists():
                self.logger.warning(f"Pairs file not found: {self.pairs_file}")
                return False

            with open(self.pairs_file, 'r') as f:
                self.selected_pairs = json.load(f)

            if not isinstance(self.selected_pairs, list):
                self.logger.error("Pairs file must contain a JSON list")
                return False

            self.logger.info(f"✅ Loaded {len(self.selected_pairs)} trading pairs:")
            for pair in self.selected_pairs:
                self.logger.info(f"   - {pair}")

            return True

        except Exception as e:
            self.logger.error(f"Failed to load pairs: {e}")
            return False

    def register_pairs_with_health_monitor(self, timeframes: List[int] = [60]) -> None:
        """Register selected pairs with health monitor.

        Args:
            timeframes: List of candle periods in seconds (default: 60s only)
        """
        if not self.selected_pairs:
            self.logger.warning("No pairs loaded for health monitoring")
            return

        for display_name in self.selected_pairs:
            for period in timeframes:
                # Health monitor tracks by display name and period
                self.health_monitor.register_subscription(display_name, period)

                # Initialize status tracking
                if display_name not in self.pair_status:
                    self.pair_status[display_name] = TradingPairStatus(
                        display_name=display_name,
                        internal_name=self._get_internal_name(display_name),
                        is_active=True
                    )

        self.logger.info(f"✅ Registered {len(self.selected_pairs)} pairs with health monitor")

    def _get_internal_name(self, display_name: str) -> str:
        """Convert display name to internal symbol.

        Examples:
            "EUR/USD (OTC)" -> "EURUSD_otc"
            "CHF/JPY" -> "CHFJPY"
        """
        # Remove (OTC) suffix and slashes
        internal = display_name.replace(" (OTC)", "_otc").replace("/", "")
        return internal

    def enable_automation(self) -> bool:
        """Enable automated trading for selected pairs.

        Returns:
            True if successfully enabled
        """
        if not self.selected_pairs:
            self.logger.error("Cannot enable automation: no pairs loaded")
            return False

        if not settings.enable_automated_trading:
            self.logger.warning("Automated trading disabled in settings")
            return False

        # Register pairs with health monitor
        self.register_pairs_with_health_monitor(timeframes=[60])

        # Enable in automated trader
        self.is_enabled = True
        self.logger.info(f"🚀 Automated trading ENABLED for {len(self.selected_pairs)} pairs")

        return True

    def disable_automation(self) -> None:
        """Disable automated trading."""
        self.is_enabled = False
        self.logger.info("⏹️  Automated trading DISABLED")

    def activate_pair(self, pair_name: str) -> bool:
        """Activate a specific pair for trading.

        Args:
            pair_name: Display name of pair (e.g., "CHF/JPY")

        Returns:
            True if successfully activated
        """
        if pair_name not in self.pair_status:
            self.logger.warning(f"Pair not found: {pair_name}")
            return False

        self.pair_status[pair_name].is_active = True
        self.logger.info(f"✅ PAIR ACTIVATED: {pair_name}")
        return True

    def deactivate_pair(self, pair_name: str) -> bool:
        """Deactivate a specific pair (won't execute trades).

        Args:
            pair_name: Display name of pair (e.g., "CHF/JPY")

        Returns:
            True if successfully deactivated
        """
        if pair_name not in self.pair_status:
            self.logger.warning(f"Pair not found: {pair_name}")
            return False

        self.pair_status[pair_name].is_active = False
        self.logger.info(f"⏸️  PAIR DEACTIVATED: {pair_name}")
        return True

    def activate_all_pairs(self) -> int:
        """Activate all selected pairs.

        Returns:
            Number of pairs activated
        """
        count = 0
        for pair_name in self.pair_status:
            self.pair_status[pair_name].is_active = True
            count += 1

        self.logger.info(f"✅ Activated all {count} pairs")
        return count

    def deactivate_all_pairs(self) -> int:
        """Deactivate all selected pairs.

        Returns:
            Number of pairs deactivated
        """
        count = 0
        for pair_name in self.pair_status:
            self.pair_status[pair_name].is_active = False
            count += 1

        self.logger.info(f"⏸️  Deactivated all {count} pairs")
        return count

    def is_pair_active(self, pair_name: str) -> bool:
        """Check if a pair is active for trading.

        Args:
            pair_name: Display name of pair

        Returns:
            True if pair is active
        """
        if pair_name not in self.pair_status:
            return False
        return self.pair_status[pair_name].is_active

    def get_active_pairs(self) -> List[str]:
        """Get list of currently active pairs.

        Returns:
            List of active pair names
        """
        return [
            name for name, status in self.pair_status.items()
            if status.is_active
        ]

    def get_inactive_pairs(self) -> List[str]:
        """Get list of currently inactive pairs.

        Returns:
            List of inactive pair names
        """
        return [
            name for name, status in self.pair_status.items()
            if not status.is_active
        ]

    async def process_signal(self, signal: TradeSignal) -> Dict:
        """Process a trade signal for selected pairs only.

        Args:
            signal: Trade signal from ML model

        Returns:
            Dict with execution result
        """
        # Check if automation enabled
        if not self.is_enabled:
            return {
                'executed': False,
                'reason': 'Automation disabled',
                'asset': signal.asset
            }

        # Check if this asset is in selected pairs
        if signal.asset not in self.selected_pairs:
            return {
                'executed': False,
                'reason': f'Asset {signal.asset} not in selected pairs',
                'asset': signal.asset
            }

        # Check if this pair is currently active (NEW)
        if not self.is_pair_active(signal.asset):
            return {
                'executed': False,
                'reason': f'Pair {signal.asset} is currently deactivated',
                'asset': signal.asset,
                'deactivated': True
            }

        # Update pair tracking
        if signal.asset in self.pair_status:
            self.pair_status[signal.asset].last_signal_time = signal.timestamp
            self.pair_status[signal.asset].last_signal_confidence = signal.confidence
            self.pair_status[signal.asset].signals_today += 1

        # Process through automated trader (BUG FIX #13: Actually execute the signal)
        result = await self.automated_trader.process_signal(signal)

        # Track if trade was executed
        if result.get('executed'):
            self.record_executed_trade(
                asset=signal.asset,
                side=signal.side,
                amount=result['trade'].amount if result.get('trade') else 0.0
            )

        return result

    def record_executed_trade(self, asset: str, side: str, amount: float) -> None:
        """Record a successfully executed trade.

        Args:
            asset: Asset traded
            side: BUY or SELL
            amount: Trade amount in dollars
        """
        if asset in self.pair_status:
            self.pair_status[asset].trades_executed += 1

        # Update constraint tracker
        self.constraint_tracker.record_trade(amount)

    def get_automation_status(self) -> Dict:
        """Get current automation status.

        Returns:
            Dict with complete automation state
        """
        uptime_sec = time.time() - self.start_time
        uptime_min = uptime_sec / 60

        total_signals = sum(p.signals_today for p in self.pair_status.values())
        total_trades = sum(p.trades_executed for p in self.pair_status.values())

        # Get constraint status (don't fail if this errors)
        constraints = {}
        try:
            constraints = self.constraint_tracker.get_status()
        except Exception as e:
            self.logger.warning(f"Could not get constraint status: {e}")

        # Get health status (don't fail if this errors)
        health_data = {
            'status': 'UNKNOWN',
            'latency_ms': 0,
            'stale_assets': [],
            'uptime_percent': 0,
            'alerts': []
        }
        try:
            health = self.health_monitor.get_health_status()
            health_data = {
                'status': health.connection_health,
                'latency_ms': health.message_latency_ms,
                'stale_assets': health.stale_assets,
                'uptime_percent': health.estimated_uptime_percent,
                'alerts': health.alerts
            }
        except Exception as e:
            self.logger.warning(f"Could not get health status: {e}")

        return {
            'enabled': self.is_enabled,
            'uptime_minutes': uptime_min,
            'pairs': {
                'selected': len(self.selected_pairs),
                'active': sum(1 for p in self.pair_status.values() if p.is_active),
                'list': self.selected_pairs
            },
            'signals': {
                'today': total_signals,
                'by_pair': {
                    asset: p.signals_today
                    for asset, p in self.pair_status.items()
                }
            },
            'trades': {
                'today': total_trades,
                'by_pair': {
                    asset: p.trades_executed
                    for asset, p in self.pair_status.items()
                }
            },
            'constraints': constraints,
            'health': health_data
        }

    def get_pair_statuses(self) -> Dict[str, Dict]:
        """Get status of each selected pair.

        Returns:
            Dict mapping asset names to status dicts
        """
        result = {}
        for asset, status in self.pair_status.items():
            result[asset] = {
                'display_name': status.display_name,
                'internal_name': status.internal_name,
                'is_active': status.is_active,
                'last_signal': {
                    'time': status.last_signal_time,
                    'confidence': status.last_signal_confidence
                },
                'signals_today': status.signals_today,
                'trades_today': status.trades_executed
            }
        return result

    def should_accept_signal_for_asset(self, asset: str) -> bool:
        """Check if we should process signals for this asset.

        Args:
            asset: Asset symbol (display name)

        Returns:
            True if:
            - Automation is enabled
            - Asset is in selected pairs
            - Asset is currently active (not deactivated)
        """
        if not self.is_enabled:
            return False

        if asset not in self.selected_pairs:
            return False

        # Check if pair is specifically activated
        if not self.is_pair_active(asset):
            return False

        return True

    def export_trading_session(self, filepath: str) -> None:
        """Export complete trading session report.

        Args:
            filepath: Path to save report
        """
        import json
        from datetime import datetime

        report = {
            'exported_at': datetime.now().isoformat(),
            'uptime_seconds': time.time() - self.start_time,
            'automation': {
                'enabled': self.is_enabled,
                'pairs_count': len(self.selected_pairs),
                'pairs': self.selected_pairs
            },
            'performance': {
                'total_signals': sum(p.signals_today for p in self.pair_status.values()),
                'total_trades': sum(p.trades_executed for p in self.pair_status.values()),
                'pair_details': self.get_pair_statuses()
            },
            'status': self.get_automation_status()
        }

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

        self.logger.info(f"Trading session exported to {filepath}")
