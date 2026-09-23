#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: Order Executor Engine
==============================
Executes actual trades via Quotex API.
Handles BUY/SELL order placement, tracking, and confirmation.

Features:
- Place BUY/SELL orders with Quotex client
- Track order execution results
- Log all trades for compliance
- Handle order failures gracefully
- Return execution status to caller
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Callable
from enum import Enum

from ml.config import settings


class OrderSide(Enum):
    """Trade direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    """Order execution status."""
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderResult:
    """Result of order execution."""
    order_id: Optional[str]
    asset: str
    side: str
    amount: float
    status: str
    timestamp: float
    message: str = ""
    execution_price: float = 0.0
    profit_loss: float = 0.0


class OrderExecutor:
    """
    Executes trades on Quotex platform.

    Responsibilities:
    1. Place BUY/SELL orders via API
    2. Handle order responses
    3. Track order results
    4. Log all executions
    """

    def __init__(
        self,
        quotex_client: Optional[object] = None,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize order executor.

        Args:
            quotex_client: Quotex API client instance
            logger: Optional logger instance
        """
        self.client = quotex_client
        self.logger = logger or logging.getLogger(__name__)

        # Order tracking
        self.orders_placed: int = 0
        self.orders_executed: int = 0
        self.orders_failed: int = 0
        self.total_traded: float = 0.0

        # Order history
        self.order_history: list = []
        self.MAX_HISTORY = 1000

    async def execute_buy_order(
        self,
        asset: str,
        amount: float,
        expiration_time: int = 300,
        signal_confidence: float = 0.0,
        direction: str = "call"
    ) -> OrderResult:
        """Execute a BUY order (CALL direction).

        Args:
            asset: Asset to buy (internal name like "CHFJPY")
            amount: Amount to trade in USD
            expiration_time: Expiration in seconds (default 5 min)
            signal_confidence: ML signal confidence (0-1)
            direction: Order direction - "call" for bullish (default), "put" for bearish

        Returns:
            OrderResult with execution details
        """
        if not self.client:
            return OrderResult(
                order_id=None,
                asset=asset,
                side="BUY",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message="No Quotex client configured"
            )

        self.orders_placed += 1
        try:
            self.logger.info(
                f"🔵 PLACING BUY ORDER: {asset} ${amount:.2f} "
                f"(confidence: {signal_confidence:.1%})"
            )

            # Place order via Quotex API
            result = await asyncio.wait_for(
                asyncio.create_task(
                    self._place_buy_order(asset, amount, expiration_time, direction)
                ),
                timeout=90
            )

            # FIX #1: Properly unpack tuple (success, response)
            success, response = result

            if not success:
                self.orders_failed += 1
                status = OrderStatus.FAILED.value
                message = str(response) if response else "Unknown broker error"
                order_id = None
            else:
                # FIX #2: Extract actual order ID from broker response
                if isinstance(response, dict) and response.get("id"):
                    order_id = str(response.get("id"))
                    self.orders_executed += 1
                    self.total_traded += amount
                    status = OrderStatus.EXECUTED.value
                    message = "Order executed successfully"
                else:
                    self.orders_failed += 1
                    status = OrderStatus.FAILED.value
                    message = "Broker response missing order ID"
                    order_id = None

            order_result = OrderResult(
                order_id=order_id,
                asset=asset,
                side="BUY",
                amount=amount,
                status=status,
                timestamp=time.time(),
                message=message,
                execution_price=0.0  # Updated when position closes
            )

            self._record_order(order_result)

            if status == OrderStatus.EXECUTED.value:
                self.logger.info(f"✅ BUY ORDER EXECUTED: {asset} ${amount:.2f} (ID: {order_id})")
            else:
                self.logger.warning(f"❌ BUY ORDER FAILED: {asset} - {message}")

            return order_result

        except asyncio.TimeoutError:
            self.orders_failed += 1
            self.logger.error(f"❌ BUY ORDER TIMEOUT: {asset}")
            return OrderResult(
                order_id=None,
                asset=asset,
                side="BUY",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message="Order placement timeout (>10s)"
            )

        except Exception as e:
            self.orders_failed += 1
            self.logger.error(f"❌ BUY ORDER ERROR: {asset} - {type(e).__name__}: {e}")
            return OrderResult(
                order_id=None,
                asset=asset,
                side="BUY",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message=f"Execution error: {str(e)}"
            )

    async def execute_sell_order(
        self,
        asset: str,
        amount: float,
        signal_confidence: float = 0.0
    ) -> OrderResult:
        """Execute a SELL order (closes open option).

        Args:
            asset: Asset to sell (internal name)
            amount: Amount to trade in USD
            signal_confidence: ML signal confidence (0-1)

        Returns:
            OrderResult with execution details
        """
        if not self.client:
            return OrderResult(
                order_id=None,
                asset=asset,
                side="SELL",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message="No Quotex client configured"
            )

        self.orders_placed += 1
        try:
            self.logger.info(
                f"🔴 PLACING SELL ORDER (CLOSE): {asset} ${amount:.2f} "
                f"(confidence: {signal_confidence:.1%})"
            )

            # Place order via Quotex API
            result = await asyncio.wait_for(
                asyncio.create_task(
                    self._place_sell_order(asset, amount)
                ),
                timeout=90
            )

            # FIX #1: Properly unpack tuple (success, response)
            success, response = result

            if not success:
                self.orders_failed += 1
                status = OrderStatus.FAILED.value
                message = str(response) if response else "Unknown broker error"
                order_id = None
            else:
                # FIX #2: Extract actual order ID from broker response
                if isinstance(response, dict) and response.get("id"):
                    order_id = str(response.get("id"))
                    self.orders_executed += 1
                    self.total_traded += amount
                    status = OrderStatus.EXECUTED.value
                    message = "Position closed successfully"
                else:
                    self.orders_failed += 1
                    status = OrderStatus.FAILED.value
                    message = "Broker response missing order ID"
                    order_id = None

            order_result = OrderResult(
                order_id=order_id,
                asset=asset,
                side="SELL",
                amount=amount,
                status=status,
                timestamp=time.time(),
                message=message,
                execution_price=0.0
            )

            self._record_order(order_result)

            if status == OrderStatus.EXECUTED.value:
                self.logger.info(f"✅ SELL ORDER EXECUTED: {asset} ${amount:.2f} (ID: {order_id})")
            else:
                self.logger.warning(f"❌ SELL ORDER FAILED: {asset} - {message}")

            return order_result

        except asyncio.TimeoutError:
            self.orders_failed += 1
            self.logger.error(f"❌ SELL ORDER TIMEOUT: {asset}")
            return OrderResult(
                order_id=None,
                asset=asset,
                side="SELL",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message="Order placement timeout (>10s)"
            )

        except Exception as e:
            self.orders_failed += 1
            self.logger.error(f"❌ SELL ORDER ERROR: {asset} - {type(e).__name__}: {e}")
            return OrderResult(
                order_id=None,
                asset=asset,
                side="SELL",
                amount=amount,
                status=OrderStatus.FAILED.value,
                timestamp=time.time(),
                message=f"Execution error: {str(e)}"
            )

    def _to_internal_asset(self, display_name: str) -> str:
        """Convert display name to internal Quotex symbol.

        Examples:
            "EUR/USD (OTC)" → "EURUSD_otc"
            "AUD/CAD (OTC)" → "AUDCAD_otc"
        """
        if not display_name:
            return display_name
        return display_name.replace(" (OTC)", "_otc").replace("/", "").replace(" ", "")

    async def _place_buy_order(self, asset: str, amount: float, duration: int, direction: str = "call"):
        """Internal: Place BUY order via Quotex API.

        Args:
            asset: Asset symbol (display name like "EUR/USD (OTC)")
            amount: Trade amount
            duration: Expiration in seconds
            direction: Order direction "call" or "put"

        Returns:
            Tuple: (success: bool, response: dict|error_string)
        """
        try:
            # Convert "EUR/USD (OTC)" → "EURUSD_otc" for Quotex API
            internal_asset = self._to_internal_asset(asset)
            self.logger.info(f"   → Placing order: {asset} → {internal_asset}")

            result = await self.client.buy(
                amount=amount,
                asset=internal_asset,
                direction=direction,
                duration=duration,
                time_mode="TIME"
            )
            return result
        except Exception as e:
            self.logger.error(f"API BUY error: {type(e).__name__}: {e}")
            return (False, f"API Error: {str(e)}")

    async def _place_sell_order(self, asset: str, amount: float):
        """Internal: Place SELL order (close position) via Quotex API.

        Args:
            asset: Asset symbol
            amount: Trade amount

        Returns:
            Tuple: (success: bool, response: dict|error_string)
        """
        try:
            # Call Quotex API: client.sell_option()
            # Note: Quotex sell_option() closes the last open position
            result = await self.client.sell_option()
            return result
        except Exception as e:
            self.logger.error(f"API SELL error: {type(e).__name__}: {e}")
            return (False, f"API Error: {str(e)}")

    def _record_order(self, order_result: OrderResult) -> None:
        """Record order in history for tracking.

        Args:
            order_result: Order execution result
        """
        self.order_history.append({
            'timestamp': order_result.timestamp,
            'asset': order_result.asset,
            'side': order_result.side,
            'amount': order_result.amount,
            'status': order_result.status,
            'order_id': order_result.order_id,
            'message': order_result.message
        })

        # Keep history size bounded
        if len(self.order_history) > self.MAX_HISTORY:
            self.order_history.pop(0)

    def get_execution_stats(self) -> Dict:
        """Get order execution statistics.

        Returns:
            Dict with execution metrics
        """
        execution_rate = (
            (self.orders_executed / self.orders_placed * 100)
            if self.orders_placed > 0 else 0
        )

        return {
            'orders_placed': self.orders_placed,
            'orders_executed': self.orders_executed,
            'orders_failed': self.orders_failed,
            'execution_rate_percent': execution_rate,
            'total_traded_usd': self.total_traded,
            'avg_order_size': (
                self.total_traded / self.orders_executed
                if self.orders_executed > 0 else 0
            )
        }

    def get_recent_orders(self, limit: int = 10) -> list:
        """Get recent orders.

        Args:
            limit: Number of recent orders to return

        Returns:
            List of recent order records
        """
        return self.order_history[-limit:]

    def export_order_log(self, filepath: str) -> None:
        """Export order history to file.

        Args:
            filepath: Path to save order log
        """
        import json
        from datetime import datetime

        export = {
            'exported_at': datetime.now().isoformat(),
            'statistics': self.get_execution_stats(),
            'orders': self.order_history
        }

        with open(filepath, 'w') as f:
            json.dump(export, f, indent=2)

        self.logger.info(f"Order log exported to {filepath}")
