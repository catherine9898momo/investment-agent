"""SQLite 记忆存储层 — 管理持仓、关注列表、偏好和历史分析"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "memory.db"


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db():
    """初始化数据库表结构"""
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            market TEXT NOT NULL,  -- US / CN / HK
            shares REAL DEFAULT 0,
            avg_cost REAL DEFAULT 0,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            reason TEXT DEFAULT '',
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,  -- weekly / adhoc
            content TEXT NOT NULL,
            companies TEXT DEFAULT '[]',  -- JSON array
            events TEXT DEFAULT '[]',     -- JSON array
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            summary TEXT,
            related_companies TEXT DEFAULT '[]',
            published_at TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    db.close()


# ── Portfolio ──

def add_holding(symbol: str, name: str, market: str, shares: float = 0, avg_cost: float = 0):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO portfolio (symbol, name, market, shares, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (symbol, name, market, shares, avg_cost, datetime.now().isoformat()),
    )
    db.commit()
    db.close()


def remove_holding(symbol: str):
    db = get_db()
    db.execute("DELETE FROM portfolio WHERE symbol = ?", (symbol,))
    db.commit()
    db.close()


def get_portfolio() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM portfolio ORDER BY market, symbol").fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Watchlist ──

def add_to_watchlist(symbol: str, name: str, market: str, reason: str = ""):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO watchlist (symbol, name, market, reason) VALUES (?, ?, ?, ?)",
        (symbol, name, market, reason),
    )
    db.commit()
    db.close()


def remove_from_watchlist(symbol: str):
    db = get_db()
    db.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
    db.commit()
    db.close()


def get_watchlist() -> list[dict]:
    db = get_db()
    rows = db.execute("SELECT * FROM watchlist ORDER BY market, symbol").fetchall()
    db.close()
    return [dict(r) for r in rows]


# ── Preferences ──

def set_preference(key: str, value: str):
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, ?)",
        (key, value, datetime.now().isoformat()),
    )
    db.commit()
    db.close()


def get_preference(key: str) -> str | None:
    db = get_db()
    row = db.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    db.close()
    return row["value"] if row else None


def get_all_preferences() -> dict[str, str]:
    db = get_db()
    rows = db.execute("SELECT key, value FROM preferences").fetchall()
    db.close()
    return {r["key"]: r["value"] for r in rows}


# ── Analyses ──

def save_analysis(date: str, type_: str, content: str, companies: str = "[]", events: str = "[]"):
    db = get_db()
    db.execute(
        "INSERT INTO analyses (date, type, content, companies, events) VALUES (?, ?, ?, ?, ?)",
        (date, type_, content, companies, events),
    )
    db.commit()
    db.close()


def get_recent_analyses(limit: int = 10) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM analyses ORDER BY date DESC LIMIT ?", (limit,)
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
