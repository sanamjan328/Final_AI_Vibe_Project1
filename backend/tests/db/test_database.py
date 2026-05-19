"""Tests for the SQLite database layer."""

from __future__ import annotations

import os
from pathlib import Path

import aiosqlite
import pytest

from app.db import database
from app.db.database import (
    DEFAULT_CASH_BALANCE,
    DEFAULT_USER_ID,
    DEFAULT_WATCHLIST,
    get_db,
    get_db_path,
    init_db,
)


EXPECTED_TABLES: dict[str, set[str]] = {
    "users_profile": {"id", "cash_balance", "created_at"},
    "watchlist": {"id", "user_id", "ticker", "added_at"},
    "positions": {"id", "user_id", "ticker", "quantity", "avg_cost", "updated_at"},
    "trades": {
        "id",
        "user_id",
        "ticker",
        "side",
        "quantity",
        "price",
        "executed_at",
    },
    "portfolio_snapshots": {"id", "user_id", "total_value", "recorded_at"},
    "chat_messages": {
        "id",
        "user_id",
        "role",
        "content",
        "actions",
        "created_at",
    },
}


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    return str(tmp_path / "finally_test.db")


async def _table_columns(conn: aiosqlite.Connection, table: str) -> set[str]:
    async with conn.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return {row[1] for row in rows}


async def test_init_db_creates_all_tables(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()
        names = {row[0] for row in rows}
    for table in EXPECTED_TABLES:
        assert table in names, f"missing table: {table}"


async def test_tables_have_expected_columns(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        for table, expected_cols in EXPECTED_TABLES.items():
            actual_cols = await _table_columns(conn, table)
            assert expected_cols.issubset(
                actual_cols
            ), f"table {table} missing columns; got {actual_cols}, expected {expected_cols}"


async def test_seed_creates_default_user(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        async with conn.execute(
            "SELECT id, cash_balance FROM users_profile"
        ) as cur:
            rows = await cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == DEFAULT_USER_ID
    assert rows[0][1] == DEFAULT_CASH_BALANCE


async def test_seed_creates_default_watchlist(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker",
            (DEFAULT_USER_ID,),
        ) as cur:
            rows = await cur.fetchall()
    tickers = {row[0] for row in rows}
    assert tickers == set(DEFAULT_WATCHLIST)
    assert len(rows) == len(DEFAULT_WATCHLIST)


async def test_init_db_is_idempotent(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    await init_db(temp_db_path)
    await init_db(temp_db_path)

    async with aiosqlite.connect(temp_db_path) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users_profile") as cur:
            user_count = (await cur.fetchone())[0]
        async with conn.execute("SELECT COUNT(*) FROM watchlist") as cur:
            wl_count = (await cur.fetchone())[0]

    assert user_count == 1
    assert wl_count == len(DEFAULT_WATCHLIST)


async def test_unique_constraints_enforced(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                ("dup-1", DEFAULT_USER_ID, "AAPL", "2024-01-01T00:00:00Z"),
            )
            await conn.commit()

    async with aiosqlite.connect(temp_db_path) as conn:
        await conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("p1", DEFAULT_USER_ID, "AAPL", 1.0, 100.0, "2024-01-01T00:00:00Z"),
        )
        await conn.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("p2", DEFAULT_USER_ID, "AAPL", 5.0, 50.0, "2024-01-01T00:00:00Z"),
            )
            await conn.commit()


async def test_get_db_yields_connection(
    temp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DB_PATH", temp_db_path)
    await init_db(temp_db_path)

    gen = get_db()
    conn = await gen.__anext__()
    try:
        assert isinstance(conn, aiosqlite.Connection)
        async with conn.execute("SELECT id FROM users_profile") as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == DEFAULT_USER_ID
    finally:
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()


async def test_get_db_path_respects_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "custom.db"
    monkeypatch.setenv("DB_PATH", str(target))
    assert get_db_path() == str(target)


async def test_get_db_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DB_PATH", raising=False)
    resolved = Path(get_db_path())
    assert resolved.name == "finally.db"
    assert resolved.parent.name == "db"


async def test_writes_and_reads_round_trip(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    async with aiosqlite.connect(temp_db_path) as conn:
        await conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "trade-1",
                DEFAULT_USER_ID,
                "AAPL",
                "buy",
                10.0,
                190.0,
                "2024-01-01T00:00:00Z",
            ),
        )
        await conn.commit()
        async with conn.execute(
            "SELECT ticker, side, quantity, price FROM trades WHERE id = ?",
            ("trade-1",),
        ) as cur:
            row = await cur.fetchone()
    assert row == ("AAPL", "buy", 10.0, 190.0)
