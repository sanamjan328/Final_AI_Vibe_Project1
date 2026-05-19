"""Tests for /api/portfolio endpoints."""

from __future__ import annotations

import pytest


def test_get_portfolio_initial_state(client, seeded_prices):
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    data = r.json()
    assert data["cash_balance"] == pytest.approx(10000.0)
    assert data["positions"] == []
    assert data["total_value"] == pytest.approx(10000.0)


def test_buy_reduces_cash_and_creates_position(client, seeded_prices):
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["error"] is None
    assert body["trade"]["ticker"] == "AAPL"
    assert body["trade"]["side"] == "buy"
    assert body["trade"]["price"] == pytest.approx(200.0)
    assert body["cash_balance"] == pytest.approx(10000.0 - 5 * 200.0)

    pv = client.get("/api/portfolio").json()
    assert len(pv["positions"]) == 1
    pos = pv["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pos["quantity"] == pytest.approx(5.0)
    assert pos["avg_cost"] == pytest.approx(200.0)
    assert pos["current_price"] == pytest.approx(200.0)


def test_buy_insufficient_cash_returns_error(client, seeded_prices):
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1000},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "Insufficient cash" in body["error"]
    assert body["trade"] is None
    assert body["cash_balance"] == pytest.approx(10000.0)


def test_sell_increases_cash_and_reduces_position(client, seeded_prices):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5})

    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["cash_balance"] == pytest.approx(10000.0 - 5 * 200.0 + 2 * 200.0)

    pv = client.get("/api/portfolio").json()
    assert len(pv["positions"]) == 1
    assert pv["positions"][0]["quantity"] == pytest.approx(3.0)


def test_sell_more_than_owned_returns_error(client, seeded_prices):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2})

    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "Insufficient shares" in body["error"]


def test_sell_all_deletes_position(client, seeded_prices):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 5})
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "sell", "quantity": 5})

    pv = client.get("/api/portfolio").json()
    assert pv["positions"] == []
    assert pv["cash_balance"] == pytest.approx(10000.0)


def test_buy_with_no_price_returns_error(client, fresh_cache):
    # No prices in cache.
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "No live price" in body["error"]


def test_buy_averages_cost_on_second_purchase(client, seeded_prices):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2})
    # Bump price up and buy again to verify weighted avg.
    import asyncio
    from tests.api.conftest import make_price
    asyncio.run(seeded_prices.update([make_price("AAPL", 300.0, 200.0)]))
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 2})

    pos = client.get("/api/portfolio").json()["positions"][0]
    assert pos["quantity"] == pytest.approx(4.0)
    # (2 * 200 + 2 * 300) / 4 = 250
    assert pos["avg_cost"] == pytest.approx(250.0)


def test_history_includes_trade_snapshot(client, seeded_prices):
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "side": "buy", "quantity": 1})
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    history = r.json()
    assert len(history) >= 1
    assert history[-1]["total_value"] == pytest.approx(10000.0)


def test_negative_quantity_rejected(client, seeded_prices):
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": -1},
    )
    body = r.json()
    assert body["success"] is False
    assert "positive" in body["error"].lower()


def test_invalid_side_rejected(client, seeded_prices):
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "hold", "quantity": 1},
    )
    body = r.json()
    assert body["success"] is False
    assert "side" in body["error"].lower()
