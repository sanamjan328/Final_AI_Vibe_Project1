"""SQLite database layer for FinAlly.

Exports:
- init_db(): create tables and seed defaults if missing
- get_db(): async generator yielding an aiosqlite.Connection (FastAPI dependency)
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
from dotenv import load_dotenv


DEFAULT_WATCHLIST: tuple[str, ...] = (
    "AAPL",
    "GOOGL",
    "MSFT",
    "AMZN",
    "TSLA",
    "NVDA",
    "META",
    "JPM",
    "V",
    "NFLX",
)

DEFAULT_USER_ID = "default"
DEFAULT_CASH_BALANCE = 10000.0

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users_profile (
        id TEXT PRIMARY KEY,
        cash_balance REAL NOT NULL DEFAULT 10000.0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        ticker TEXT NOT NULL,
        added_at TEXT NOT NULL,
        UNIQUE(user_id, ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        ticker TEXT NOT NULL,
        quantity REAL NOT NULL,
        avg_cost REAL NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(user_id, ticker)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trades (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        ticker TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity REAL NOT NULL,
        price REAL NOT NULL,
        executed_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        total_value REAL NOT NULL,
        recorded_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL DEFAULT 'default',
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        actions TEXT,
        created_at TEXT NOT NULL
    )
    """,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _project_root() -> Path:
    # backend/app/db/database.py -> project root is three parents up.
    return Path(__file__).resolve().parents[3]


def get_db_path() -> str:
    """Resolve the SQLite path.

    Reads ``DB_PATH`` from the environment (loading ``.env`` from project root if
    present). The default is ``db/finally.db`` relative to the project root.
    Special values ``:memory:`` and ``file::memory:?cache=shared`` are passed
    through unchanged.
    """
    load_dotenv(_project_root() / ".env", override=False)
    raw = os.getenv("DB_PATH", "db/finally.db")
    if raw == ":memory:" or raw.startswith("file::memory:"):
        return raw
    path = Path(raw)
    if not path.is_absolute():
        path = _project_root() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


async def _create_schema(conn: aiosqlite.Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        await conn.execute(stmt)
    await conn.commit()


async def _seed_if_empty(conn: aiosqlite.Connection) -> None:
    async with conn.execute("SELECT COUNT(*) FROM users_profile") as cur:
        row = await cur.fetchone()
    if row is not None and row[0] == 0:
        await conn.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            (DEFAULT_USER_ID, DEFAULT_CASH_BALANCE, _utc_now_iso()),
        )

    async with conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
    ) as cur:
        row = await cur.fetchone()
    if row is not None and row[0] == 0:
        now = _utc_now_iso()
        await conn.executemany(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            [
                (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, now)
                for ticker in DEFAULT_WATCHLIST
            ],
        )

    await conn.commit()


async def init_db(db_path: str | None = None) -> None:
    """Create tables and seed default data if missing.

    Idempotent: safe to call multiple times. Running on an already-seeded
    database is a no-op.
    """
    path = db_path or get_db_path()
    async with aiosqlite.connect(path) as conn:
        await conn.execute("PRAGMA foreign_keys = ON")
        await _create_schema(conn)
        await _seed_if_empty(conn)


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """FastAPI dependency: yields an open aiosqlite connection per request."""
    path = get_db_path()
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    try:
        await conn.execute("PRAGMA foreign_keys = ON")
        yield conn
    finally:
        await conn.close()
