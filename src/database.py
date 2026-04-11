from __future__ import annotations
import sqlite3
import os
from typing import Optional


class TradeRepository:
    def __init__(self, db: Database):
        self._db = db

    def create(self, stock_code: str, stock_name: str, news_source: str,
               news_channel: str = None, news_text: str = None,
               parameter_snapshot: str = None) -> int:
        cur = self._db.execute(
            "INSERT INTO trades (stock_code, stock_name, news_source, news_channel, "
            "news_text, parameter_snapshot) VALUES (?, ?, ?, ?, ?, ?)",
            (stock_code, stock_name, news_source, news_channel, news_text, parameter_snapshot)
        )
        return cur.lastrowid

    def get(self, trade_id: int) -> Optional[dict]:
        return self._db.fetch_one("SELECT * FROM trades WHERE id = ?", (trade_id,))

    def list(self, status: str = None, date: str = None, limit: int = 100,
             news_source: str = None) -> list[dict]:
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if date:
            query += " AND date(created_at) = ?"
            params.append(date)
        if news_source:
            query += " AND news_source = ?"
            params.append(news_source)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self._db.fetch_all(query, tuple(params))

    def update(self, trade_id: int, **kwargs) -> None:
        if not kwargs:
            return
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [trade_id]
        self._db.execute(f"UPDATE trades SET {sets} WHERE id = ?", tuple(vals))


class ParameterRepository:
    def __init__(self, db: Database):
        self._db = db

    def get_all(self) -> list[dict]:
        return self._db.fetch_all("SELECT * FROM parameters ORDER BY key")

    def upsert(self, key: str, value: str, updated_by: str) -> None:
        existing = self._db.fetch_one("SELECT value FROM parameters WHERE key = ?", (key,))
        if existing:
            self._db.execute(
                "INSERT INTO parameter_history (key, old_value, new_value, updated_by) "
                "VALUES (?, ?, ?, ?)",
                (key, existing["value"], value, updated_by)
            )
            self._db.execute(
                "UPDATE parameters SET value = ?, updated_at = datetime('now', 'localtime'), "
                "updated_by = ? WHERE key = ?",
                (value, updated_by, key)
            )
        else:
            self._db.execute(
                "INSERT INTO parameters (key, value, updated_by) VALUES (?, ?, ?)",
                (key, value, updated_by)
            )

    def get_history(self) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM parameter_history ORDER BY updated_at DESC"
        )


class TickRepository:
    def __init__(self, db: Database):
        self._db = db

    def insert(self, trade_id: int, stock_code: str, price: float,
               volume: int, bid_or_ask: str, timestamp: str) -> int:
        cur = self._db.execute(
            "INSERT INTO ticks (trade_id, stock_code, price, volume, bid_or_ask, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (trade_id, stock_code, price, volume, bid_or_ask, timestamp)
        )
        return cur.lastrowid

    def get_by_trade(self, trade_id: int) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM ticks WHERE trade_id = ? ORDER BY timestamp", (trade_id,)
        )


class ExecutionRepository:
    def __init__(self, db: Database):
        self._db = db

    def insert(self, trade_id: int, side: str, price: float,
               quantity: int, executed_at: str) -> int:
        cur = self._db.execute(
            "INSERT INTO trade_executions (trade_id, side, price, quantity, executed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (trade_id, side, price, quantity, executed_at)
        )
        return cur.lastrowid

    def get_by_trade(self, trade_id: int) -> list[dict]:
        return self._db.fetch_all(
            "SELECT * FROM trade_executions WHERE trade_id = ? ORDER BY executed_at",
            (trade_id,)
        )


class NewsChannelRepository:
    def __init__(self, db: Database):
        self._db = db

    def list(self) -> list[dict]:
        return self._db.fetch_all("SELECT * FROM news_channels ORDER BY id")

    def create(self, channel_url: str, channel_name: str = None) -> int:
        cur = self._db.execute(
            "INSERT INTO news_channels (channel_url, channel_name) VALUES (?, ?)",
            (channel_url, channel_name)
        )
        return cur.lastrowid

    def delete(self, channel_id: int) -> None:
        self._db.execute("DELETE FROM news_channels WHERE id = ?", (channel_id,))

    def toggle(self, channel_id: int) -> None:
        self._db.execute(
            "UPDATE news_channels SET enabled = CASE WHEN enabled = 1 THEN 0 ELSE 1 END "
            "WHERE id = ?", (channel_id,)
        )


class DailyStatsRepository:
    def __init__(self, db: Database):
        self._db = db

    def upsert(self, date: str, **kwargs) -> None:
        existing = self._db.fetch_one("SELECT * FROM daily_stats WHERE date = ?", (date,))
        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            vals = list(kwargs.values()) + [date]
            self._db.execute(f"UPDATE daily_stats SET {sets} WHERE date = ?", tuple(vals))
        else:
            cols = ["date"] + list(kwargs.keys())
            placeholders = ", ".join(["?"] * len(cols))
            vals = [date] + list(kwargs.values())
            self._db.execute(
                f"INSERT INTO daily_stats ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(vals)
            )

    def get_range(self, days: int = 365, date_from: str = None,
                  date_to: str = None) -> list[dict]:
        if date_from and date_to:
            return self._db.fetch_all(
                "SELECT * FROM daily_stats WHERE date BETWEEN ? AND ? ORDER BY date DESC",
                (date_from, date_to)
            )
        return self._db.fetch_all(
            "SELECT * FROM daily_stats WHERE date >= date('now', 'localtime', ?) "
            "ORDER BY date DESC", (f"-{days} days",)
        )

    def get_summary(self, date_from: str = None, date_to: str = None,
                    source: str = None) -> dict:
        rows = self.get_range(date_from=date_from, date_to=date_to) if date_from else self.get_range()
        if not rows:
            return {"total_trades": 0, "win_count": 0, "loss_count": 0,
                    "win_rate": 0.0, "total_pnl": 0.0, "avg_pnl_pct": 0.0}
        total_trades = sum(r["total_trades"] for r in rows)
        win_count = sum(r["win_count"] for r in rows)
        loss_count = sum(r["loss_count"] for r in rows)
        total_pnl = sum(r["total_pnl"] for r in rows)
        avg_pnl = sum(r["avg_pnl_pct"] for r in rows) / len(rows) if rows else 0
        return {
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_count / total_trades if total_trades > 0 else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl_pct": avg_pnl,
        }


class Database:
    def __init__(self, path: str):
        self._path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

        self.trades = TradeRepository(self)
        self.params = ParameterRepository(self)
        self.ticks = TickRepository(self)
        self.executions = ExecutionRepository(self)
        self.channels = NewsChannelRepository(self)
        self.daily_stats = DailyStatsRepository(self)

    def ensure_schema(self) -> None:
        schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
        with open(schema_path, encoding="utf-8") as f:
            self._conn.executescript(f.read())

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self._conn.close()
