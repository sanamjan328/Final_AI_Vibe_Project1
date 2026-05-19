"""Shared portfolio math used by the trade route, snapshot task, and chat route.

Keeping it in its own module avoids circular imports between routers.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from app.market import PriceCache


DEFAULT_USER_ID = "default"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


@dataclass
class TradeResult:
    success: bool
    error: Optional[str]
    ticker: str
    side: str
    quantity: float
    price: float
    executed_at: str
    cash_balance: float


async def _get_cash(conn: aiosqlite.Connection, user_id: str) -> float:
    async with conn.execute(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError(f"users_profile row missing for {user_id}")
    return float(row[0])


async def _get_position(
    conn: aiosqlite.Connection, user_id: str, ticker: str
) -> Optional[tuple[str, float, float]]:
    async with conn.execute(
        "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    return (row[0], float(row[1]), float(row[2]))


async def execute_trade(
    conn: aiosqlite.Connection,
    cache: PriceCache,
    ticker: str,
    side: str,
    quantity: float,
    user_id: str = DEFAULT_USER_ID,
) -> TradeResult:
    """Execute a market trade against the price cache and DB.

    On success: mutates positions and cash, inserts a trades row, inserts a
    portfolio_snapshot, and commits. On failure: returns TradeResult with
    success=False and a human-readable error; no DB mutation is committed.
    """
    ticker = ticker.upper().strip()
    side = side.lower().strip()
    now = _utc_now_iso()

    if side not in ("buy", "sell"):
        cash = await _get_cash(conn, user_id)
        return TradeResult(
            success=False,
            error=f"Invalid side '{side}'. Must be 'buy' or 'sell'.",
            ticker=ticker, side=side, quantity=quantity, price=0.0,
            executed_at=now, cash_balance=cash,
        )

    if quantity <= 0:
        cash = await _get_cash(conn, user_id)
        return TradeResult(
            success=False,
            error="Quantity must be positive.",
            ticker=ticker, side=side, quantity=quantity, price=0.0,
            executed_at=now, cash_balance=cash,
        )

    update = cache.get(ticker)
    if update is None:
        cash = await _get_cash(conn, user_id)
        return TradeResult(
            success=False,
            error=f"No live price available for {ticker}.",
            ticker=ticker, side=side, quantity=quantity, price=0.0,
            executed_at=now, cash_balance=cash,
        )
    price = float(update.price)

    cash = await _get_cash(conn, user_id)
    position = await _get_position(conn, user_id, ticker)

    if side == "buy":
        cost = quantity * price
        if cost > cash + 1e-9:
            return TradeResult(
                success=False,
                error=(
                    f"Insufficient cash: need ${cost:,.2f}, have ${cash:,.2f}."
                ),
                ticker=ticker, side=side, quantity=quantity, price=price,
                executed_at=now, cash_balance=cash,
            )
        new_cash = cash - cost
        if position is None:
            await conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_id, ticker, quantity, price, now),
            )
        else:
            pos_id, old_qty, old_cost = position
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_cost) + (quantity * price)) / new_qty
            await conn.execute(
                "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
                (new_qty, new_avg, now, pos_id),
            )
    else:  # sell
        if position is None or position[1] < quantity - 1e-9:
            owned = 0.0 if position is None else position[1]
            return TradeResult(
                success=False,
                error=(
                    f"Insufficient shares: trying to sell {quantity} {ticker}, "
                    f"own {owned}."
                ),
                ticker=ticker, side=side, quantity=quantity, price=price,
                executed_at=now, cash_balance=cash,
            )
        proceeds = quantity * price
        new_cash = cash + proceeds
        pos_id, old_qty, old_cost = position
        new_qty = old_qty - quantity
        if new_qty <= 1e-9:
            await conn.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        else:
            await conn.execute(
                "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
                (new_qty, now, pos_id),
            )

    await conn.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (new_cash, user_id),
    )
    await conn.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, ticker, side, quantity, price, now),
    )

    total_value = await compute_total_value(conn, cache, user_id)
    await conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, total_value, now),
    )
    await conn.commit()

    return TradeResult(
        success=True,
        error=None,
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        executed_at=now,
        cash_balance=new_cash,
    )


async def compute_total_value(
    conn: aiosqlite.Connection,
    cache: PriceCache,
    user_id: str = DEFAULT_USER_ID,
) -> float:
    cash = await _get_cash(conn, user_id)
    total = cash
    async with conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ?",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    for ticker, qty, avg_cost in rows:
        update = cache.get(ticker)
        price = float(update.price) if update is not None else float(avg_cost)
        total += float(qty) * price
    return total


async def get_portfolio_view(
    conn: aiosqlite.Connection,
    cache: PriceCache,
    user_id: str = DEFAULT_USER_ID,
) -> dict:
    cash = await _get_cash(conn, user_id)
    async with conn.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = ?"
        " ORDER BY ticker",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()

    positions: list[dict] = []
    total_value = cash
    for ticker, qty, avg_cost in rows:
        update = cache.get(ticker)
        current_price = float(update.price) if update is not None else float(avg_cost)
        qty = float(qty)
        avg_cost = float(avg_cost)
        market_value = qty * current_price
        cost_basis = qty * avg_cost
        unrealized_pnl = market_value - cost_basis
        pnl_pct = ((current_price / avg_cost) - 1.0) * 100.0 if avg_cost > 0 else 0.0
        positions.append({
            "ticker": ticker,
            "quantity": qty,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "pnl_pct": pnl_pct,
        })
        total_value += market_value

    return {
        "cash_balance": cash,
        "total_value": total_value,
        "positions": positions,
    }
