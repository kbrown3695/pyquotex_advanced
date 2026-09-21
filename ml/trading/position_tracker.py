#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase H: Position Tracker
=========================
Tracks open positions and closed trades.
Monitors P&L and execution metrics.

Features:
- Track open positions per asset
- Record trade entry/exit points
- Calculate P&L per trade
- Aggregate position metrics
- Export position log
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Position:
    """An open or closed trading position."""
    position_id: str
    asset: str
    side: str  # BUY or SELL
    entry_amount: float
    entry_price: float = 0.0
    entry_time: float = field(default_factory=time.time)

    # Exit info (populated when position closes)
    exit_price: float = 0.0
    exit_time: Optional[float] = None
    exit_reason: str = ""

    # Metrics
    status: str = "OPEN"  # OPEN, CLOSED_WIN, CLOSED_LOSS, CLOSED_BREAK_EVEN
    profit_loss_pct: float = 0.0
    profit_loss_usd: float = 0.0


class PositionTracker:
    """
    Tracks open and closed trading positions.

    Responsibilities:
    1. Record position entries
    2. Track position exits
    3. Calculate P&L
    4. Aggregate metrics
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        """Initialize position tracker.

        Args:
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(__name__)

        # Active positions (asset -> position)
        self.open_positions: Dict[str, List[Position]] = {}

        # Closed positions history
        self.closed_positions: List[Position] = []
        self.MAX_HISTORY = 1000

        # Statistics
        self.total_trades: int = 0
        self.winning_trades: int = 0
        self.losing_trades: int = 0
        self.total_profit_loss: float = 0.0

    def open_position(
        self,
        position_id: str,
        asset: str,
        side: str,
        amount: float,
        entry_price: float = 0.0
    ) -> Position:
        """Record a new open position.

        Args:
            position_id: Unique position identifier
            asset: Asset symbol
            side: BUY or SELL
            amount: Position size in USD
            entry_price: Entry price (if available)

        Returns:
            Position object
        """
        position = Position(
            position_id=position_id,
            asset=asset,
            side=side,
            entry_amount=amount,
            entry_price=entry_price,
            entry_time=time.time()
        )

        # Add to open positions
        if asset not in self.open_positions:
            self.open_positions[asset] = []

        self.open_positions[asset].append(position)

        self.logger.info(
            f"📍 POSITION OPENED: {position_id} {side} {asset} ${amount:.2f}"
        )

        return position

    def close_position(
        self,
        position_id: str,
        asset: str,
        exit_price: float = 0.0,
        exit_reason: str = ""
    ) -> Optional[Position]:
        """Close an open position.

        Args:
            position_id: Position to close
            asset: Asset symbol
            exit_price: Exit price
            exit_reason: Reason for closing

        Returns:
            Closed position with P&L calculated
        """
        if asset not in self.open_positions:
            self.logger.warning(f"No open positions for {asset}")
            return None

        # Find position by ID
        position = None
        for pos in self.open_positions[asset]:
            if pos.position_id == position_id:
                position = pos
                break

        if not position:
            self.logger.warning(f"Position {position_id} not found")
            return None

        # Calculate P&L
        position.exit_price = exit_price
        position.exit_time = time.time()
        position.exit_reason = exit_reason

        # Simple P&L calculation (in real trading, adjust for entry/exit prices)
        if position.entry_price > 0 and exit_price > 0:
            if position.side == "BUY":
                pnl_pct = ((exit_price - position.entry_price) / position.entry_price) * 100
            else:  # SELL
                pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100

            position.profit_loss_pct = pnl_pct
            position.profit_loss_usd = (pnl_pct / 100) * position.entry_amount

        # Determine status
        if position.profit_loss_pct > 0.1:
            position.status = "CLOSED_WIN"
            self.winning_trades += 1
        elif position.profit_loss_pct < -0.1:
            position.status = "CLOSED_LOSS"
            self.losing_trades += 1
        else:
            position.status = "CLOSED_BREAK_EVEN"

        # Move to closed
        self.open_positions[asset].remove(position)
        self.closed_positions.append(position)
        self.total_trades += 1
        self.total_profit_loss += position.profit_loss_usd

        # Keep history bounded
        if len(self.closed_positions) > self.MAX_HISTORY:
            self.closed_positions.pop(0)

        # Log result
        status_emoji = "✅" if position.status == "CLOSED_WIN" else "❌" if position.status == "CLOSED_LOSS" else "🟡"
        self.logger.info(
            f"{status_emoji} POSITION CLOSED: {position_id} {asset} "
            f"P&L: {position.profit_loss_pct:+.2f}% (${position.profit_loss_usd:+.2f})"
        )

        return position

    def get_open_positions(self, asset: Optional[str] = None) -> List[Position]:
        """Get open positions.

        Args:
            asset: Optional asset filter

        Returns:
            List of open positions
        """
        if asset:
            return self.open_positions.get(asset, [])

        all_positions = []
        for positions in self.open_positions.values():
            all_positions.extend(positions)
        return all_positions

    def get_position_by_id(self, position_id: str) -> Optional[Position]:
        """Get position by ID.

        Args:
            position_id: Position identifier

        Returns:
            Position if found
        """
        for positions in self.open_positions.values():
            for pos in positions:
                if pos.position_id == position_id:
                    return pos
        return None

    def get_statistics(self) -> Dict:
        """Get position statistics.

        Returns:
            Dict with trading metrics
        """
        win_rate = (
            (self.winning_trades / self.total_trades * 100)
            if self.total_trades > 0 else 0
        )

        total_open = len(self.get_open_positions())

        return {
            'open_positions': total_open,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate_percent': win_rate,
            'total_profit_loss_usd': self.total_profit_loss,
            'avg_profit_loss_per_trade': (
                self.total_profit_loss / self.total_trades
                if self.total_trades > 0 else 0
            )
        }

    def get_position_summary_by_asset(self) -> Dict[str, Dict]:
        """Get position summary grouped by asset.

        Returns:
            Dict mapping asset to position summary
        """
        summary = {}

        for asset, positions in self.open_positions.items():
            total_exposure = sum(p.entry_amount for p in positions)
            summary[asset] = {
                'open_positions': len(positions),
                'total_exposure_usd': total_exposure,
                'positions': [
                    {
                        'id': p.position_id,
                        'side': p.side,
                        'amount': p.entry_amount,
                        'entry_price': p.entry_price,
                        'opened_at': datetime.fromtimestamp(p.entry_time).isoformat()
                    }
                    for p in positions
                ]
            }

        return summary

    def get_recent_trades(self, limit: int = 20) -> List[Dict]:
        """Get recent closed trades.

        Args:
            limit: Number of recent trades

        Returns:
            List of trade records
        """
        return [
            {
                'position_id': p.position_id,
                'asset': p.asset,
                'side': p.side,
                'amount': p.entry_amount,
                'entry_price': p.entry_price,
                'exit_price': p.exit_price,
                'pnl_pct': p.profit_loss_pct,
                'pnl_usd': p.profit_loss_usd,
                'status': p.status,
                'exit_reason': p.exit_reason,
                'duration_sec': (p.exit_time - p.entry_time) if p.exit_time else 0,
                'opened_at': datetime.fromtimestamp(p.entry_time).isoformat(),
                'closed_at': (
                    datetime.fromtimestamp(p.exit_time).isoformat()
                    if p.exit_time else None
                )
            }
            for p in self.closed_positions[-limit:]
        ]

    def export_positions_log(self, filepath: str) -> None:
        """Export position history to file.

        Args:
            filepath: Path to save log
        """
        import json

        export = {
            'exported_at': datetime.now().isoformat(),
            'statistics': self.get_statistics(),
            'open_positions': self.get_position_summary_by_asset(),
            'recent_trades': self.get_recent_trades(100)
        }

        with open(filepath, 'w') as f:
            json.dump(export, f, indent=2)

        self.logger.info(f"Position log exported to {filepath}")
