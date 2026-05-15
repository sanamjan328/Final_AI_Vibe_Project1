import os
from unittest.mock import patch
import pytest
from app.market.cache import PriceCache
from app.market.factory import create_market_data_source
from app.market.simulator import MarketSimulator
from app.market.massive_client import MassiveClient


def test_factory_returns_simulator_when_no_key():
    cache = PriceCache()
    with patch.dict(os.environ, {}, clear=True):
        source = create_market_data_source(cache)
    assert isinstance(source, MarketSimulator)


def test_factory_returns_simulator_when_key_is_empty_string():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": ""}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MarketSimulator)


def test_factory_returns_simulator_when_key_is_whitespace():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": "   "}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MarketSimulator)


def test_factory_returns_massive_client_when_key_set():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key-123"}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MassiveClient)


def test_factory_massive_client_uses_default_poll_interval():
    cache = PriceCache()
    # clear=True ensures MASSIVE_POLL_INTERVAL is absent so the default kicks in
    with patch.dict(os.environ, {"MASSIVE_API_KEY": "test-key"}, clear=True):
        source = create_market_data_source(cache)
    assert isinstance(source, MassiveClient)
    assert source._poll_interval == 15.0


def test_factory_massive_client_uses_custom_poll_interval():
    cache = PriceCache()
    env = {"MASSIVE_API_KEY": "test-key", "MASSIVE_POLL_INTERVAL": "5.0"}
    with patch.dict(os.environ, env, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MassiveClient)
    assert source._poll_interval == 5.0


def test_factory_returns_market_data_source_interface():
    """Both implementations should satisfy the MarketDataSource interface."""
    from app.market.interface import MarketDataSource
    cache = PriceCache()

    with patch.dict(os.environ, {}, clear=True):
        sim = create_market_data_source(cache)
    assert isinstance(sim, MarketDataSource)

    with patch.dict(os.environ, {"MASSIVE_API_KEY": "key"}, clear=False):
        massive = create_market_data_source(cache)
    assert isinstance(massive, MarketDataSource)


def test_factory_massive_client_has_correct_api_key():
    cache = PriceCache()
    with patch.dict(os.environ, {"MASSIVE_API_KEY": "my-secret-key"}, clear=False):
        source = create_market_data_source(cache)
    assert isinstance(source, MassiveClient)
    assert source._api_key == "my-secret-key"
