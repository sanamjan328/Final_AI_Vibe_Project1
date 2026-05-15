import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from app.market.cache import PriceCache
from app.market.massive_client import MassiveClient, BASE_URL


def _make_client(api_key: str = "test-key", poll_interval: float = 999.0) -> tuple[MassiveClient, PriceCache]:
    cache = PriceCache()
    client = MassiveClient(api_key=api_key, cache=cache, poll_interval=poll_interval)
    return client, cache


SAMPLE_SNAPSHOT = {
    "status": "OK",
    "count": 1,
    "tickers": [
        {
            "ticker": "AAPL",
            "todaysChange": 1.23,
            "todaysChangePerc": 0.65,
            "updated": 1_700_000_000_000_000_000,  # nanoseconds
            "day": {"o": 189.0, "h": 191.0, "l": 188.0, "c": 190.5, "v": 50_000_000, "vw": 190.1},
            "prevDay": {"o": 188.0, "h": 190.0, "l": 187.0, "c": 189.27, "v": 48_000_000, "vw": 188.9},
            "lastTrade": {"p": 190.54, "s": 100, "t": 1_700_000_000_000_000_000},
        }
    ],
}


# ---------------------------------------------------------------------------
# _parse_snapshots — happy path
# ---------------------------------------------------------------------------

def test_parse_snapshots_uses_last_trade_price():
    client, _ = _make_client()
    updates = client._parse_snapshots(SAMPLE_SNAPSHOT)
    assert len(updates) == 1
    u = updates[0]
    assert u.ticker == "AAPL"
    assert u.price == 190.54       # from lastTrade.p
    assert u.prev_price == 189.27  # from prevDay.c
    assert u.change == 1.23        # from todaysChange
    assert u.change_pct == 0.65    # from todaysChangePerc
    assert u.direction == "up"


def test_parse_snapshots_falls_back_to_day_close_when_no_last_trade():
    client, _ = _make_client()
    data = {
        "status": "OK",
        "tickers": [
            {
                "ticker": "MSFT",
                "todaysChange": -2.10,
                "todaysChangePerc": -0.50,
                "updated": 0,
                "day": {"c": 413.5, "o": 415.0, "h": 416.0, "l": 412.0, "v": 20_000_000},
                "prevDay": {"c": 415.6},
                # no lastTrade field
            }
        ],
    }
    updates = client._parse_snapshots(data)
    assert len(updates) == 1
    assert updates[0].price == 413.5   # fell back to day.c
    assert updates[0].prev_price == 415.6
    assert updates[0].change == -2.10
    assert updates[0].change_pct == -0.50


def test_parse_snapshots_computes_change_when_field_missing():
    """When todaysChange/todaysChangePerc are absent, compute from price diff."""
    client, _ = _make_client()
    data = {
        "status": "OK",
        "tickers": [
            {
                "ticker": "GOOGL",
                "updated": 0,
                "day": {"c": 176.0},
                "prevDay": {"c": 175.0},
                # no todaysChange, no lastTrade
            }
        ],
    }
    updates = client._parse_snapshots(data)
    assert len(updates) == 1
    u = updates[0]
    assert u.price == 176.0
    assert u.prev_price == 175.0
    assert abs(u.change - 1.0) < 0.001
    assert abs(u.change_pct - (1.0 / 175.0 * 100)) < 0.01


def test_parse_snapshots_timestamp_from_nanoseconds():
    client, _ = _make_client()
    ns = 1_700_000_000_000_000_000
    expected_ts = datetime.fromtimestamp(ns / 1e9, tz=timezone.utc)
    updates = client._parse_snapshots(SAMPLE_SNAPSHOT)
    assert updates[0].timestamp == expected_ts


def test_parse_snapshots_zero_updated_uses_now():
    client, _ = _make_client()
    data = {
        "status": "OK",
        "tickers": [
            {
                "ticker": "AAPL",
                "updated": 0,
                "day": {"c": 190.0},
                "prevDay": {"c": 189.0},
            }
        ],
    }
    before = datetime.now(timezone.utc)
    updates = client._parse_snapshots(data)
    after = datetime.now(timezone.utc)
    assert before <= updates[0].timestamp <= after


def test_parse_snapshots_skips_malformed_entries():
    client, _ = _make_client()
    data = {
        "status": "OK",
        "tickers": [
            {"ticker": "BROKEN"},  # missing day / prevDay — will raise KeyError
            {
                "ticker": "AAPL",
                "updated": 0,
                "day": {"c": 190.0},
                "prevDay": {"c": 189.0},
            },
        ],
    }
    updates = client._parse_snapshots(data)
    # BROKEN should be skipped; AAPL should be parsed
    assert len(updates) == 1
    assert updates[0].ticker == "AAPL"


def test_parse_snapshots_empty_tickers_list():
    client, _ = _make_client()
    updates = client._parse_snapshots({"status": "OK", "tickers": []})
    assert updates == []


