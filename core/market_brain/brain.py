"""MarketBrain â€” deterministic aggregation into a single MarketState.

The CIO (and any analyst) must receive MarketState BEFORE forming a view.
No LLM involvement: everything here is math over stored/fetched market data.

Inputs are read in this priority order:
1. injected data (tests / callers that already hold fresh feeds)
2. DB (quotes + candles tables)
3. live providers via the market-data registry (last resort, marked)

Outputs carry provenance per component (spec PRIORITY 2).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select

from core.config import get_settings
from core.market_brain.engines import (
    data_quality_score,
    liquidity_score,
    macro_score,
    momentum_score,
    range_contraction_metric,
    relative_volume_metric,
    risk_score,
)
from core.market_brain.state import (
    ComponentScore,
    MarketState,
    RegimeLabel,
    RiskMode,
    VolatilityState,
)
from core.memory.models import Candle as DBCandle
from core.memory.models import Quote as DBQuote
from core.provenance import ProvenanceType

logger = logging.getLogger("orion.market_brain")

# symbols required to compute the global picture (missing ones lower data_quality)
MACRO_SYMBOLS = ("DXY", "US10Y", "VIX", "SPX")


class MarketBrain:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    # ------------------------------------------------------------- public API
    async def build(self, scope: str) -> MarketState:
        scope_candles = self._candles_from_db(scope.upper())
        scope_quote = self._latest_quote(scope.upper())
        macro_closes = {s: self._closes_from_db(s) for s in MACRO_SYMBOLS}
        benchmark_closes = macro_closes.get("SPX") or []
        return self.compose(
            scope=scope.upper(),
            scope_closes=[c.close for c in scope_candles],
            scope_candles=scope_candles,
            spread_bps=self._spread_bps(scope_quote),
            macro_closes={k: v for k, v in macro_closes.items() if v},
            benchmark_closes=benchmark_closes,
            quote_freshness=self._freshness([scope_quote]),
        )

    # ------------------------------------------------------------ composition
    def compose(
        self,
        *,
        scope: str,
        scope_closes: list[float],
        scope_candles: list,
        spread_bps: float | None,
        macro_closes: dict[str, list[float]],
        benchmark_closes: list[float],
        quote_freshness: list[float | None] | None = None,
    ) -> MarketState:
        components: list[ComponentScore] = []

        # --- regime (from core.regime multi-factor detector)
        regime_label = RegimeLabel.INSUFFICIENT_DATA
        vol_state = VolatilityState.NORMAL
        if len(scope_candles) >= 30:
            from core.regime import classify as classify_regime

            reg = classify_regime(scope, scope_candles)
            regime_label = (
                RegimeLabel.TRENDING if reg.trend == "TRENDING" else RegimeLabel.RANGING
            )
            vol_state = {
                "HIGH_VOLATILITY": VolatilityState.HIGH,
                "LOW_VOLATILITY": VolatilityState.LOW,
            }.get(reg.volatility, VolatilityState.NORMAL)
            components.append(
                ComponentScore(
                    name="regime",
                    value=round(reg.confidence, 3),
                    scale="0_1",
                    provenance=ProvenanceType.DERIVED,
                    detail={
                        "trend": reg.trend,
                        "volatility": reg.volatility,
                        "method": reg.method,
                        **reg.metrics,
                    },
                )
            )

        # --- momentum
        mom = momentum_score(scope_closes) if len(scope_closes) >= 11 else None
        if mom is not None:
            components.append(
                ComponentScore(
                    name="momentum", value=round(mom, 3), scale="-1_1", provenance=ProvenanceType.DERIVED
                )
            )

        # --- liquidity
        rel_vol = relative_volume_metric(scope_candles)
        rng_contraction = range_contraction_metric(scope_candles)
        liq = liquidity_score(
            spread_bps=spread_bps,
            relative_volume=rel_vol,
            range_contraction=rng_contraction,
        )
        if liq is not None:
            components.append(
                ComponentScore(
                    name="liquidity",
                    value=round(liq, 3),
                    scale="0_1",
                    provenance=ProvenanceType.DERIVED,
                    detail={
                        "spread_bps": round(spread_bps, 2) if spread_bps is not None else None,
                        "relative_volume": round(rel_vol, 3) if rel_vol is not None else None,
                    },
                )
            )

        # --- macro score (only from REAL stored series; missing â†’ None)
        dxy_roc = _roc(macro_closes.get("DXY"), 20)
        us10y_chg = _abs_change(macro_closes.get("US10Y"), 5)
        vix_level = macro_closes.get("VIX", [])[-1:] or None
        spx_mom = (
            momentum_score(macro_closes["SPX"]) if len(macro_closes.get("SPX", [])) >= 11 else None
        )
        macro_v, macro_detail = macro_score(
            dxy_roc=dxy_roc,
            us10y_change=us10y_chg,
            vix_level=vix_level[0] if vix_level else None,
            spx_momentum=spx_mom,
        )
        if macro_v is not None:
            components.append(
                ComponentScore(
                    name="macro",
                    value=round(macro_v, 3),
                    scale="-1_1",
                    provenance=ProvenanceType.DERIVED,
                    detail=dict(macro_detail),
                )
            )

        # --- positioning: NO institutional feed wired yet â€” honest NOT AVAILABLE
        components.append(
            ComponentScore(
                name="positioning",
                value=None,
                scale="0_1",
                provenance=ProvenanceType.INFERRED,
                detail={"availability": "NOT AVAILABLE", "reason": "no COT/OI feed configured"},
            )
        )

        # --- risk score
        drawdown = _drawdown_pct(scope_closes)
        risk_v, risk_detail = risk_score(
            volatility_state=vol_state.value,
            drawdown_pct=drawdown,
            macro_stress=macro_v,
            feed_degraded=(quote_freshness is not None and any(f is None for f in quote_freshness)),
        )
        components.append(
            ComponentScore(
                name="risk",
                value=round(risk_v, 3),
                scale="-1_1",
                provenance=ProvenanceType.DERIVED,
                detail=dict(risk_detail),
            )
        )

        # --- data quality
        dq = data_quality_score(quote_freshness or [None])
        dq = max(dq, 0.2 if len(scope_closes) >= 30 else 0.0)

        risk_mode = (
            RiskMode.RISK_OFF
            if (macro_v is not None and macro_v <= -0.25) or risk_v <= -0.40
            else RiskMode.RISK_ON
        )

        return MarketState(
            scope=scope,
            ts=datetime.now(UTC),
            regime=regime_label,
            risk_mode=risk_mode,
            volatility=vol_state,
            macro_score=round(macro_v, 3) if macro_v is not None else None,
            liquidity_score=round(liq, 3) if liq is not None else None,
            positioning_score=None,  # never fabricated
            risk_score=round(risk_v, 3),
            momentum_score=round(mom, 3) if mom is not None else None,
            data_quality=dq,
            components=components,
        )

    # ------------------------------------------------------------------ io
    def _candles_from_db(self, symbol: str, limit: int = 200) -> list:
        with self.session_factory() as session:
            rows = (
                session.execute(
                    select(DBCandle)
                    .where(DBCandle.symbol == symbol)
                    .order_by(desc(DBCandle.ts_open))
                    .limit(limit)
                )
                .scalars()
                .all()
            )
        return sorted(rows, key=lambda r: r.ts_open)

    def _closes_from_db(self, symbol: str, limit: int = 120) -> list[float]:
        return [c.close for c in self._candles_from_db(symbol, limit)]

    def _latest_quote(self, symbol: str):
        with self.session_factory() as session:
            return (
                session.execute(
                    select(DBQuote)
                    .where(DBQuote.symbol == symbol)
                    .order_by(desc(DBQuote.id))
                    .limit(1)
                )
                .scalars()
                .first()
            )

    def _spread_bps(self, q) -> float | None:
        if q is None or q.bid is None or q.ask is None or not q.price:
            return None
        return abs(q.ask - q.bid) / q.price * 10_000

    def _freshness(self, quotes: list) -> list[float | None]:
        stale_sec = get_settings().monitor_quote_staleness_sec
        now = datetime.now(UTC)
        out: list[float | None] = []
        for q in quotes:
            if q is None:
                out.append(None)
                continue
            ts = q.ts_source if q.ts_source.tzinfo else q.ts_source.replace(tzinfo=UTC)
            age = (now - ts).total_seconds()
            out.append(age if age <= stale_sec * 4 else None)
        return out


# ------------------------------------------------------------------ helpers


def _roc(closes: list[float] | None, lookback: int) -> float | None:
    import math

    if not closes or len(closes) <= lookback:
        return None
    a, b = closes[-(lookback + 1)], closes[-1]
    return math.log(b / a) if a > 0 and b > 0 else None


def _abs_change(closes: list[float] | None, lookback: int) -> float | None:
    if not closes or len(closes) <= lookback:
        return None
    return closes[-1] - closes[-(lookback + 1)]


def _drawdown_pct(closes: list[float]) -> float | None:
    if len(closes) < 20:
        return None
    peak = max(closes[-60:])
    last = closes[-1]
    return (last - peak) / peak if peak > 0 else None
