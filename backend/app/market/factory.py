import os
import logging
from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(cache: PriceCache) -> MarketDataSource:
    """Instantiate the correct MarketDataSource based on environment config.

    Selection logic:
      - MASSIVE_API_KEY set and non-empty  →  MassiveClient
      - Otherwise                           →  MarketSimulator

    Optional env vars:
      - MASSIVE_POLL_INTERVAL  float seconds, default 15.0 (free tier safe)
    """
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()

    if api_key:
        from .massive_client import MassiveClient
        poll_interval = float(os.getenv("MASSIVE_POLL_INTERVAL", "15.0"))
        logger.info("Market data: Massive API (poll_interval=%.1fs)", poll_interval)
        return MassiveClient(api_key=api_key, cache=cache, poll_interval=poll_interval)

    from .simulator import MarketSimulator
    logger.info("Market data: Simulator (no MASSIVE_API_KEY set)")
    return MarketSimulator(cache=cache)
