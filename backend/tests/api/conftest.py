"""Shared fixtures for API-route tests.

Each test gets a fresh on-disk SQLite file (initialised + seeded by init_db)
and a fresh PriceCache wired into the api.state module. The lifespan/market
data source is NOT started — tests drive prices directly via cache.update().
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from app.api import state as api_state
from app.db.database import init_db
from app.market import PriceCache
from app.market.models import PriceUpdate


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch) -> Path:
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    asyncio.run(init_db(str(db_file)))
    return db_file


@pytest.fixture
def fresh_cache(monkeypatch) -> PriceCache:
    cache = PriceCache()
    monkeypatch.setattr(api_state, "cache", cache)
    monkeypatch.setattr(api_state, "source", None)
    return cache


@pytest.fixture
def client(tmp_db, fresh_cache) -> TestClient:
    # Build a TestClient WITHOUT lifespan so we don't spin up the market
    # data source or snapshot loop during unit tests.
    from app.main import app
    return TestClient(app)


def make_price(ticker: str, price: float, prev: float | None = None) -> PriceUpdate:
    prev = prev if prev is not None else price
    change = price - prev
    change_pct = (change / prev * 100.0) if prev != 0 else 0.0
    return PriceUpdate(
        ticker=ticker,
        price=price,
        prev_price=prev,
        timestamp=datetime.now(timezone.utc),
        change=change,
        change_pct=change_pct,
    )


@pytest_asyncio.fixture
async def seeded_prices(fresh_cache: PriceCache) -> PriceCache:
    await fresh_cache.update([
        make_price("AAPL", 200.0),
        make_price("GOOGL", 150.0),
        make_price("MSFT", 400.0),
    ])
    return fresh_cache