def test_parse_snapshots_prices_are_rounded():
    client, _ = _make_client()
    data = {
        "status": "OK",
        "tickers": [
            {
                "ticker": "AAPL",
                "updated": 0,
                "day": {"c": 190.123456789},
                "prevDay": {"c": 189.987654321},
            }
        ],
    }
    updates = client._parse_snapshots(data)
    # Prices should be rounded to 4 decimal places
    assert updates[0].price == round(190.123456789, 4)
    assert updates[0].prev_price == round(189.987654321, 4)


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------

def test_add_ticker_normalises_to_upper():
    client, _ = _make_client()
    client._tickers = set()
    client.add_ticker("aapl")
    assert "AAPL" in client._tickers


def test_add_ticker_idempotent():
    client, _ = _make_client()
    client._tickers = {"AAPL"}
    client.add_ticker("AAPL")
    assert client._tickers == {"AAPL"}


def test_remove_ticker_normalises_to_upper():
    client, _ = _make_client()
    client._tickers = {"AAPL"}
    client.remove_ticker("aapl")
    assert "AAPL" not in client._tickers


def test_remove_ticker_nonexistent_is_safe():
    client, _ = _make_client()
    client._tickers = {"AAPL"}
    client.remove_ticker("XYZ")  # should not raise
    assert "AAPL" in client._tickers


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_populates_tickers():
    client, _ = _make_client()
    # Use a very long poll interval so the loop doesn't actually fire
    with patch.object(client, "_poll_loop", new_callable=AsyncMock):
        await client.start(["AAPL", "MSFT"])
    assert client._tickers == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_start_normalises_tickers_to_upper():
    client, _ = _make_client()
    with patch.object(client, "_poll_loop", new_callable=AsyncMock):
        await client.start(["aapl", "msft"])
    assert client._tickers == {"AAPL", "MSFT"}


@pytest.mark.asyncio
async def test_stop_cancels_task():
    client, _ = _make_client()
    cancelled = False

    async def fake_loop():
        nonlocal cancelled
        try:
            await asyncio.sleep(9999)
        except asyncio.CancelledError:
            cancelled = True
            raise

    client._task = asyncio.create_task(fake_loop())
    await client.stop()
    assert cancelled


@pytest.mark.asyncio
async def test_stop_when_not_started_is_safe():
    client, _ = _make_client()
    await client.stop()  # no task — should not raise


# ---------------------------------------------------------------------------
# get_daily_bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_daily_bars_returns_bars():
    client, _ = _make_client()
    agg_data = {
        "results": [
            {"t": 1_700_006_400_000, "o": 189.0, "h": 191.0, "l": 188.0, "c": 190.5, "v": 50_000_000, "vw": 190.1},
        ]
    }
    mock_response = MagicMock()
    mock_response.json.return_value = agg_data
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        bars = await client.get_daily_bars("AAPL", "2025-01-01", "2025-01-31")

    assert len(bars) == 1
    bar = bars[0]
    assert bar.ticker == "AAPL"
    assert bar.open == 189.0
    assert bar.high == 191.0
    assert bar.low == 188.0
    assert bar.close == 190.5
    assert bar.volume == 50_000_000
    assert bar.vwap == 190.1


@pytest.mark.asyncio
async def test_get_daily_bars_returns_empty_on_error():
    client, _ = _make_client()
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.RequestError("network error"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        bars = await client.get_daily_bars("AAPL", "2025-01-01", "2025-01-31")

    assert bars == []


@pytest.mark.asyncio
async def test_get_daily_bars_empty_results():
    client, _ = _make_client()
    mock_response = MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        bars = await client.get_daily_bars("AAPL", "2025-01-01", "2025-01-31")

    assert bars == []


# ---------------------------------------------------------------------------
# _fetch_snapshots error handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_snapshots_clears_tickers_on_403():
    client, _ = _make_client()
    client._tickers = {"AAPL"}

    mock_response = MagicMock()
    mock_response.status_code = 403
    error = httpx.HTTPStatusError("forbidden", request=MagicMock(), response=mock_response)

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=error)

    result = await client._fetch_snapshots(mock_http)
    assert result == []
    assert len(client._tickers) == 0  # tickers cleared to prevent hammering


@pytest.mark.asyncio
async def test_fetch_snapshots_returns_empty_on_network_error():
    client, _ = _make_client()
    client._tickers = {"AAPL"}

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(side_effect=httpx.RequestError("connection refused"))

    with patch("asyncio.sleep", new_callable=AsyncMock):
        result = await client._fetch_snapshots(mock_http)

    assert result == []


@pytest.mark.asyncio
async def test_fetch_snapshots_returns_empty_on_non_ok_status():
    client, _ = _make_client()
    client._tickers = {"AAPL"}

    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "ERROR", "tickers": []}
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await client._fetch_snapshots(mock_http)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_snapshots_returns_parsed_updates_on_success():
    client, cache = _make_client()
    client._tickers = {"AAPL"}

    mock_response = MagicMock()
    mock_response.json.return_value = SAMPLE_SNAPSHOT
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)

    result = await client._fetch_snapshots(mock_http)
    assert len(result) == 1
    assert result[0].ticker == "AAPL"
