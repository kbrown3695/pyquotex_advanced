"""SQLite-backed persistent candle storage.

Stores OHLCV data for all asset/timeframe pairs, enabling:
- Full historical chart data (beyond 200-candle live buffer)
- Backtesting and analysis
- Query any date range on-demand
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class CandleStore:
    """SQLite database for persistent candle storage."""

    def __init__(self, db_path: str = "quotex_candles.db"):
        """Initialize candle store.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Create candles table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS candles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(asset, timeframe, time)
            )
            """
        )

        # Create index for fast queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_asset_timeframe_time
            ON candles(asset, timeframe, time DESC)
            """
        )

        conn.commit()
        conn.close()

    def save_candle(self, asset: str, timeframe: str, candle: Dict[str, Any]) -> None:
        """Save a single candle to database.

        Args:
            asset: Asset symbol (e.g. "AUD/CAD (OTC)")
            timeframe: Timeframe (e.g. "1m", "3s")
            candle: Dict with keys: time, open, high, low, close, volume
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO candles
                (asset, timeframe, time, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset,
                    timeframe,
                    candle.get("time"),
                    candle.get("open"),
                    candle.get("high"),
                    candle.get("low"),
                    candle.get("close"),
                    candle.get("volume", 0),
                ),
            )
            conn.commit()
        except Exception as e:
            print(f"Error saving candle: {e}")
        finally:
            conn.close()

    def save_candles_batch(
        self, asset: str, timeframe: str, candles: List[Dict[str, Any]]
    ) -> None:
        """Save multiple candles efficiently.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            candles: List of candle dicts
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            for candle in candles:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO candles
                    (asset, timeframe, time, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        asset,
                        timeframe,
                        candle.get("time"),
                        candle.get("open"),
                        candle.get("high"),
                        candle.get("low"),
                        candle.get("close"),
                        candle.get("volume", 0),
                    ),
                )
            conn.commit()
        except Exception as e:
            print(f"Error saving candles batch: {e}")
        finally:
            conn.close()

    def get_candles(
        self,
        asset: str,
        timeframe: str,
        limit: int = 200,
        start_time: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get candles for an asset/timeframe.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            limit: Max candles to return (default 200, most recent)
            start_time: Unix timestamp to filter from (optional)

        Returns:
            List of candle dicts, ordered by time ASC
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            if start_time:
                query = """
                    SELECT * FROM candles
                    WHERE asset = ? AND timeframe = ? AND time >= ?
                    ORDER BY time ASC
                    LIMIT ?
                """
                cursor.execute(query, (asset, timeframe, start_time, limit))
            else:
                query = """
                    SELECT * FROM candles
                    WHERE asset = ? AND timeframe = ?
                    ORDER BY time DESC
                    LIMIT ?
                """
                cursor.execute(query, (asset, timeframe, limit))
                rows = cursor.fetchall()
                rows.reverse()  # Reverse to ascending order
                return [dict(row) for row in rows]

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_latest_candle(self, asset: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """Get the most recent candle.

        Args:
            asset: Asset symbol
            timeframe: Timeframe

        Returns:
            Candle dict or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM candles
                WHERE asset = ? AND timeframe = ?
                ORDER BY time DESC
                LIMIT 1
                """,
                (asset, timeframe),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def count_candles(self, asset: str, timeframe: str) -> int:
        """Count total candles for an asset/timeframe.

        Args:
            asset: Asset symbol
            timeframe: Timeframe

        Returns:
            Count of candles in database
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT COUNT(*) FROM candles WHERE asset = ? AND timeframe = ?",
                (asset, timeframe),
            )
            return cursor.fetchone()[0]
        finally:
            conn.close()

    def delete_old_candles(self, asset: str, timeframe: str, keep_count: int = 5000) -> int:
        """Delete old candles, keeping only most recent.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            keep_count: Number of recent candles to keep

        Returns:
            Number of candles deleted
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get the time of the nth most recent candle
            cursor.execute(
                """
                SELECT time FROM candles
                WHERE asset = ? AND timeframe = ?
                ORDER BY time DESC
                LIMIT 1 OFFSET ?
                """,
                (asset, timeframe, keep_count),
            )
            result = cursor.fetchone()
            if not result:
                return 0

            cutoff_time = result[0]

            # Delete older candles
            cursor.execute(
                """
                DELETE FROM candles
                WHERE asset = ? AND timeframe = ? AND time < ?
                """,
                (asset, timeframe, cutoff_time),
            )
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_candles_in_range(
        self, asset: str, timeframe: str, start_time: int, end_time: int
    ) -> List[Dict[str, Any]]:
        """Get candles within a time range.

        Args:
            asset: Asset symbol
            timeframe: Timeframe
            start_time: Unix timestamp (inclusive)
            end_time: Unix timestamp (exclusive)

        Returns:
            List of candle dicts, ordered by time ASC
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM candles
                WHERE asset = ? AND timeframe = ? AND time >= ? AND time < ?
                ORDER BY time ASC
                """,
                (asset, timeframe, start_time, end_time),
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


__all__ = ["CandleStore"]
