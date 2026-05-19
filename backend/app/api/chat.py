"""Chat endpoint — proxies to the LLM module and auto-executes its actions."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api import state
from app.api.portfolio_logic import (
    DEFAULT_USER_ID,
    execute_trade,
    get_portfolio_view,
)
from app.db.database import get_db


router = APIRouter()

HISTORY_LIMIT = 20


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


async def _load_history(conn, limit: int) -> list[dict]:
    async with conn.execute(
        "SELECT role, content FROM chat_messages WHERE user_id = ?"
        " ORDER BY created_at DESC LIMIT ?",
        (DEFAULT_USER_ID, limit),
    ) as cur:
        rows = await cur.fetchall()
    rows.reverse()
    return [{"role": r[0], "content": r[1]} for r in rows]


async def _persist_message(conn, role: str, content: str, actions: dict | None) -> None:
    await conn.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()),
            DEFAULT_USER_ID,
            role,
            content,
            json.dumps(actions) if actions is not None else None,
            _utc_now_iso(),
        ),
    )


def _import_llm():
    """Import the LLM chat module lazily so missing module → 503, not import error."""
    try:
        from app.llm import chat as llm_chat  # type: ignore
        return llm_chat
    except Exception:
        return None


@router.post("/chat")
async def post_chat(body: ChatRequest, conn=Depends(get_db)) -> dict:
    llm_chat = _import_llm()
    if llm_chat is None:
        raise HTTPException(
            status_code=503,
            detail="LLM module not available yet. Try again once app.llm.chat is implemented.",
        )

    portfolio_context = await get_portfolio_view(conn, state.cache, DEFAULT_USER_ID)
    history = await _load_history(conn, HISTORY_LIMIT)

    mock = os.getenv("LLM_MOCK", "").strip().lower() == "true"

    try:
        response = await llm_chat.process_chat_message(
            user_message=body.message,
            portfolio_context=portfolio_context,
            conversation_history=history,
            mock=mock,
        )
    except Exception as exc:  # network/quota/parse failure
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}")

    # ChatResponse is a Pydantic model from app.llm.chat. Pull fields defensively
    # so a slightly different shape (dict, etc.) still works.
    if hasattr(response, "model_dump"):
        data = response.model_dump()
    elif isinstance(response, dict):
        data = response
    else:
        data = {
            "message": getattr(response, "message", ""),
            "trades": getattr(response, "trades", []) or [],
            "watchlist_changes": getattr(response, "watchlist_changes", []) or [],
        }

    proposed_trades = data.get("trades") or []
    proposed_watchlist = data.get("watchlist_changes") or []
    message_text = data.get("message", "")

    executed_trades: list[dict] = []
    failed_trades: list[dict] = []
    for t in proposed_trades:
        ticker = t.get("ticker") if isinstance(t, dict) else getattr(t, "ticker", None)
        side = t.get("side") if isinstance(t, dict) else getattr(t, "side", None)
        qty = t.get("quantity") if isinstance(t, dict) else getattr(t, "quantity", None)
        if not ticker or not side or qty is None:
            failed_trades.append({"trade": t, "error": "Missing ticker, side, or quantity"})
            continue
        result = await execute_trade(
            conn, state.cache, ticker=ticker, side=side, quantity=float(qty)
        )
        if result.success:
            executed_trades.append({
                "ticker": result.ticker,
                "side": result.side,
                "quantity": result.quantity,
                "price": result.price,
                "executed_at": result.executed_at,
            })
            if side.lower() == "buy" and state.source is not None:
                state.source.add_ticker(result.ticker)
        else:
            failed_trades.append({
                "ticker": result.ticker,
                "side": result.side,
                "quantity": result.quantity,
                "error": result.error,
            })

    executed_watchlist_changes: list[dict] = []
    for change in proposed_watchlist:
        ticker = change.get("ticker") if isinstance(change, dict) else getattr(change, "ticker", None)
        action = change.get("action") if isinstance(change, dict) else getattr(change, "action", None)
        if not ticker or action not in ("add", "remove"):
            continue
        ticker = ticker.upper().strip()
        if action == "add":
            try:
                await conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, _utc_now_iso()),
                )
                await conn.commit()
                if state.source is not None:
                    state.source.add_ticker(ticker)
                executed_watchlist_changes.append({"ticker": ticker, "action": "add"})
            except Exception:
                await conn.rollback()
        else:
            await conn.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
                (DEFAULT_USER_ID, ticker),
            )
            await conn.commit()
            executed_watchlist_changes.append({"ticker": ticker, "action": "remove"})

    # Persist conversation. Actions JSON captures what actually happened.
    await _persist_message(conn, "user", body.message, None)
    await _persist_message(
        conn,
        "assistant",
        message_text,
        {
            "executed_trades": executed_trades,
            "failed_trades": failed_trades,
            "executed_watchlist_changes": executed_watchlist_changes,
        },
    )
    await conn.commit()

    return {
        "message": message_text,
        "trades": proposed_trades,
        "watchlist_changes": proposed_watchlist,
        "executed_trades": executed_trades,
        "failed_trades": failed_trades,
        "executed_watchlist_changes": executed_watchlist_changes,
    }
