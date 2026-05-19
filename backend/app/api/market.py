"""SSE stream of live price updates."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api import state
from app.market.models import PriceUpdate


router = APIRouter()

KEEPALIVE_INTERVAL_SEC = 15.0


def _serialize(update: PriceUpdate) -> str:
    payload = {
        "ticker": update.ticker,
        "price": update.price,
        "prev_price": update.prev_price,
        "change_pct": update.change_pct,
        "direction": update.direction,
        "timestamp": update.timestamp.isoformat().replace("+00:00", "Z"),
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _event_generator(request: Request) -> AsyncIterator[str]:
    cache = state.cache
    queue = cache.subscribe()
    try:
        # Send a snapshot of every ticker currently known so a new client
        # paints something before the next market tick arrives.
        for update in cache.get_all().values():
            yield _serialize(update)

        while True:
            if await request.is_disconnected():
                break
            try:
                update = await asyncio.wait_for(
                    queue.get(), timeout=KEEPALIVE_INTERVAL_SEC
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield _serialize(update)
    finally:
        cache.unsubscribe(queue)


@router.get("/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers=headers,
    )
