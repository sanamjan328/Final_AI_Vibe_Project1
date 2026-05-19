"""Portfolio endpoints: GET /portfolio, POST /portfolio/trade, GET /portfolio/history."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api import state
from app.api.portfolio_logic import (
    DEFAULT_USER_ID,
    execute_trade,
    get_portfolio_view,
)
from app.db.database import get_db


router = APIRouter()


class TradeRequest(BaseModel):
    ticker: str = Field(..., min_length=1)
    side: str
    quantity: float


@router.get("/portfolio")
async def get_portfolio(conn=Depends(get_db)) -> dict:
    return await get_portfolio_view(conn, state.cache, DEFAULT_USER_ID)


@router.post("/portfolio/trade")
async def post_trade(body: TradeRequest, conn=Depends(get_db)) -> dict:
    result = await execute_trade(
        conn,
        state.cache,
        ticker=body.ticker,
        side=body.side,
        quantity=body.quantity,
    )

    # Track the ticker in the market data source so future ticks include it.
    if result.success and body.side.lower() == "buy" and state.source is not None:
        state.source.add_ticker(result.ticker)

    return {
        "success": result.success,
        "error": result.error,
        "trade": {
            "ticker": result.ticker,
            "side": result.side,
            "quantity": result.quantity,
            "price": result.price,
            "executed_at": result.executed_at,
        } if result.success else None,
        "cash_balance": result.cash_balance,
    }


@router.get("/portfolio/history")
async def get_history(conn=Depends(get_db)) -> list[dict]:
    async with conn.execute(
        "SELECT total_value, recorded_at FROM portfolio_snapshots"
        " WHERE user_id = ? ORDER BY recorded_at ASC",
        (DEFAULT_USER_ID,),
    ) as cur:
        rows = await cur.fetchall()
    return [
        {"total_value": float(r[0]), "recorded_at": r[1]} for r in rows
    ]
