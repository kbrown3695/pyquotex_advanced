#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: Automated Trader with Constraint Enforcement
=====================================================
Main automation loop that respects account constraints, WebSocket health,
and risk management rules. Designed for demo-mode testing first.

Features:
- Signal-based trade execution
- Real-time constraint checking
- Health monitoring before trades
- Position sizing based on available capital
- Compliance logging for all trades
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Dict, Callable
from datetime import datetime, time as dt_time

from ml.trading.account_constraint_tracker import AccountConstraintTracker, ConstraintStatus
from ml.serving.websocket_health_monitor import WebSocketHealthMonitor, ConnectionHealth
from ml.trading.order_executor import OrderExecutor
from ml.trading.position_tracker import PositionTracker
from ml.config import settings


@dataclass
class TradeSignal:
    """Trade signal from ML model."""
    asset: str
    side: str  # "BUY" or "SELL"
    confidence: float  # 0.0 to 1.0
    target_return: float  # Expected return %
    timestamp: float
    model_name: str = "Ensemble"


@dataclass
class ExecutedTrade:
    """Record of executed trade."""
    asset: str
    side: str
    amount: float
    timestamp: float
    order_id: Optional[str] = None
    execution_price: float = 0.0
    result: str = "PENDING"  # PENDING, WIN, LOSS


