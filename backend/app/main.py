"""FastAPI application entrypoint for FinAlly.

Run with: ``uvicorn app.main:app --host 0.0.0.0 --port 8000`` from the
``backend/`` directory.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import chat as chat_module
from app.api import market as market_module
from app.api import portfolio as portfolio_module
from app.api import state as api_state
from app.api import system as system_module
from app.api import watchlist as watchlist_module
from app.api.portfolio_logic import DEFAULT_USER_ID, compute_total_value
from app.db.database import get_db_path, init_db
from app.market import create_market_data_source


logger = logging.getLogger(__name__)


SNAPSHOT_INTERVAL_SEC = 30.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


async def _gather_startup_tickers() -> list[str]:
    """Union of watchlist tickers and tickers with open positions."""
    path = get_db_path()
    async with aiosqlite.connect(path) as conn:
        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
        ) as cur:
            watch = [r[0] for r in await cur.fetchall()]
        async with conn.execute(
            "SELECT ticker FROM positions WHERE user_id = ? AND quantity > 0",
            (DEFAULT_USER_ID,),
        ) as cur:
            held = [r[0] for r in await cur.fetchall()]
    return list(dict.fromkeys(watch + held))


async def _snapshot_loop() -> None:
    """Record a portfolio_snapshots row every SNAPSHOT_INTERVAL_SEC."""
    path = get_db_path()
    while True:
        try:
            await asyncio.sleep(SNAPSHOT_INTERVAL_SEC)
            async with aiosqlite.connect(path) as conn:
                total = await compute_total_value(conn, api_state.cache, DEFAULT_USER_ID)
                await conn.execute(
                    "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
                    " VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, total, _utc_now_iso()),
                )
                await conn.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Snapshot task failed; continuing.")


async def _record_initial_snapshot() -> None:
    """Drop a single snapshot row right at startup so the P&L chart isn't empty."""
    path = get_db_path()
    async with aiosqlite.connect(path) as conn:
        total = await compute_total_value(conn, api_state.cache, DEFAULT_USER_ID)
        await conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
            " VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER_ID, total, _utc_now_iso()),
        )
        await conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    api_state.source = create_market_data_source(api_state.cache)
    tickers = await _gather_startup_tickers()
    await api_state.source.start(tickers)

    await _record_initial_snapshot()

    snapshot_task = asyncio.create_task(_snapshot_loop())
    try:
        yield
    finally:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except (asyncio.CancelledError, Exception):
            pass
        if api_state.source is not None:
            await api_state.source.stop()


app = FastAPI(lifespan=lifespan, title="FinAlly Backend")

app.include_router(market_module.router, prefix="/api")
app.include_router(portfolio_module.router, prefix="/api")
app.include_router(watchlist_module.router, prefix="/api")
app.include_router(chat_module.router, prefix="/api")
app.include_router(system_module.router, prefix="/api")


# Static frontend (built Next.js export). Mounted last so /api/* wins.
_static_dir = Path(__file__).resolve().parent.parent / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
