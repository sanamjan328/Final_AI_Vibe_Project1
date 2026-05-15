from datetime import datetime, timezone
import pytest
from app.market.models import PriceUpdate, DailyBar


def _make_update(change: float) -> PriceUpdate:
    return PriceUpdate(
        ticker="AAPL",
        price=190.0 + change,
        prev_price=190.0,
        timestamp=datetime.now(timezone.utc),
        change=change,
        change_pct=change / 190.0 * 100,
    )


def test_direction_up():
    u = _make_update(0.5)
    assert u.direction == "up"


def test_direction_down():
    u = _make_update(-0.5)
    assert u.direction == "down"


def test_direction_flat():
    u = _make_update(0.0)
    assert u.direction == "flat"


def test_price_update_fields():
    now = datetime.now(timezone.utc)
    u = PriceUpdate(
        ticker="TSLA",
        price=250.12,
        prev_price=249.88,
        timestamp=now,
        change=0.24,
        change_pct=0.096,
    )
    assert u.ticker == "TSLA"
    assert u.price == 250.12
    assert u.prev_price == 249.88
    assert u.timestamp is now
    assert u.change == 0.24
    assert u.change_pct == 0.096


def test_daily_bar_fields():
    bar = DailyBar(
        ticker="AAPL",
        date="2025-01-15",
        open=189.0,
        high=192.0,
        low=188.5,
        close=191.0,
        volume=55_000_000,
        vwap=190.5,
    )
    assert bar.ticker == "AAPL"
    assert bar.date == "2025-01-15"
    assert bar.open == 189.0
    assert bar.high == 192.0
    assert bar.low == 188.5
    assert bar.close == 191.0
    assert bar.volume == 55_000_000
    assert bar.vwap == 190.5


def test_daily_bar_vwap_optional():
    bar = DailyBar(
        ticker="AAPL",
        date="2025-01-15",
        open=189.0,
        high=192.0,
        low=188.5,
        close=191.0,
        volume=55_000_000,
    )
    assert bar.vwap is None
