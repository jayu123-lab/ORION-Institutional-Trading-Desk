"""Live gateway safety-lock tests + async paper engine flow."""

import pytest

from core.config import get_settings
from core.execution.gateway import LiveBrokerGateway, LiveModeDisabled
from core.execution.models import OrderRequest, OrderSide, OrderType


def _order() -> OrderRequest:
    return OrderRequest(
        client_order_id="gw-1", asset="XAUUSD", side=OrderSide.BUY,
        order_type=OrderType.MARKET, qty=1.0,
    )


@pytest.mark.asyncio
async def test_live_gateway_locked_by_default(monkeypatch):
    monkeypatch.setenv("ORION_LIVE_MODE", "false")
    get_settings.cache_clear()
    gw = LiveBrokerGateway()
    assert not gw.unlocked
    with pytest.raises(LiveModeDisabled):
        await gw.submit_order(_order())
    with pytest.raises(LiveModeDisabled):
        await gw.cancel_order("x")
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_gateway_refuses_wrong_token(monkeypatch):
    monkeypatch.setenv("ORION_LIVE_MODE", "true")
    monkeypatch.setenv("ORION_LIVE_CONFIRM_TOKEN", "correct-horse")
    get_settings.cache_clear()
    try:
        gw = LiveBrokerGateway()
        assert gw.unlocked  # flag+token configured, but...
        with pytest.raises(LiveModeDisabled):
            await gw.submit_order(_order(), human_token="wrong-token")
        # even the correct token must hit the Phase-5 wall (no transport)
        with pytest.raises(LiveModeDisabled, match="Phase"):
            await gw.submit_order(_order(), human_token="correct-horse")
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_live_gateway_token_config_missing(monkeypatch):
    monkeypatch.setenv("ORION_LIVE_MODE", "true")
    monkeypatch.setenv("ORION_LIVE_CONFIRM_TOKEN", "")
    get_settings.cache_clear()
    try:
        gw = LiveBrokerGateway()
        assert not gw.unlocked
        with pytest.raises(LiveModeDisabled):
            await gw.submit_order(_order(), human_token=None)
    finally:
        get_settings.cache_clear()
