"""Shared module-level handles to the price cache and market data source.

The FastAPI lifespan in ``app.main`` initialises ``cache`` and ``source`` on
startup. Router modules import these names directly. Tests can replace them
with fakes by monkeypatching this module.
"""

from __future__ import annotations

from app.market import PriceCache, MarketDataSource


cache: PriceCache = PriceCache()
source: MarketDataSource | None = None


def get_cache() -> PriceCache:
    return cache


def get_source() -> MarketDataSource | None:
    return source
