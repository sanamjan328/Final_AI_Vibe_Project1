import asyncio
import logging
import numpy as np
from datetime import datetime, timezone
from typing import NamedTuple

from .interface import MarketDataSource
from .cache import PriceCache
from .models import PriceUpdate, DailyBar

logger = logging.getLogger(__name__)

SECONDS_PER_YEAR = 252 * 6.5 * 3600  # ~5.9M trading seconds/year
TICK_INTERVAL = 0.5                   # seconds between price updates

# (seed_price, annual_drift, annual_volatility)
TICKER_PARAMS: dict[str, tuple[float, float, float]] = {
    "AAPL":  (190.00, 0.15, 0.25),
    "GOOGL": (175.00, 0.12, 0.28),
    "MSFT":  (415.00, 0.18, 0.22),
    "AMZN":  (185.00, 0.20, 0.30),
    "TSLA":  (250.00, 0.08, 0.55),   # high vol
    "NVDA":  (875.00, 0.35, 0.50),   # high growth + vol
    "META":  (520.00, 0.25, 0.32),
    "JPM":   (200.00, 0.10, 0.20),   # lower vol (financials)
    "V":     (270.00, 0.12, 0.18),   # lower vol (payments)
    "NFLX":  (700.00, 0.15, 0.38),
}

#         AAPL   GOOGL  MSFT   AMZN   TSLA   NVDA   META   JPM    V      NFLX
CORRELATION_MATRIX = np.array([
    [1.00,  0.65,  0.70,  0.55,  0.45,  0.60,  0.60,  0.30,  0.35,  0.50],
    [0.65,  1.00,  0.65,  0.60,  0.40,  0.55,  0.65,  0.25,  0.30,  0.55],
    [0.70,  0.65,  1.00,  0.55,  0.42,  0.60,  0.58,  0.30,  0.32,  0.48],
    [0.55,  0.60,  0.55,  1.00,  0.40,  0.50,  0.60,  0.25,  0.35,  0.60],
    [0.45,  0.40,  0.42,  0.40,  1.00,  0.55,  0.38,  0.20,  0.22,  0.40],
    [0.60,  0.55,  0.60,  0.50,  0.55,  1.00,  0.52,  0.25,  0.28,  0.45],
    [0.60,  0.65,  0.58,  0.60,  0.38,  0.52,  1.00,  0.25,  0.30,  0.58],
    [0.30,  0.25,  0.30,  0.25,  0.20,  0.25,  0.25,  1.00,  0.65,  0.22],
    [0.35,  0.30,  0.32,  0.35,  0.22,  0.28,  0.30,  0.65,  1.00,  0.28],
    [0.50,  0.55,  0.48,  0.60,  0.40,  0.45,  0.58,  0.22,  0.28,  1.00],
])
# Row/column order matches list(TICKER_PARAMS.keys())

P_EVENT = 0.002          # ~0.2% chance of shock per ticker per tick (~1/4 min)
EVENT_REVERT_TICKS = 10  # suppress drift for 5 seconds after a shock


class _TickerState(NamedTuple):
    price: float
    drift: float   # per-tick drift, pre-computed at start
    vol: float     # per-tick volatility, pre-computed at start
    revert: int    # ticks remaining in post-shock mean-reversion window


