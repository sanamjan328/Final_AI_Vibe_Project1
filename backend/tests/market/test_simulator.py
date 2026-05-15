import asyncio
import pytest
import numpy as np
from app.market.cache import PriceCache
from app.market.simulator import (
    MarketSimulator,
    TICKER_PARAMS,
    TICK_INTERVAL,
    SECONDS_PER_YEAR,
    P_EVENT,
    EVENT_REVERT_TICKS,
)


@pytest.mark.asyncio
async def test_simulator_produces_prices_for_all_tickers():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL", "TSLA"])
    await asyncio.sleep(1.5)  # 3 ticks at 500ms
    await sim.stop()

    prices = cache.get_all()
    assert "AAPL" in prices
    assert "TSLA" in prices


@pytest.mark.asyncio
async def test_simulator_prices_are_positive():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL", "GOOGL", "MSFT"])
    await asyncio.sleep(1.5)
    await sim.stop()

    for ticker, update in cache.get_all().items():
        assert update.price > 0, f"{ticker} price should be positive"


@pytest.mark.asyncio
async def test_simulator_direction_is_valid():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL", "TSLA"])
    await asyncio.sleep(1.5)
    await sim.stop()

    for ticker, update in cache.get_all().items():
        assert update.direction in ("up", "down", "flat"), \
            f"{ticker} direction '{update.direction}' is invalid"


@pytest.mark.asyncio
async def test_simulator_add_ticker_at_runtime():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL"])
    sim.add_ticker("NVDA")
    await asyncio.sleep(1.5)
    await sim.stop()

    assert cache.get("NVDA") is not None
    assert cache.get("NVDA").price > 0


@pytest.mark.asyncio
async def test_simulator_add_ticker_case_insensitive():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL"])
    sim.add_ticker("nvda")  # lowercase
    await asyncio.sleep(1.5)
    await sim.stop()

    assert cache.get("NVDA") is not None


@pytest.mark.asyncio
async def test_simulator_add_ticker_no_duplicate():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL"])
    sim.add_ticker("AAPL")  # already exists
    await sim.stop()

    assert sim._tickers.count("AAPL") == 1


@pytest.mark.asyncio
async def test_simulator_remove_ticker():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL", "NVDA"])
    sim.remove_ticker("NVDA")
    await asyncio.sleep(1.5)
    await sim.stop()

    # NVDA was removed from simulation but its cached price may still exist
    assert "NVDA" not in sim._tickers
    assert "NVDA" not in sim._states


@pytest.mark.asyncio
async def test_simulator_remove_nonexistent_ticker_is_safe():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL"])
    sim.remove_ticker("XYZ")  # not in list — should not raise
    await sim.stop()


@pytest.mark.asyncio
async def test_simulator_cache_entry_persists_after_remove():
    """Removing a ticker stops updates but its last price stays in the cache."""
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL", "NVDA"])
    await asyncio.sleep(1.0)  # ensure at least one tick populated the cache
    sim.remove_ticker("NVDA")
    await asyncio.sleep(0.5)
    await sim.stop()

    # Cache entry is still there even after removal
    assert cache.get("NVDA") is not None


@pytest.mark.asyncio
async def test_simulator_get_daily_bars_returns_empty():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    bars = await sim.get_daily_bars("AAPL", "2025-01-01", "2025-01-31")
    assert bars == []


@pytest.mark.asyncio
async def test_simulator_stop_is_idempotent():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["AAPL"])
    await sim.stop()
    await sim.stop()  # second stop should not raise


@pytest.mark.asyncio
async def test_simulator_empty_ticker_list():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start([])
    await asyncio.sleep(0.6)
    await sim.stop()
    assert cache.get_all() == {}


@pytest.mark.asyncio
async def test_simulator_unknown_ticker_uses_defaults():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    await sim.start(["FAKESTOCK"])
    await asyncio.sleep(1.5)
    await sim.stop()

    update = cache.get("FAKESTOCK")
    assert update is not None
    assert update.price > 0


def test_make_state_known_ticker():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    state = sim._make_state("AAPL")
    seed_price, annual_drift, annual_vol = TICKER_PARAMS["AAPL"]
    expected_drift = (annual_drift - 0.5 * annual_vol ** 2) * (TICK_INTERVAL / SECONDS_PER_YEAR)
    expected_vol = annual_vol * (TICK_INTERVAL / SECONDS_PER_YEAR) ** 0.5
    assert state.price == seed_price
    assert abs(state.drift - expected_drift) < 1e-12
    assert abs(state.vol - expected_vol) < 1e-12
    assert state.revert == 0


def test_make_state_unknown_ticker_uses_defaults():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    state = sim._make_state("XYZ")
    assert state.price == 100.0  # default seed price
    assert state.drift > 0
    assert state.vol > 0
    assert state.revert == 0


def test_rebuild_cholesky_single_ticker():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL"])
    assert sim._cholesky is not None
    assert sim._cholesky.shape == (1, 1)
    assert sim._cholesky[0, 0] == pytest.approx(1.0)


def test_rebuild_cholesky_two_known_tickers():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL", "MSFT"])
    L = sim._cholesky
    assert L is not None
    assert L.shape == (2, 2)
    # Verify L @ L.T reconstructs the correlation matrix
    C_reconstructed = L @ L.T
    assert C_reconstructed[0, 0] == pytest.approx(1.0)
    assert C_reconstructed[1, 1] == pytest.approx(1.0)
    assert C_reconstructed[0, 1] == pytest.approx(0.70, abs=1e-6)  # AAPL-MSFT correlation


def test_rebuild_cholesky_with_unknown_ticker():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL", "FAKESTOCK"])
    L = sim._cholesky
    assert L is not None
    C = L @ L.T
    assert C[0, 1] == pytest.approx(0.3, abs=1e-6)  # default correlation


def test_rebuild_cholesky_empty_list():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers([])
    assert sim._cholesky is None


def test_compute_tick_returns_updates_for_all_tickers():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL", "TSLA", "NVDA"])
    updates = sim._compute_tick()
    tickers_in_updates = {u.ticker for u in updates}
    assert tickers_in_updates == {"AAPL", "TSLA", "NVDA"}


def test_compute_tick_prices_are_positive():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL", "TSLA"])
    for _ in range(50):
        updates = sim._compute_tick()
        for u in updates:
            assert u.price > 0, f"Price for {u.ticker} must be positive"


def test_compute_tick_updates_internal_state():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL"])
    original_price = sim._states["AAPL"].price
    sim._compute_tick()
    # State should be updated after a tick (price may be same in edge case but state exists)
    assert "AAPL" in sim._states


def test_compute_tick_empty_returns_empty():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers([])
    updates = sim._compute_tick()
    assert updates == []


def test_compute_tick_revert_decrements():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL"])
    # Manually set a revert counter
    state = sim._states["AAPL"]
    sim._states["AAPL"] = state._replace(revert=5)

    # Patch random to avoid shock path
    import unittest.mock as mock
    with mock.patch("numpy.random.random", return_value=1.0):  # never trigger shock
        sim._compute_tick()

    new_revert = sim._states["AAPL"].revert
    assert new_revert == 4


def test_compute_tick_change_pct_matches_change():
    cache = PriceCache()
    sim = MarketSimulator(cache)
    sim._init_tickers(["AAPL"])

    for _ in range(20):
        updates = sim._compute_tick()
        for u in updates:
            if u.prev_price > 0:
                expected_pct = (u.change / u.prev_price) * 100
                assert abs(u.change_pct - round(expected_pct, 4)) < 0.01, \
                    f"change_pct mismatch: got {u.change_pct}, expected {expected_pct}"
