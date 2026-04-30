"""SQLite state for paper-trade phase. Migration to Postgres on live deploy."""
import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .config import BOT


SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id TEXT NOT NULL,
    market_question TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('YES', 'NO')),
    entry_price REAL NOT NULL,
    size_usd REAL NOT NULL,
    shares REAL NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    exit_price REAL,
    pnl_usd REAL,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED-WIN', 'CLOSED-LOSS', 'CLOSED-STOPLOSS')),
    mode TEXT NOT NULL,
    category TEXT,
    end_date TEXT NOT NULL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
CREATE INDEX IF NOT EXISTS idx_positions_market ON positions(market_id);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at TEXT NOT NULL,
    markets_seen INTEGER NOT NULL,
    candidates_found INTEGER NOT NULL,
    positions_opened INTEGER NOT NULL,
    bankroll_used REAL NOT NULL,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS skipped (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at TEXT NOT NULL,
    market_id TEXT NOT NULL,
    market_question TEXT,
    skip_reason TEXT NOT NULL,
    market_price REAL,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_skipped_reason ON skipped(skip_reason);
"""


@contextmanager
def connect():
    Path(BOT.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(BOT.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def insert_position(*, market_id: str, market_question: str, side: str,
                    entry_price: float, size_usd: float, shares: float,
                    end_date: str, category: str | None, mode: str,
                    metadata: dict | None = None) -> int:
    with connect() as conn:
        cur = conn.execute("""
            INSERT INTO positions
              (market_id, market_question, side, entry_price, size_usd, shares,
               opened_at, status, mode, category, end_date, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
        """, (
            market_id, market_question, side, entry_price, size_usd, shares,
            datetime.utcnow().isoformat(), mode, category, end_date,
            json.dumps(metadata or {}),
        ))
        return cur.lastrowid


def open_positions() -> list[sqlite3.Row]:
    with connect() as conn:
        return list(conn.execute(
            "SELECT * FROM positions WHERE status = 'OPEN' ORDER BY opened_at"
        ))


def close_position(*, position_id: int, exit_price: float, pnl_usd: float,
                   status: str) -> None:
    with connect() as conn:
        conn.execute("""
            UPDATE positions SET closed_at = ?, exit_price = ?,
                                 pnl_usd = ?, status = ?
            WHERE id = ?
        """, (datetime.utcnow().isoformat(), exit_price, pnl_usd, status,
              position_id))


def already_holding(market_id: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM positions WHERE market_id = ? AND status = 'OPEN'",
            (market_id,),
        ).fetchone()
        return row is not None


def category_exposure() -> dict[str, float]:
    """Sum of open USD by category (for concentration limits)."""
    with connect() as conn:
        rows = conn.execute("""
            SELECT category, SUM(size_usd) AS exposure
            FROM positions WHERE status = 'OPEN' GROUP BY category
        """).fetchall()
    return {r["category"] or "uncategorized": r["exposure"] for r in rows}


def log_scan(*, markets_seen: int, candidates: int, opened: int,
             bankroll_used: float, metadata: dict | None = None) -> None:
    with connect() as conn:
        conn.execute("""
            INSERT INTO scans (scanned_at, markets_seen, candidates_found,
                               positions_opened, bankroll_used, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), markets_seen, candidates,
              opened, bankroll_used, json.dumps(metadata or {})))


def log_skip(*, market_id: str, question: str, reason: str,
             price: float | None, metadata: dict | None = None) -> None:
    with connect() as conn:
        conn.execute("""
            INSERT INTO skipped (scanned_at, market_id, market_question,
                                 skip_reason, market_price, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (datetime.utcnow().isoformat(), market_id, question, reason,
              price, json.dumps(metadata or {})))


def stats(since_iso: str | None = None) -> dict:
    """Win rate, avg return, total P&L, drawdown — the validation metrics."""
    where = "WHERE status != 'OPEN'"
    params: tuple = ()
    if since_iso:
        where += " AND closed_at >= ?"
        params = (since_iso,)
    with connect() as conn:
        row = conn.execute(f"""
            SELECT
              COUNT(*) AS n,
              SUM(CASE WHEN status = 'CLOSED-WIN' THEN 1 ELSE 0 END) AS wins,
              SUM(pnl_usd) AS total_pnl,
              AVG(pnl_usd / size_usd) AS avg_return
            FROM positions {where}
        """, params).fetchone()
    n = row["n"] or 0
    return {
        "resolved": n,
        "wins": row["wins"] or 0,
        "win_rate": (row["wins"] or 0) / n if n else 0.0,
        "total_pnl": row["total_pnl"] or 0.0,
        "avg_return": row["avg_return"] or 0.0,
    }
