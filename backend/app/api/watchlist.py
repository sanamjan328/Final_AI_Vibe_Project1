"""Watchlist endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import state
from app.api.portfolio_logic import DEFAULT_USER_ID
from app.db.database import get_db


router = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class WatchlistAddBody(BaseModel):
    ticker: str = Field(..., min_length=1)


@router.get("/watchlist")
async def list_watchlist(conn=Depends(get_db)) -> list[dict]:
    async with conn.execute(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker",
        (DEFAULT_USER_ID,),
    ) as cur:
        rows = await cur.fetchall()

    out: list[dict] = []
    for (ticker,) in rows:
        update = state.cache.get(ticker)
        if update is None:
            out.append({
                "ticker": ticker,
                "price": None,
                "prev_price": None,
                "change_pct": None,
                "direction": None,
            })
        else:
            out.append({
                "ticker": ticker,
                "price": update.price,
                "prev_price": update.prev_price,
                "change_pct": update.change_pct,
                "direction": update.direction,
            })
    return out


@router.post("/watchlist")
async def add_to_watchlist(body: WatchlistAddBody, conn=Depends(get_db)) -> dict:
    ticker = body.ticker.upper().strip()
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker must be non-empty")

    try:
        await conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, _utc_now_iso()),
        )
        await conn.commit()
        added = True
    except Exception:
        # UNIQUE constraint — ticker already present. Treat as idempotent success.
        await conn.rollback()
        added = False

    if state.source is not None:
        state.source.add_ticker(ticker)

    return {"ticker": ticker, "added": added}


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, conn=Depends(get_db)) -> dict:
    ticker = ticker.upper().strip()
    cur = await conn.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        (DEFAULT_USER_ID, ticker),
    )
    removed = cur.rowcount > 0
    await conn.commit()

    # Only stop tracking the ticker if no open position holds it.
    if removed and state.source is not None:
        async with conn.execute(
            "SELECT 1 FROM positions WHERE user_id = ? AND ticker = ? AND quantity > 0",
            (DEFAULT_USER_ID, ticker),
        ) as pcur:
            has_position = await pcur.fetchone() is not None
        if not has_position:
            state.source.remove_ticker(ticker)

    return {"ticker": ticker, "removed": removed}
