"""InstitutionalPositioningAgent â€” honest positioning intelligence (PRIORITY 5).

Responsibilities: COT, Managed Money, Commercials, Leveraged Funds,
CTA positioning, Open Interest, Dealer Gamma, Options OI, ETF flows,
fund flows.

Hard rule (AGENTS.md #1): never invent figures. Every metric carries an
explicit availability label:

- VERIFIED DATA    : read from an official source this cycle (CFTC today)
- DERIVED DATA     : computed deterministically from verified inputs
- NOT AVAILABLE    : no feed configured â€” we say so instead of guessing

Special focus assets: XAUUSD/GC/MGC, NASDAQ/NQ, SPX/ES, BTC, XRP.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from providers.positioning.cftc import CFTC_MARKET_MAP, CotRecord, fetch_cot


class DataAvailability:
    VERIFIED = "VERIFIED DATA"
    DERIVED = "DERIVED DATA"
    NOT_AVAILABLE = "NOT AVAILABLE"


class PositioningMetric(BaseModel):
    name: str
    value: str  # formatted value or the availability label
    availability: str  # VERIFIED DATA | DERIVED DATA | NOT AVAILABLE
    detail: str | None = None


class AssetPositioningReport(BaseModel):
    symbol: str
    metrics: list[PositioningMetric]
    overall_availability: str
    notes: list[str] = []


class InstitutionalPositioningAgent:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def report(self, symbol: str) -> AssetPositioningReport:
        symbol_u = symbol.upper()
        cot_record: CotRecord | None = None
        cot_note: str | None = None
        try:
            if self._client is not None:
                cot_record = await fetch_cot(symbol_u, self._client)
            else:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    cot_record = await fetch_cot(symbol_u, client)
        except Exception as exc:  # noqa: BLE001 - network must not kill the report
            cot_note = f"CFTC fetch failed: {exc}"

        metrics: list[PositioningMetric] = []
        if cot_record is not None:
            metrics.extend(self._cot_metrics(cot_record))
        elif symbol_u in CFTC_MARKET_MAP and cot_note is None:
            metrics.append(
                PositioningMetric(
                    name="COT", value=DataAvailability.NOT_AVAILABLE,
                    availability=DataAvailability.NOT_AVAILABLE,
                    detail=f"symbol {symbol_u} has no verified CFTC market mapping",
                )
            )
        else:
            metrics.append(
                PositioningMetric(
                    name="COT",
                    value=cot_note or DataAvailability.NOT_AVAILABLE,
                    availability=DataAvailability.NOT_AVAILABLE,
                )
            )

        # everything without a wired feed â€” explicit, never fabricated
        for name in (
            "Dealer Gamma",
            "Options OI",
            "ETF Flows",
            "Fund Flows",
            "CTA Positioning",
            "Leveraged Funds Detail",
        ):
            metrics.append(
                PositioningMetric(
                    name=name,
                    value=DataAvailability.NOT_AVAILABLE,
                    availability=DataAvailability.NOT_AVAILABLE,
                    detail="no provider configured",
                )
            )

        verified_count = sum(1 for m in metrics if m.availability == DataAvailability.VERIFIED)
        if verified_count:
            overall = DataAvailability.VERIFIED
        elif any(m.availability == DataAvailability.DERIVED for m in metrics):
            overall = DataAvailability.DERIVED
        else:
            overall = DataAvailability.NOT_AVAILABLE

        return AssetPositioningReport(
            symbol=symbol_u,
            metrics=metrics,
            overall_availability=overall,
            notes=["weekly COT cadence: positions lag price up to ~6 days"],
        )

    def _cot_metrics(self, rec: CotRecord) -> list[PositioningMetric]:
        out = [
            PositioningMetric(
                name="COT Open Interest",
                value=f"{rec.open_interest:,}",
                availability=DataAvailability.VERIFIED,
                detail=f"{rec.cftc_market} @ {rec.report_date} ({rec.dataset} dataset)",
            )
        ]
        if rec.managed_money_net is not None:
            out.append(
                PositioningMetric(
                    name="Managed Money Net",
                    value=f"{rec.managed_money_net:+,}",
                    availability=DataAvailability.VERIFIED,
                    detail=(
                        f"long {rec.managed_money_long:,} / short "
                        f"{rec.managed_money_short:,} @ {rec.report_date}"
                    ),
                )
            )
        if rec.swap_long is not None or rec.swap_short is not None:
            out.append(
                PositioningMetric(
                    name="Swap Dealer Net",
                    value=f"{(rec.swap_long or 0) - (rec.swap_short or 0):+,}",
                    availability=DataAvailability.VERIFIED,
                    detail=f"long {rec.swap_long or 0:,} / short {rec.swap_short or 0:,}",
                )
            )
        if rec.noncommercial_net is not None:
            out.append(
                PositioningMetric(
                    name="Noncommercial Net",
                    value=f"{rec.noncommercial_net:+,}",
                    availability=DataAvailability.VERIFIED,
                    detail=(
                        f"long {rec.noncommercial_long:,} / short "
                        f"{rec.noncommercial_short:,} @ {rec.report_date}"
                    ),
                )
            )
        if rec.open_interest and rec.managed_money_long is not None:
            pct = rec.managed_money_long / rec.open_interest * 100
            out.append(
                PositioningMetric(
                    name="MM Long % of OI",
                    value=f"{pct:.1f}%",
                    availability=DataAvailability.DERIVED,
                    detail="derived: managed money long / total OI",
                )
            )
        return out
