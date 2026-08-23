"""Shared playbook assembly (P3-P4 support layer).

`ContextBuilder.build()` already derives session map, liquidity map,
ORION_RANGE_2_6 and sweeps into ctx["technicals"] (single source of
truth, computed from the SAME real candle rows it reads for summaries).
This module turns that context into:

- BIAS SCORE components (P11)
- TRADE QUALITY inputs (P12)
- a doctrine DECISION via ORIONTradingDoctrine (P1/P13/P14)

and exposes `assemble_technicals()` used by the Gold/XRP playbooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.desk.context import ContextBuilder, not_available
from core.doctrine.doctrine import ORIONTradingDoctrine
from core.doctrine.scores import (
    compute_bias_score,
    compute_trade_quality,
    extension_score,
    freshness_score,
    risk_state_score,
    rr_score,
)


@dataclass
class TechnicalStack:
    symbol: str
    ctx: dict
    session_map: dict | None = None
    liquidity: dict | None = None
    range_zone: dict | None = None
    sweeps: list[dict] = field(default_factory=list)
    bias_score: dict | None = None
    trade_quality: dict | None = None
    decision: dict | None = None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "session_levels": self.session_map,
            "liquidity": self.liquidity,
            "orion_range_2_6": self.range_zone,
            "sweeps": self.sweeps,
            "bias_score": self.bias_score,
            "trade_quality": self.trade_quality,
            "decision": self.decision,
            "volume_flow": not_available("no verified order-flow feed"),
            "dealer_data": not_available("NOT AVAILABLE — VERIFIED SOURCE REQUIRED"),
        }


async def assemble_technicals(builder: ContextBuilder, symbol: str) -> TechnicalStack:
    """Full doctrine stack for `symbol` from REAL stored data only."""
    ctx = await builder.build(symbol)
    tech = ctx.get("technicals") or {}
    scoring = score_context(ctx)

    return TechnicalStack(
        symbol=symbol, ctx=ctx,
        session_map=tech.get("session_levels"),
        liquidity=tech.get("liquidity"),
        range_zone=tech.get("orion_range_2_6"),
        sweeps=tech.get("sweeps") or [],
        bias_score=scoring["bias_score"],
        trade_quality=scoring["trade_quality"],
        decision=scoring["decision"],
    )


# ------------------------------------------------------------------ scoring
def _pct_to_score(v) -> float | None:
    """MarketBrain scores arrive as -1..1 → map to 0..100."""
    if isinstance(v, (int, float)):
        return max(0.0, min(100.0, (float(v) + 1) * 50))
    return None


def _regime_score(regime: str | None, momentum) -> float | None:
    base = {
        "TRENDING_UP": 70.0, "TRENDING_DOWN": 30.0, "RANGE": 50.0,
        "INSUFFICIENT_DATA": None,
    }.get((regime or "").upper())
    if base is None:
        return _pct_to_score(momentum)
    return base


def _positioning_score(cot_block: dict) -> float | None:
    val = cot_block.get("value") if isinstance(cot_block, dict) else None
    if not isinstance(val, dict):
        return None
    mm = val.get("managed_money_net")
    nc = val.get("noncommercial_net")
    net = mm if isinstance(mm, (int, float)) else (
        nc if isinstance(nc, (int, float)) else None)
    if net is None:
        return None
    # crude normalization around zero — weekly COT only gives tilt, not timing
    return max(0.0, min(100.0, 50 + max(-50.0, min(50.0, net / 50_000 * 25))))


def _cross_asset_score(rhos: list[float]) -> float | None:
    if not rhos:
        return None
    avg = sum(rhos) / len(rhos)
    return max(0.0, min(100.0, (avg + 1) * 50))


def _structure_score(ctx: dict, last_price: float | None) -> float | None:
    cval = ((ctx.get("candles") or {}).get("value") or {})
    hi, lo = cval.get("swing_high_20"), cval.get("swing_low_20")
    if not isinstance(last_price, (int, float)) or hi is None or lo is None:
        return None
    span = hi - lo
    if span <= 0:
        return None
    pos = (last_price - lo) / span          # 0 at low, 1 at high
    return max(0.0, min(100.0, pos * 100))


def _nearest_pool(lq: dict, price: float) -> dict | None:
    buy = lq.get("buy_side") or []
    sell = lq.get("sell_side") or []
    pools = [p for p in buy + sell if isinstance(p.get("price"), (int, float))]
    if not pools:
        return None
    return min(pools, key=lambda p: abs(p["price"] - price))


def _rr_vs_pools(lq: dict, price: float, rng_hi: float | None,
                 rng_lo: float | None) -> float | None:
    """Best measurable R:R: entry≈price, invalidation = opposite extreme of
    mapped range, target = farthest pool in the favorable direction."""
    buy = [p["price"] for p in lq.get("buy_side") or [] if p["price"] > price]
    sell = [p["price"] for p in lq.get("sell_side") or [] if p["price"] < price]
    rrs: list[float] = []
    if sell and rng_hi:                      # long: stop below nearest sell pool
        risk = abs(price - min(sell))
        if risk > 0:
            rrs.append(abs(rng_hi - price) / risk)
    if buy and rng_lo:                       # short
        risk = abs(max(buy) - price)
        if risk > 0:
            rrs.append(abs(price - rng_lo) / risk)
    return max(rrs) if rrs else None


def score_context(ctx: dict) -> dict:
    """Bias score + trade quality + doctrine decision from an ALREADY built ctx."""
    ms = ctx.get("market_state") or {}
    price_block = ctx.get("price") or {}
    last_price = price_block.get("value") if isinstance(
        price_block.get("value"), (int, float)) else None
    cval = (ctx.get("candles") or {}).get("value") or {}
    raw_atr = cval.get("atr")
    atr = raw_atr if isinstance(raw_atr, (int, float)) else None
    tech = ctx.get("technicals") or {}
    lq = tech.get("liquidity") or {}
    sweeps = tech.get("sweeps") or []

    macro_val = _pct_to_score(ms.get("macro_score"))
    regime_val = _regime_score(ms.get("regime"), ms.get("momentum_score"))
    liq_val = _pct_to_score(ms.get("liquidity_score"))
    positioning_val = _positioning_score(ctx.get("positioning_cftc") or {})
    corr_blocks = ctx.get("correlations") or {}
    cross_vals = [
        b["value"] for b in corr_blocks.values()
        if isinstance(b, dict) and isinstance(b.get("value"), (int, float))
    ]
    cross_val = _cross_asset_score(cross_vals)
    news = ctx.get("news") or []
    news_val = 55.0 if news else 45.0   # headlines are event-risk, not direction
    structure_val = _structure_score(ctx, last_price)

    components = {
        "macro": {"value": macro_val} if macro_val is not None else {},
        "cross_asset": {"value": cross_val} if cross_val is not None else {},
        "positioning": {"value": positioning_val} if positioning_val is not None else {},
        "regime": {"value": regime_val} if regime_val is not None else {},
        "liquidity": {"value": liq_val} if liq_val is not None else {},
        "structure": {"value": structure_val} if structure_val is not None else {},
        "news_event_risk": {"value": news_val},
    }
    bias_result = compute_bias_score(components)

    # --- trade quality inputs
    tq_inputs: dict[str, dict] = {}
    pool = _nearest_pool(lq, last_price) if last_price else None
    dist_atr = (abs(pool["price"] - last_price) / atr
                if pool and atr else None)
    tq_inputs["location"] = (
        {"score": max(10.0, 90.0 - dist_atr * 60.0), "detail":
         f"{pool['kind']} @ {pool['price']:g}"}
        if pool is not None and dist_atr is not None else {})
    reaction = any(s.get("kind") in ("SWEEP_HIGH", "SWEEP_LOW", "FAILED_BREAKOUT")
                   for s in sweeps)
    tq_inputs["reaction"] = {"score": 80.0 if reaction else 20.0}
    tq_inputs["confirmation"] = {"score": 75.0 if reaction else 20.0}
    rq = _rr_vs_pools(lq, last_price, cval.get("swing_high_20"),
                      cval.get("swing_low_20")) if last_price else None
    tq_inputs["rr"] = {"score": rr_score(rq)} if rq is not None else {}
    tq_inputs["liquidity_conditions"] = {"score": 80.0}  # specialist vetoes upstream
    status = price_block.get("status") or ""
    tq_inputs["data_freshness"] = {"score": freshness_score(status)}
    high_impact = any(isinstance(n, dict) and n.get("relevance") == "HIGH"
                      for n in news)
    tq_inputs["event_risk"] = {"score": 35.0 if high_impact else 75.0}
    ext = dist_atr
    zone_price = (tech.get("orion_range_2_6") or {}).get("zone_price")
    if ext is None and zone_price and last_price and atr:
        ext = abs(last_price - zone_price) / atr
    tq_inputs["extension"] = {"score": extension_score(ext)} if ext is not None else {}
    snap = ((ctx.get("risk_snapshot") or {}).get("value") or {})
    tq_inputs["risk_state"] = ({"score": risk_state_score(snap.get("verdict"))}
                               if snap.get("verdict") else {})
    tq_result = compute_trade_quality(tq_inputs)

    # --- doctrine decision (bias ≠ entry; sequence enforced)
    bias_dir = "NEUTRAL"
    if structure_val is not None:
        bias_dir = "LONG" if bias_result.total >= 55 else (
            "SHORT" if bias_result.total <= 45 else "NEUTRAL")
    doctrine = ORIONTradingDoctrine()
    decision = doctrine.evaluate(
        bias=bias_dir,
        reaction=reaction if (reaction or lq) else None,
        confirmation=reaction,
        rr=rq,
        extension_atr=ext,
        risk_ok=snap.get("verdict") != "RED_LIGHT",
        has_level=bool(pool),
    )
    return {
        "bias_score": bias_result.to_dict(),
        "trade_quality": tq_result.to_dict(),
        "decision": decision.to_dict(),
    }