class MarketSimulator(MarketDataSource):
    """Synthetic price engine using correlated GBM.

    Default tickers use a shared 10x10 correlation matrix.
    Unknown tickers added at runtime are assigned a default correlation of 0.3
    with all others and the generic parameters (seed=100, drift=12%, vol=30%).
    """

    def __init__(self, cache: PriceCache) -> None:
        self._cache = cache
        self._tickers: list[str] = []
        self._states: dict[str, _TickerState] = {}
        self._cholesky: np.ndarray | None = None
        self._task: asyncio.Task | None = None

    async def start(self, tickers: list[str]) -> None:
        self._init_tickers(tickers)
        self._task = asyncio.create_task(self._tick_loop())
        logger.info("MarketSimulator started with %d tickers", len(self._tickers))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MarketSimulator stopped")

    def add_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker not in self._states:
            self._states[ticker] = self._make_state(ticker)
            self._tickers.append(ticker)
            self._rebuild_cholesky()

    def remove_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        if ticker in self._states:
            del self._states[ticker]
            self._tickers = [t for t in self._tickers if t != ticker]
            self._rebuild_cholesky()

    async def get_daily_bars(self, ticker: str, from_date: str, to_date: str) -> list[DailyBar]:
        return []  # no historical data in simulator

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _make_state(self, ticker: str) -> _TickerState:
        seed_price, annual_drift, annual_vol = TICKER_PARAMS.get(
            ticker, (100.0, 0.12, 0.30)
        )
        drift_per_tick = (annual_drift - 0.5 * annual_vol ** 2) * (TICK_INTERVAL / SECONDS_PER_YEAR)
        vol_per_tick = annual_vol * (TICK_INTERVAL / SECONDS_PER_YEAR) ** 0.5
        return _TickerState(price=seed_price, drift=drift_per_tick, vol=vol_per_tick, revert=0)

    def _init_tickers(self, tickers: list[str]) -> None:
        self._tickers = [t.upper() for t in tickers]
        for ticker in self._tickers:
            self._states[ticker] = self._make_state(ticker)
        self._rebuild_cholesky()

    def _rebuild_cholesky(self) -> None:
        """Recompute the Cholesky factor whenever the ticker list changes."""
        n = len(self._tickers)
        if n == 0:
            self._cholesky = None
            return

        default_order = list(TICKER_PARAMS.keys())
        default_idx = {t: i for i, t in enumerate(default_order)}

        C = np.eye(n)
        for i, ti in enumerate(self._tickers):
            for j, tj in enumerate(self._tickers):
                if i == j:
                    continue
                if ti in default_idx and tj in default_idx:
                    C[i, j] = CORRELATION_MATRIX[default_idx[ti], default_idx[tj]]
                else:
                    C[i, j] = 0.3  # default cross-asset correlation for unknown tickers

        self._cholesky = np.linalg.cholesky(C)

    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            updates = self._compute_tick()
            if updates:
                await self._cache.update(updates)

    def _compute_tick(self) -> list[PriceUpdate]:
        n = len(self._tickers)
        if n == 0 or self._cholesky is None:
            return []

        # Draw correlated normals for this tick
        z = self._cholesky @ np.random.standard_normal(n)

        now = datetime.now(tz=timezone.utc)
        updates: list[PriceUpdate] = []
        new_states: dict[str, _TickerState] = {}

        for i, ticker in enumerate(self._tickers):
            state = self._states[ticker]

            # Shock event: override GBM with a sudden ±5% jump
            if np.random.random() < P_EVENT:
                shock_pct = np.random.uniform(-0.05, 0.05)
                new_price = max(state.price * (1 + shock_pct), 0.01)
                change = new_price - state.price
                updates.append(PriceUpdate(
                    ticker=ticker,
                    price=round(new_price, 4),
                    prev_price=round(state.price, 4),
                    timestamp=now,
                    change=round(change, 4),
                    change_pct=round(shock_pct * 100, 4),
                ))
                new_states[ticker] = _TickerState(
                    price=new_price, drift=state.drift,
                    vol=state.vol, revert=EVENT_REVERT_TICKS,
                )
                continue

            # Normal GBM step
            effective_drift = 0.0 if state.revert > 0 else state.drift
            log_return = effective_drift + state.vol * z[i]
            new_price = max(state.price * np.exp(log_return), 0.01)
            change = new_price - state.price
            change_pct = (change / state.price * 100) if state.price else 0.0

            updates.append(PriceUpdate(
                ticker=ticker,
                price=round(new_price, 4),
                prev_price=round(state.price, 4),
                timestamp=now,
                change=round(change, 4),
                change_pct=round(change_pct, 4),
            ))
            new_states[ticker] = _TickerState(
                price=new_price, drift=state.drift,
                vol=state.vol, revert=max(0, state.revert - 1),
            )

        for ticker, state in new_states.items():
            self._states[ticker] = state

        return updates
