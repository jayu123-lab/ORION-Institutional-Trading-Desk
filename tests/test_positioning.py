"""Tests for CFTC parsing (pure) and the positioning agent."""

import httpx
import pytest

from core.positioning.agent import DataAvailability, InstitutionalPositioningAgent
from providers.positioning.cftc import (
    CFTC_MARKET_MAP,
    parse_disaggregated,
    parse_legacy,
)

# real-shaped rows from the live API (values captured 2026-08-23)
DISAGG_ROW = {
    "market_and_exchange_names": "GOLD - COMMODITY EXCHANGE INC.",
    "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000",
    "open_interest_all": "406260",
    "m_money_positions_long_all": "154595",
    "m_money_positions_short_all": "12947",
    "swap_positions_long_all": "87907",
    "swap__positions_short_all": "247361",
    "producer_merchant_merchant_positions_long_all": "",
}

LEGACY_ROW = {
    "market_and_exchange_names": "MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE",
    "report_date_as_yyyy_mm_dd": "2026-08-18T00:00:00.000",
    "open_interest_all": "32133",
    "noncomm_positions_long_all": "25181",
    "noncomm_positions_short_all": "4321",
    "comm_positions_long_all": "171",
    "comm_positions_short_all": "9000",
}


class TestParsers:
    def test_disaggregated_gold(self):
        rec = parse_disaggregated("XAUUSD", DISAGG_ROW)
        assert rec.managed_money_net == 154595 - 12947
        assert rec.open_interest == 406260
        assert rec.report_date == "2026-08-18"
        assert rec.dataset == "disaggregated"
        assert rec.swap_short == 247361

    def test_legacy_bitcoin(self):
        rec = parse_legacy("BTCUSD", LEGACY_ROW)
        assert rec.noncommercial_net == 25181 - 4321
        assert rec.commercial_long == 171
        assert rec.dataset == "legacy"
        assert rec.managed_money_net is None

    def test_empty_numeric_fields_become_none(self):
        rec = parse_disaggregated("GC", {**DISAGG_ROW, "m_money_positions_long_all": ""})
        assert rec.managed_money_long is None

    def test_market_map_focus_assets(self):
        for sym in ("XAUUSD", "GC", "MGC", "XAGUSD", "SI", "BTCUSD"):
            assert sym in CFTC_MARKET_MAP
        # XRP has no COT market — must stay unmapped (honest NOT AVAILABLE)
        assert "XRPUSD" not in CFTC_MARKET_MAP


@pytest.mark.asyncio
async def test_report_unmapped_symbol_honest():
    agent = InstitutionalPositioningAgent()
    rep = await agent.report("XRPUSD")
    cot = next(m for m in rep.metrics if m.name == "COT")
    assert cot.availability == DataAvailability.NOT_AVAILABLE


def _responder(payload: list[dict]):
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


class TestLiveShapedClient:
    @pytest.mark.asyncio
    async def test_report_with_cftc_data(self):
        transport = _responder([DISAGG_ROW])
        async with httpx.AsyncClient(transport=transport) as client:
            agent = InstitutionalPositioningAgent(client=client)
            rep = await agent.report("XAUUSD")
        mm = next(m for m in rep.metrics if m.name == "Managed Money Net")
        assert mm.availability == DataAvailability.VERIFIED
        assert "+" in mm.value  # net long formatted with sign
        derived = [m for m in rep.metrics if m.availability == DataAvailability.DERIVED]
        assert any("MM Long" in m.name for m in derived)
        gamma = next(m for m in rep.metrics if m.name == "Dealer Gamma")
        assert gamma.availability == DataAvailability.NOT_AVAILABLE
        assert rep.overall_availability == DataAvailability.VERIFIED

    @pytest.mark.asyncio
    async def test_report_network_failure_degrades_not_crashes(self):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline")

        async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
            agent = InstitutionalPositioningAgent(client=client)
            rep = await agent.report("BTCUSD")
        assert rep.overall_availability == DataAvailability.NOT_AVAILABLE
        assert any("fetch failed" in m.value for m in rep.metrics)
