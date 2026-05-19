"""Tests for /api/watchlist endpoints."""

from __future__ import annotations


def test_list_default_watchlist(client, seeded_prices):
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    rows = r.json()
    tickers = [row["ticker"] for row in rows]
    assert set(tickers) == {
        "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
        "NVDA", "META", "JPM", "V", "NFLX",
    }


def test_list_prices_present_or_null(client, seeded_prices):
    rows = client.get("/api/watchlist").json()
    by_ticker = {r["ticker"]: r for r in rows}
    # Seeded prices: AAPL, GOOGL, MSFT have values; others null.
    assert by_ticker["AAPL"]["price"] == 200.0
    assert by_ticker["AAPL"]["direction"] in ("up", "down", "flat")
    assert by_ticker["TSLA"]["price"] is None
    assert by_ticker["TSLA"]["prev_price"] is None
    assert by_ticker["TSLA"]["change_pct"] is None
    assert by_ticker["TSLA"]["direction"] is None


def test_add_ticker(client, seeded_prices):
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 200
    assert r.json() == {"ticker": "PYPL", "added": True}

    tickers = [row["ticker"] for row in client.get("/api/watchlist").json()]
    assert "PYPL" in tickers


def test_add_duplicate_ticker_is_idempotent(client, seeded_prices):
    client.post("/api/watchlist", json={"ticker": "AAPL"})
    r = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["added"] is False


def test_remove_ticker(client, seeded_prices):
    r = client.delete("/api/watchlist/AAPL")
    assert r.status_code == 200
    assert r.json() == {"ticker": "AAPL", "removed": True}

    tickers = [row["ticker"] for row in client.get("/api/watchlist").json()]
    assert "AAPL" not in tickers


def test_remove_nonexistent_ticker(client, seeded_prices):
    r = client.delete("/api/watchlist/ZZZZ")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticker": "ZZZZ", "removed": False}
