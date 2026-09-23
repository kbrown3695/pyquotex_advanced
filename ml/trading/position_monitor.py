#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Position Monitor
================
Monitors open positions and closes them when expired.
Updates P&L when positions close.
Tracks binary option expiration and results.

Features:
- Monitor open positions for expiration
- Auto-close expired positions
- Fetch position results from broker
- Calculate and record P&L
- Track win/loss statistics
"""

import asyncio
import logging
import time
from typing import Dict, Optional, List
from datetime import datetime, timedelta


class PositionMonitor:
    """
    Monitors trading positions and updates P&L.

    Responsibilities:
    1. Track position expiration times
    2. Close expired positions
    3. Fetch results from broker
    4. Update P&L in position tracker
    5. Report statistics
    """

    def __init__(
        self,
        quotex_client: Optional[object] = None,
        position_tracker: Optional[object] = None,
        logger: Optional[logging.Logger] = None,
        check_interval: float = 5.0
    ):
        """Initialize position monitor.

        Args:
            quotex_client: Quotex API client
            position_tracker: PositionTracker instance
            logger: Optional logger
            check_interval: How often to check positions (seconds)
        """
        self.client = quotex_client
        self.position_tracker = position_tracker
        self.logger = logger or logging.getLogger(__name__)
        self.check_interval = check_interval

        # Position expiration tracking
        self.position_expirations: Dict[str, float] = {}  # position_id -> expiration_time
        self.position_assets: Dict[str, str] = {}  # position_id -> asset
        self.is_running = False
        self.monitor_task: Optional[asyncio.Task] = None

    def register_position(
        self,
        position_id: str,
        asset: str,
        duration_seconds: int = 300
    ) -> None:
        """Register a position for monitoring.

        Args:
            position_id: Unique position ID
            asset: Asset symbol
            duration_seconds: How long until position expires
        """
        expiration_time = time.time() + duration_seconds
        self.position_expirations[position_id] = expiration_time
        self.position_assets[position_id] = asset

        self.logger.info(
            f"⏱️  Position registered: {position_id} ({asset}) "
            f"expires in {duration_seconds}s"
        )

    async def start_monitoring(self) -> None:
        """Start background position monitoring."""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info("🔍 Position monitor started")

        try:
            while self.is_running:
                await self._check_positions()
                await asyncio.sleep(self.check_interval)
        except asyncio.CancelledError:
            self.logger.info("⏹️  Position monitor stopped")
            self.is_running = False

    def start(self) -> None:
        """Start monitoring in current event loop."""
        if self.is_running:
            return

        self.is_running = True
        self.logger.info("🔍 Position monitor started")
        self.monitor_task = asyncio.create_task(self.start_monitoring())

    def stop(self) -> None:
        """Stop monitoring."""
        self.is_running = False
        if self.monitor_task:
            self.monitor_task.cancel()
        self.logger.info("⏹️  Position monitor stopped")

    async def _check_positions(self) -> None:
        """Check all positions for expiration and close if needed."""
        current_time = time.time()
        expired_positions = []

        # Find expired positions
        for position_id, expiration_time in list(self.position_expirations.items()):
            if current_time >= expiration_time:
                expired_positions.append(position_id)

        # Close expired positions
        for position_id in expired_positions:
            await self._close_expired_position(position_id)

    async def _close_expired_position(self, position_id: str) -> None:
        """Close an expired position and update P&L.

        Args:
            position_id: Position to close
        """
        asset = self.position_assets.get(position_id)

        if not asset:
            self.logger.warning(f"Position {position_id} not found in tracking")
            return

        try:
            # Get current price (exit price)
            exit_price = await self._get_current_price(asset)

            if exit_price > 0 and self.position_tracker:
                # Close the position with calculated P&L
                closed_pos = self.position_tracker.close_position(
                    position_id=position_id,
                    asset=asset,
                    exit_price=exit_price,
                    exit_reason="EXPIRED"
                )

                if closed_pos:
                    self.logger.info(
                        f"✅ Position expired and closed: {position_id} "
                        f"P&L: {closed_pos.profit_loss_pct:+.2f}% "
                        f"(${closed_pos.profit_loss_usd:+.2f})"
                    )

                    # ✅ [NEW] Report trade outcome to ML training system (Phase G3 feedback)
                    try:
                        # Import here to avoid circular imports
                        from ml.serving.signal_service import MLSignalService

                        # Get signal info if available
                        signal_components = getattr(closed_pos, 'signal_components', {})
                        entry_price = getattr(closed_pos, 'entry_price', 0.0)

                        if signal_components and entry_price > 0:
                            # Report to online learning manager
                            trade_result = {
                                'profit': closed_pos.profit_loss_usd,
                                'profit_pct': closed_pos.profit_loss_pct,
                                'components': signal_components,
                                'side': closed_pos.side,
                                'entry': entry_price,
                                'exit': exit_price,
                                'asset': asset,
                                'timestamp': time.time(),
                            }

                            # Call report_trade_outcome through engine (available globally)
                            # This is set up in engine.py and wired to ML_SERVICE
                            try:
                                import sys
                                # Import from engine module
                                import importlib
                                engine_module = sys.modules.get('__main__')
                                if hasattr(engine_module, 'report_trade_outcome'):
                                    report_outcome = engine_module.report_trade_outcome
                                    report_outcome(
                                        profit=closed_pos.profit_loss_usd,
                                        components=signal_components,
                                        side=closed_pos.side,
                                        entry=entry_price,
                                        exit=exit_price
                                    )
                                    self.logger.info(f"📊 Trade outcome reported to ML learning system for {position_id}")
                            except Exception as feedback_err:
                                self.logger.debug(f"Could not report trade outcome: {feedback_err}")
                    except ImportError:
                        pass  # ML system not available, skip feedback

            # Remove from tracking
            del self.position_expirations[position_id]
            del self.position_assets[position_id]

        except Exception as e:
            self.logger.error(f"❌ Error closing position {position_id}: {e}")

    async def _get_current_price(self, asset: str) -> float:
        """Get current price for asset (exit price).

        Args:
            asset: Asset symbol

        Returns:
            Current price, or 0 if unavailable
        """
        if not self.client:
            return 0.0

        try:
            # Try to get from WebSocket real-time data
            if hasattr(self.client, 'api') and hasattr(self.client.api, 'instruments'):
                instruments = self.client.api.instruments
                if isinstance(instruments, dict) and asset in instruments:
                    instrument = instruments[asset]
                    if hasattr(instrument, 'current_price'):
                        return float(instrument.current_price)

            # Fallback: try get_realtime_price
            if hasattr(self.client, 'get_realtime_price'):
                try:
                    price = await asyncio.wait_for(
                        asyncio.create_task(
                            self.client.get_realtime_price(asset)
                        ),
                        timeout=2
                    )
                    return float(price) if price else 0.0
                except (asyncio.TimeoutError, Exception):
                    pass

            return 0.0

        except Exception as e:
            self.logger.error(f"Error getting price for {asset}: {e}")
            return 0.0

    def get_position_stats(self) -> Dict:
        """Get current position monitoring statistics.

        Returns:
            Dict with positions and stats
        """
        return {
            'monitored_positions': len(self.position_expirations),
            'position_list': list(self.position_expirations.keys()),
            'is_monitoring': self.is_running
        }

    def get_monitored_positions(self) -> List[Dict]:
        """Get details of all monitored positions.

        Returns:
            List of position details
        """
        current_time = time.time()
        positions = []

        for position_id, expiration_time in self.position_expirations.items():
            asset = self.position_assets.get(position_id, 'UNKNOWN')
            time_remaining = max(0, expiration_time - current_time)

            positions.append({
                'position_id': position_id,
                'asset': asset,
                'expiration_time': expiration_time,
                'time_remaining_sec': time_remaining,
                'is_expired': time_remaining <= 0
            })

        return positions
