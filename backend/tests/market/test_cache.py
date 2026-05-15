import asyncio
from datetime import datetime, timezone
import pytest
from app.market.cache import PriceCache
from app.market.models import PriceUpdate


def _make_update(ticker: str, price: float, prev: float = 0.0, change: float = 0.0) -> PriceUpdate:
    return PriceUpdate(
        ticker=ticker,
        price=price,
        prev_price=prev,
        timestamp=datetime.now(timezone.utc),
        change=change,
        change_pct=0.0,
    )


@pytest.mark.asyncio
async def test_update_stores_price():
    cache = PriceCache()
    u = _make_update("AAPL", 190.0)
    await cache.update([u])
    assert cache.get("AAPL") is u


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_ticker():
    cache = PriceCache()
    assert cache.get("XYZ") is None


@pytest.mark.asyncio
async def test_get_all_returns_copy():
    cache = PriceCache()
    await cache.update([_make_update("AAPL", 190.0)])
    result = cache.get_all()
    assert "AAPL" in result
    result["EXTRA"] = None  # mutating the copy should not affect the cache
    assert "EXTRA" not in cache.get_all()


@pytest.mark.asyncio
async def test_get_tickers():
    cache = PriceCache()
    await cache.update([
        _make_update("AAPL", 190.0),
        _make_update("MSFT", 415.0),
    ])
    tickers = cache.get_tickers()
    assert set(tickers) == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_subscriber_receives_update():
    cache = PriceCache()
    q = cache.subscribe()
    u = _make_update("AAPL", 190.0)
    await cache.update([u])
    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.ticker == "AAPL"
    assert received.price == 190.0


@pytest.mark.asyncio
async def test_subscriber_receives_multiple_updates():
    cache = PriceCache()
    q = cache.subscribe()
    updates = [
        _make_update("AAPL", 190.0),
        _make_update("MSFT", 415.0),
    ]
    await cache.update(updates)
    received = []
    for _ in range(2):
        received.append(await asyncio.wait_for(q.get(), timeout=1.0))
    assert {r.ticker for r in received} == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive():
    cache = PriceCache()
    q1 = cache.subscribe()
    q2 = cache.subscribe()
    u = _make_update("AAPL", 190.0)
    await cache.update([u])
    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.ticker == "AAPL"
    assert r2.ticker == "AAPL"


@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    cache = PriceCache()
    q = cache.subscribe()
    cache.unsubscribe(q)
    assert q not in cache._subscribers


@pytest.mark.asyncio
async def test_unsubscribe_idempotent():
    cache = PriceCache()
    q = cache.subscribe()
    cache.unsubscribe(q)
    # Second call should not raise
    cache.unsubscribe(q)


@pytest.mark.asyncio
async def test_unsubscribed_queue_does_not_receive_updates():
    cache = PriceCache()
    q = cache.subscribe()
    cache.unsubscribe(q)
    await cache.update([_make_update("AAPL", 190.0)])
    assert q.empty()


@pytest.mark.asyncio
async def test_full_queue_does_not_block_update():
    """When a subscriber queue is full, updates should still complete."""
    cache = PriceCache()
    # Create a queue with maxsize=2 by patching — we test via the real subscribe but fill it first
    q = cache.subscribe()
    # Fill the queue to capacity using the internal queue's maxsize
    for i in range(q.maxsize):
        try:
            q.put_nowait(_make_update("FILL", float(i)))
        except asyncio.QueueFull:
            break
    # Now update should not raise even though the queue is full
    await cache.update([_make_update("AAPL", 190.0)])  # must not block or raise


@pytest.mark.asyncio
async def test_update_overwrites_previous_price():
    cache = PriceCache()
    await cache.update([_make_update("AAPL", 190.0)])
    await cache.update([_make_update("AAPL", 191.0)])
    assert cache.get("AAPL").price == 191.0
