"""Deterministic desk analysts for the debate engine.

Each analyst produces a REAL-data-backed opinion: every number cited comes
from the MarketBrain / DB. When an input is missing the opinion says
NOT AVAILABLE instead of guessing. These are the deterministic baseline
voices; LLM agents may later extend them with richer prose, but numbers here
are always machine-computed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.debate.schemas import AgentOpinionSchema, DataSourceRefModel
from core.market_brain.state import MarketState


def _src(
    symbol: str, provider: str | None = None, price: float | None = None
) -> DataSourceRefModel:
    return DataSourceRefModel(
        symbol=symbol,
        provider=provider,
        ts=datetime.now(UTC).isoformat(),
        price=price,
    )


def macro_opinion(ms: MarketState, macro_closes: dict[str, list[float]]) -> AgentOpinionSchema:
    args: list[str] = []
    counter: list[str] = []
    vix_series = macro_closes.get("VIX")
    vix = vix_series[-1] if vix_series else None
    if vix is not None:
        args.append(f"VIX last close {vix:.2f}")
    if ms.macro_score is not None:
        direction = "risk-off pressure" if ms.macro_score < 0 else "supportive backdrop"
        args.append(f"macro score {ms.macro_score} ({direction})")
        counter.append("macro score is a composite of few real feeds; treat as coarse")
    else:
        args.append("macro inputs NOT AVAILABLE — no stored DXY/US10Y/VIX/SPX series")
    bias = "WAIT"
    strength = 30.0
    if ms.macro_score is not None and abs(ms.macro_score) >= 0.25:
        bias = "SHORT" if ms.macro_score < 0 else "LONG"
        strength = min(80.0, 30 + abs(ms.macro_score) * 60)
    return AgentOpinionSchema(
        agent="orion-macro",
        asset=ms.scope,
        timestamp=datetime.now(UTC),
        bias=bias,
        confidence="MODERATE" if len(args) > 1 else "LOW",
        strength=strength,
        time_horizon="SWING",
        arguments=args,
        counter_arguments=counter or ["macro regime can flip on a single data release"],
        required_conditions=["fresh VIX + US10Y series before sizing up"],
        invalidation="macro_score crossing ±0.25 in the opposite direction",
        data_sources=[_src(s) for s in ("DXY", "US10Y", "VIX", "SPX") if s in macro_closes],
        data_quality=ms.data_quality,
    )


def liquidity_opinion(ms: MarketState) -> AgentOpinionSchema:
    if ms.liquidity_score is None:
        return AgentOpinionSchema(
            agent="orion-liquidity",
            asset=ms.scope,
            bias="WAIT",
            confidence="LOW",
            strength=20.0,
            time_horizon="INTRADAY",
            arguments=["liquidity inputs NOT AVAILABLE (no spread/volume/range data)"],
            counter_arguments=[],
            required_conditions=["store quotes with bid/ask to compute spread"],
            invalidation="N/A",
            data_sources=[],
            data_quality=None,
        )
    good = ms.liquidity_score >= 0.5
    comp = next((c for c in ms.components if c.name == "liquidity"), None)
    detail = comp.detail if comp else {}
    return AgentOpinionSchema(
        agent="orion-liquidity",
        asset=ms.scope,
        bias="LONG" if good else "WAIT",  # LONG risk here means 'conditions favour trading'
        confidence="MODERATE",
        strength=(40 + ms.liquidity_score * 40) if good else (70 - ms.liquidity_score * 50),
        time_horizon="INTRADAY",
        arguments=[
            f"liquidity score {ms.liquidity_score}",
            f"spread {detail.get('spread_bps')} bps, "
            f"relative volume {detail.get('relative_volume')}",
        ],
        counter_arguments=["composite is proxy-based, not order-book depth"],
        required_conditions=["spread within provider norm before market orders"],
        invalidation="spread widening beyond 2x recent median",
        data_sources=[_src(ms.scope)],
        data_quality=ms.data_quality,
    )


def quant_opinion(ms: MarketState) -> AgentOpinionSchema:
    reg_comp = next((c for c in ms.components if c.name == "regime"), None)
    metrics = reg_comp.detail if reg_comp else {}
    args = [
        f"regime {ms.regime.value} vol {ms.volatility.value} method {metrics.get('method', 'n/a')}"
    ]
    if metrics.get("adx") is not None:
        args.append(f"ADX {metrics['adx']}, efficiency {metrics.get('efficiency_ratio')}")
    if ms.momentum_score is not None:
        args.append(f"momentum {ms.momentum_score}")
    else:
        args.append("insufficient candle history for momentum")
    trend_bias = (
        "LONG" if ms.regime.value == "TRENDING" and (ms.momentum_score or 0) > 0.15
        else "SHORT" if ms.regime.value == "TRENDING" and (ms.momentum_score or 0) < -0.15
        else "NEUTRAL"
    )
    return AgentOpinionSchema(
        agent="orion-quant",
        asset=ms.scope,
        bias=trend_bias,
        confidence="MODERATE" if metrics.get("adx") is not None else "LOW",
        strength=min(75.0, 35 + abs(ms.momentum_score or 0) * 40),
        time_horizon="SWING",
        arguments=args,
        counter_arguments=["statistical regime can lag sharp reversals"],
        required_conditions=[f"volatility state stays {ms.volatility.value}"],
        invalidation="ADX collapse below 15 or momentum sign flip",
        data_sources=[_src(ms.scope)],
        data_quality=ms.data_quality,
    )


def positioning_opinion(ms: MarketState) -> AgentOpinionSchema:
    """Honest voice: institutional positioning has NO live feed yet."""
    return AgentOpinionSchema(
        agent="orion-positioning",
        asset=ms.scope,
        bias="WAIT",
        confidence="LOW",
        strength=25.0,
        time_horizon="N/A",
        arguments=[
            "COT / Managed Money / dealer gamma NOT AVAILABLE — no verified feed configured",
            "refusing to infer positioning from price action alone",
        ],
        counter_arguments=["positioning could materially change the CIO read once wired"],
        required_conditions=["wire CFTC COT or broker OI feed before weighting this desk"],
        invalidation="N/A",
        data_sources=[],
        data_quality=None,
    )


def news_opinion(ms: MarketState, high_titles: list[str], total_recent: int) -> AgentOpinionSchema:
    args = [f"{total_recent} headlines stored (last 24h), {len(high_titles)} flagged HIGH"]
    bias = "NEUTRAL"
    strength = 30.0
    if high_titles:
        args.extend(f"HIGH relevance: {t}" for t in high_titles[:3])
        strength = 45.0
    if not total_recent:
        args = ["news table empty for this cycle — ingestion pending"]
        strength = 20.0
    return AgentOpinionSchema(
        agent="orion-news",
        asset=ms.scope,
        bias=bias,
        confidence="LOW",
        strength=strength,
        time_horizon="INTRADAY",
        arguments=args,
        counter_arguments=["headline sentiment ≠ price reaction"],
        required_conditions=["manual read of HIGH-relevance items before execution"],
        invalidation="N/A",
        data_sources=[],
        data_quality=None,
    )


def cross_asset_opinion(
    ms: MarketState, correlations: dict[str, float | None]
) -> AgentOpinionSchema:
    args = []
    abnormal = []
    for pair, rho in correlations.items():
        if rho is None:
            continue
        args.append(f"{pair}: ρ={rho:+.2f}")
    # classic sanity checks with real thresholds
    gold_dxy = correlations.get("GOLD_DXY")
    if gold_dxy is not None and gold_dxy > 0.3:
        abnormal.append(f"GOLD/DXY positive correlation {gold_dxy:+.2f} — ABNORMAL relationship")
    spx_vix = correlations.get("SPX_VIX")
    if spx_vix is not None and spx_vix > -0.1:
        abnormal.append(f"SPX/VIX correlation {spx_vix:+.2f} — hedging relation broken")
    if abnormal:
        args.extend(abnormal)
    else:
        args.append("cross-asset relations within normal bands")
    return AgentOpinionSchema(
        agent="orion-crossasset",
        asset=ms.scope,
        bias="NEUTRAL",
        confidence="MODERATE" if correlations else "LOW",
        strength=55.0 if abnormal else 35.0,
        time_horizon="SWING",
        arguments=args,
        counter_arguments=["rolling windows short → noisy estimates"],
        required_conditions=["recompute after next session close"],
        invalidation="correlation regime persists opposite for 3+ sessions",
        data_sources=[_src(sym) for sym in ("GOLD", "DXY", "SPX", "VIX")],
        data_quality=ms.data_quality,
    )


def metals_opinion(ms: MarketState, dxy_drag: bool) -> AgentOpinionSchema:
    mom = ms.momentum_score
    if mom is None:
        bias, strength = "WAIT", 25.0
        args = ["no candle history for metal — cannot assess"]
    else:
        bias = "LONG" if mom > 0.2 else "SHORT" if mom < -0.2 else "NEUTRAL"
        strength = min(70.0, 30 + abs(mom) * 50)
        args = [f"metal momentum {mom:+.2f}", f"DXY drag active: {dxy_drag}"]
    return AgentOpinionSchema(
        agent="orion-metals",
        asset=ms.scope,
        bias=bias,
        confidence="LOW" if mom is None else "MODERATE",
        strength=strength,
        time_horizon="POSITION",
        arguments=args,
        counter_arguments=["real yields feed missing — key driver unseen"],
        required_conditions=["DXY stable or falling to keep long thesis alive"],
        invalidation="momentum sign flip with volume expansion",
        data_sources=[_src(ms.scope), _src("DXY")],
        data_quality=ms.data_quality,
    )