class AutomatedTrader:
    """
    Main automated trading engine with constraint enforcement.

    Responsibilities:
    1. Receive trade signals from ML models
    2. Check constraints before execution
    3. Validate WebSocket health
    4. Size positions safely
    5. Execute trades
    6. Log all activity for compliance
    """

    def __init__(
        self,
        constraint_tracker: AccountConstraintTracker,
        health_monitor: WebSocketHealthMonitor,
        order_executor: Optional[OrderExecutor] = None,
        position_tracker: Optional[PositionTracker] = None,
        trade_executor: Optional[Callable] = None,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize automated trader.

        Args:
            constraint_tracker: Account constraint tracker instance
            health_monitor: WebSocket health monitor instance
            order_executor: OrderExecutor for placing orders
            position_tracker: PositionTracker for tracking positions
            trade_executor: Legacy callable (for backwards compatibility)
            logger: Optional logger instance
        """
        self.constraint_tracker = constraint_tracker
        self.health_monitor = health_monitor
        self.order_executor = order_executor
        self.position_tracker = position_tracker or PositionTracker(logger)
        self.trade_executor = trade_executor
        self.logger = logger or logging.getLogger(__name__)

        # Trading state
        self.is_running: bool = False
        self.trades_executed: list = []
        self.rejected_signals: int = 0
        self.last_trade_time: float = 0.0

        # Configuration from settings
        self.min_time_between_trades = settings.min_time_between_trades_sec
        self.max_trades_per_day = settings.max_trades_per_day
        self.risk_per_trade_percent = settings.risk_per_trade_percent
        self.max_position_size_percent = settings.max_position_size_percent

        # Auto-trading hours
        self.automation_start_hour = settings.automation_start_hour
        self.automation_end_hour = settings.automation_end_hour

    async def start(self) -> None:
        """Start automated trading."""
        self.is_running = True
        self.logger.info("🚀 Automated trader started (DEMO MODE)")

    async def stop(self) -> None:
        """Stop automated trading."""
        self.is_running = False
        self.logger.info("⏹️  Automated trader stopped")

    async def process_signal(self, signal: TradeSignal) -> Dict:
        """Process and execute a trade signal if valid.

        Args:
            signal: TradeSignal from ML model

        Returns:
            Dict with execution result {
                'executed': bool,
                'reason': str,
                'trade': ExecutedTrade or None,
                'rejected_reason': str or None
            }
        """
        result = {
            'executed': False,
            'reason': '',
            'trade': None,
            'rejected_reason': None
        }

        # Check 1: Automated trading enabled
        if not settings.enable_automated_trading:
            result['rejected_reason'] = "Automated trading disabled in config"
            self.rejected_signals += 1
            return result

        # Check 2: Within trading hours
        now = datetime.now()
        current_hour = now.hour
        if not (self.automation_start_hour <= current_hour <= self.automation_end_hour):
            result['rejected_reason'] = f"Outside trading hours ({self.automation_start_hour}-{self.automation_end_hour})"
            self.rejected_signals += 1
            return result

        # Check 3: Time since last trade
        time_since_last = time.time() - self.last_trade_time
        if time_since_last < self.min_time_between_trades:
            result['rejected_reason'] = f"Rate limit: {self.min_time_between_trades}s between trades"
            self.rejected_signals += 1
            return result

        # Check 4: Max trades per day
        today_count = sum(1 for t in self.trades_executed if self._is_today(t.timestamp))
        if today_count >= self.max_trades_per_day:
            result['rejected_reason'] = f"Daily trade limit reached ({self.max_trades_per_day})"
            self.rejected_signals += 1
            return result

        # Check 5: Signal confidence minimum
        if signal.confidence < 0.5:
            result['rejected_reason'] = f"Low confidence: {signal.confidence:.2f} < 0.5"
            self.rejected_signals += 1
            return result

        # Check 6: Account constraints
        can_trade, constraint_reason = self.constraint_tracker.can_trade(1.0)
        if not can_trade:
            result['rejected_reason'] = f"Constraint: {constraint_reason}"
            self.rejected_signals += 1
            self.logger.warning(f"⚠️  Trade rejected: {constraint_reason}")
            return result

        # Check 7: WebSocket health
        health_ok, health_reason = self.health_monitor.check_data_quality(
            ConnectionHealth.GOOD
        )
        if not health_ok:
            result['rejected_reason'] = f"Data quality: {health_reason}"
            self.rejected_signals += 1
            self.logger.warning(f"⚠️  Trade rejected: {health_reason}")
            return result

        # Calculate position size
        position_size = self._calculate_position_size(signal)
        if position_size <= 0:
            result['rejected_reason'] = "Insufficient capital for trade"
            self.rejected_signals += 1
            return result

        # Execute trade
        try:
            trade = await self._execute_trade(signal, position_size)

            if trade:
                self.trades_executed.append(trade)
                self.last_trade_time = time.time()
                self.constraint_tracker.record_trade(position_size)

                result['executed'] = True
                result['reason'] = f"Trade executed: {signal.side} ${position_size:.2f} @ {signal.confidence:.1%} confidence"
                result['trade'] = trade

                self.logger.info(
                    f"✅ Trade executed: {signal.asset} {signal.side} ${position_size:.2f} "
                    f"(Confidence: {signal.confidence:.1%}, Expected return: {signal.target_return:+.2f}%)"
                )
            else:
                result['rejected_reason'] = "Trade executor returned None"
                self.rejected_signals += 1

        except Exception as e:
            result['rejected_reason'] = f"Execution error: {str(e)}"
            self.rejected_signals += 1
            self.logger.error(f"❌ Trade execution failed: {e}")

        return result

    def _calculate_position_size(self, signal: TradeSignal) -> float:
        """Calculate safe position size based on available capital and risk.

        Args:
            signal: Trade signal

        Returns:
            Position size in dollars
        """
        constraints = self.constraint_tracker.current_constraints
        if not constraints:
            return 0.0

        # Available balance (use demo if demo mode, else live)
        if settings.prefer_demo_mode:
            available_balance = constraints.demo_balance
        else:
            available_balance = constraints.live_balance

        # Calculate max size by risk percentage
        risk_amount = available_balance * (self.risk_per_trade_percent / 100)

        # Calculate max size by position size limit
        position_limit = available_balance * (self.max_position_size_percent / 100)

        # Use the smaller of the two
        position_size = min(risk_amount, position_limit)

        # Ensure meets minimum
        if position_size < constraints.minimum_amount:
            return 0.0

        # Ensure doesn't exceed remaining day balance
        if position_size > constraints.day_balance:
            position_size = constraints.day_balance

        return position_size

    async def _execute_trade(self, signal: TradeSignal, position_size: float) -> Optional[ExecutedTrade]:
        """Execute a trade through the broker.

        Args:
            signal: Trade signal
            position_size: Position size in dollars

        Returns:
            ExecutedTrade record or None
        """
        # Try OrderExecutor first (Phase H)
        if self.order_executor:
            try:
                if signal.side == "BUY":
                    order_result = await self.order_executor.execute_buy_order(
                        asset=signal.asset,
                        amount=position_size,
                        expiration_time=300,
                        signal_confidence=signal.confidence
                    )
                else:  # SELL
                    order_result = await self.order_executor.execute_sell_order(
                        asset=signal.asset,
                        amount=position_size,
                        signal_confidence=signal.confidence
                    )

                if order_result and order_result.status == "EXECUTED":
                    # Record position
                    pos_id = f"{signal.asset}_{int(time.time() * 1000)}"
                    self.position_tracker.open_position(
                        position_id=pos_id,
                        asset=signal.asset,
                        side=signal.side,
                        amount=position_size,
                        entry_price=order_result.execution_price
                    )

                    trade = ExecutedTrade(
                        asset=signal.asset,
                        side=signal.side,
                        amount=position_size,
                        timestamp=time.time(),
                        order_id=order_result.order_id,
                        execution_price=order_result.execution_price,
                        result="PENDING"
                    )
                    return trade
                else:
                    self.logger.warning(f"Order execution failed: {order_result.message if order_result else 'None'}")
                    return None

            except asyncio.TimeoutError:
                self.logger.error(f"Order execution timeout for {signal.asset}")
                return None
            except Exception as e:
                self.logger.error(f"Order execution error: {e}")
                return None

        # Fallback to legacy trade executor
        if not self.trade_executor:
            self.logger.warning("No trade executor configured")
            return None

        try:
            trade_result = await self.trade_executor(
                asset=signal.asset,
                side=signal.side,
                amount=position_size,
                signal_confidence=signal.confidence
            )

            if trade_result:
                trade = ExecutedTrade(
                    asset=signal.asset,
                    side=signal.side,
                    amount=position_size,
                    timestamp=time.time(),
                    order_id=trade_result.get('order_id'),
                    execution_price=trade_result.get('price', 0.0),
                    result="PENDING"
                )
                return trade

        except asyncio.TimeoutError:
            self.logger.error(f"Trade execution timeout for {signal.asset}")
        except Exception as e:
            self.logger.error(f"Trade execution error: {e}")

        return None

    def get_trading_status(self) -> Dict:
        """Get current trading status.

        Returns:
            Dict with trading statistics and status
        """
        today_count = sum(1 for t in self.trades_executed if self._is_today(t.timestamp))
        constraints = self.constraint_tracker.get_status()
        health = self.health_monitor.get_health_status()

        return {
            'is_running': self.is_running,
            'mode': 'DEMO' if settings.prefer_demo_mode else 'LIVE',
            'trades': {
                'today': today_count,
                'total': len(self.trades_executed),
                'rejected': self.rejected_signals,
                'max_per_day': self.max_trades_per_day
            },
            'constraints': constraints,
            'health': {
                'connection': health.connection_health,
                'latency_ms': health.message_latency_ms,
                'stale_assets': health.stale_assets,
                'uptime_percent': health.estimated_uptime_percent
            },
            'position_sizing': {
                'risk_per_trade_percent': self.risk_per_trade_percent,
                'max_position_size_percent': self.max_position_size_percent,
                'min_time_between_trades_sec': self.min_time_between_trades
            }
        }

    def _is_today(self, timestamp: float) -> bool:
        """Check if timestamp is from today."""
        trade_date = datetime.fromtimestamp(timestamp).date()
        today_date = datetime.now().date()
        return trade_date == today_date

    def export_trade_log(self, filepath: str) -> None:
        """Export trade log to file.

        Args:
            filepath: Path to save trade log
        """
        import json

        trades_dict = []
        for trade in self.trades_executed:
            trades_dict.append({
                'asset': trade.asset,
                'side': trade.side,
                'amount': trade.amount,
                'timestamp': trade.timestamp,
                'order_id': trade.order_id,
                'execution_price': trade.execution_price,
                'result': trade.result
            })

        export = {
            'exported_at': datetime.now().isoformat(),
            'mode': 'DEMO' if settings.prefer_demo_mode else 'LIVE',
            'total_trades': len(self.trades_executed),
            'rejected_signals': self.rejected_signals,
            'trades': trades_dict
        }

        with open(filepath, 'w') as f:
            json.dump(export, f, indent=2)

        self.logger.info(f"Trade log exported to {filepath}")
