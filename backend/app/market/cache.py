import asyncio
from .models import PriceUpdate


class PriceCache:
    """In-memory store for the latest price of every tracked ticker.

    Write path: background market data task calls update() after each poll cycle.
    Read path: SSE endpoint and API routes call get() / get_all() — plain dict lookup.
    Push path: update() puts each PriceUpdate into every subscriber's asyncio.Queue.

    CPython's GIL makes individual dict reads atomic, so reads don't need locking.
    Writes use a lock to prevent torn state during bulk updates (multiple tickers
    updated in one call must appear as a consistent snapshot).
    """

    def __init__(self) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = asyncio.Lock()
        self._subscribers: list[asyncio.Queue] = []

    async def update(self, updates: list[PriceUpdate]) -> None:
        """Write new prices and notify all SSE subscribers."""
        async with self._lock:
            for u in updates:
                self._prices[u.ticker] = u
        for queue in self._subscribers:
            for u in updates:
                try:
                    queue.put_nowait(u)
                except asyncio.QueueFull:
                    pass  # slow client — drop the update; client will catch up

    def get(self, ticker: str) -> PriceUpdate | None:
        return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceUpdate]:
        return dict(self._prices)  # shallow copy — safe for iteration

    def get_tickers(self) -> list[str]:
        return list(self._prices.keys())

    def subscribe(self) -> asyncio.Queue:
        """Return a new queue that receives every PriceUpdate going forward.

        Each connected SSE client gets its own queue. The background task puts
        into all queues on every update cycle — fan-out without contention.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove queue when an SSE client disconnects."""
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass
