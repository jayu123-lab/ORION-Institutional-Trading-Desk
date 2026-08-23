"""Deterministic specialist opinions derived from the REAL context dict.

Each function receives the ContextBuilder output (provenance-tagged dicts)
and returns a SpecialistOpinion. No invented numbers: every statement traces
to a context field; missing inputs degrade the opinion honestly.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpecialistOpinion:
    agent: str
    stance: str  # LONG|SHORT|NEUTRAL|WAIT|PASS|CAUTION|REJECT|INFORMATIVE
    confidence: str  # LOW|MODERATE|HIGH|VERY HIGH
    summary: str
    key_points: list[str] = field(default_factory=list)


def _val(block: dict | None):  # noqa: ANN201
    return block.get("value") if isinstance(block, dict) else None


def _status(block: dict | None) -> str | None:  # noqa: ANN201
    return block.get("status") if isinstance(block, dict) else None


def _price_ok(ctx: dict) -> bool:
    p = _val(ctx.get("price"))
    return isinstance(p, (int, float)) and p > 0


# ----------------------------------------------------------------- specialists
def metals_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "metals-analyst"
    if not _price_ok(ctx):
        return SpecialistOpinion(
            agent, "WAIT", "LOW",
            "No verified live quote for gold complex — cannot form a technical view.",
            ["price: NOT AVAILABLE or STALE"],
        )
    price = float(_val(ctx["price"]))
    points: list[str] = []
    stance, conf = "NEUTRAL", "MODERATE"

    candles = _val(ctx.get("candles"))
    ms = ctx.get("market_state") or {}
    if isinstance(candles, dict):
        hi, lo = candles.get("swing_high_20"), candles.get("swing_low_20")
        atr = candles.get("atr")
        if hi and lo and hi > lo:
            pos = (price - lo) / max(hi - lo, 1e-9)
            if pos >= 0.8:
                stance = "LONG"
                points.append(
                    f"price {price:g} within {(pos * 100):.0f}% of swing high {hi:g}")
            elif pos <= 0.2:
                stance = "SHORT"
                points.append(f"price {price:g} near 20-bar swing low {lo:g}")
            else:
                points.append(f"price mid-range ({(pos * 100):.0f}% of {lo:g}-{hi:g})")
        elif hi is not None and hi == lo:
            points.append("flat bar history — no usable range structure yet")
        if atr:
            atr_pct = atr / price * 100
            points.append(f"ATR(14) {atr:.2f} = {atr_pct:.2f}% of price")
            if atr_pct > 2.5:
                conf = "LOW"
                points.append("volatility elevated — widen stops or stand aside")

    regime = ms.get("regime")
    if regime == "TRENDING":
        points.append(f"regime TRENDING (momentum {ms.get('momentum_score')})")
    elif regime:
        points.append(f"regime {regime}")

    corr = ctx.get("correlations") or {}
    dxy = corr.get("XAUUSD/DXY")
    us10y = corr.get("XAUUSD/US10Y")
    if isinstance(dxy, dict) and isinstance(dxy.get("value"), (int, float)):
        points.append(f"DXY correlation {dxy['value']:+.2f}")
    if isinstance(us10y, dict) and isinstance(us10y.get("value"), (int, float)):
        points.append(f"US10Y correlation {us10y['value']:+.2f}")

    extras = ctx.get("extra_quotes") or {}
    vix = _val(extras.get("VIX"))
    if isinstance(vix, (int, float)):
        if vix > 25:
            points.append(f"VIX {vix:g} elevated — safe-haven tailwind possible")
            if stance == "SHORT":
                stance, conf = "WAIT", "LOW"
        elif isinstance(vix, (int, float)) and vix < 15:
            points.append(f"VIX {vix:g} subdued")
    dxy_status = _status(extras.get("DXY"))
    if dxy_status not in ("LIVE", "STALE", "DELAYED"):
        points.append("DXY quote unavailable — USD leg of thesis unverified")

    return SpecialistOpinion(
        agent, stance, conf,
        f"Gold technical read at {price:g}: {stance}, {conf.lower()} confidence.",
        points,
    )


def crypto_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "crypto-analyst"
    if not _price_ok(ctx):
        return SpecialistOpinion(
            agent, "WAIT", "LOW",
            "No verified live quote for this crypto asset.",
            ["price: NOT AVAILABLE"],
        )
    price = float(_val(ctx["price"]))
    points: list[str] = [f"spot {price:g}"]
    stance, conf = "NEUTRAL", "MODERATE"

    rs = _val(ctx.get("relative_strength_vs_btc"))
    if isinstance(rs, (int, float)):
        points.append(f"XRP/BTC ratio {rs:.8f}".rstrip("0").rstrip("."))
    candles = _val(ctx.get("candles"))
    if isinstance(candles, dict) and candles.get("atr"):
        atr_pct = candles["atr"] / price * 100
        points.append(f"ATR {atr_pct:.2f}% of price")
        if atr_pct > 6:
            conf = "LOW"
            points.append("extreme volatility — size down")

    ms = ctx.get("market_state") or {}
    if ms.get("risk_mode") == "RISK_OFF":
        points.append("macro risk_mode RISK_OFF — crypto beta punished")
        if stance != "WAIT":
            stance, conf = "WAIT", "LOW"
    if ms.get("regime"):
        points.append(f"regime {ms['regime']}")

    news = ctx.get("news") or []
    if news:
        titles = [n.get("value", "") for n in news[:3] if isinstance(n, dict)]
        if titles:
            points.append("recent: " + " | ".join(t.strip()[:70] for t in titles))

    return SpecialistOpinion(
        agent, stance, conf,
        f"{ctx.get('asset')} read at {price:g}: {stance}, {conf.lower()} confidence.",
        points,
    )


def equities_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "equities-analyst"
    if not _price_ok(ctx):
        return SpecialistOpinion(
            agent, "WAIT", "LOW", "No verified index quote.", [],
        )
    price = float(_val(ctx["price"]))
    ms = ctx.get("market_state") or {}
    points = [f"level {price:g}", f"regime {ms.get('regime')}"]
    stance = "NEUTRAL"
    if ms.get("risk_mode") == "RISK_ON":
        stance = "LONG"
        points.append("risk-on backdrop supports index longs")
    elif ms.get("risk_mode") == "RISK_OFF":
        stance = "SHORT"
        points.append("risk-off backdrop pressures index")
    return SpecialistOpinion(agent, stance, "MODERATE",
                             f"Index read at {price:g}: {stance}.", points)


def forex_analyst(ctx: dict) -> SpecialistOpinion:
    """EURUSD/GBPUSD/USDJPY technical read, anchored to real DXY cross-data.

    Distinct from macro_strategist: this reads the PAIR's own structure
    (swing range, ATR, regime) and only uses DXY as a cross-check, never as
    a substitute for the pair's own price action.
    """
    agent = "forex-analyst"
    if not _price_ok(ctx):
        return SpecialistOpinion(
            agent, "WAIT", "LOW",
            "No verified live quote for this FX pair — cannot form a technical view.",
            ["price: NOT AVAILABLE or STALE"],
        )
    price = float(_val(ctx["price"]))
    points: list[str] = []
    stance, conf = "NEUTRAL", "MODERATE"

    candles = _val(ctx.get("candles"))
    ms = ctx.get("market_state") or {}
    if isinstance(candles, dict):
        hi, lo = candles.get("swing_high_20"), candles.get("swing_low_20")
        atr = candles.get("atr")
        if hi and lo and hi > lo:
            pos = (price - lo) / max(hi - lo, 1e-9)
            if pos >= 0.8:
                stance = "LONG"
                points.append(f"price {price:g} within {(pos * 100):.0f}% of swing high {hi:g}")
            elif pos <= 0.2:
                stance = "SHORT"
                points.append(f"price {price:g} near 20-bar swing low {lo:g}")
            else:
                points.append(f"price mid-range ({(pos * 100):.0f}% of {lo:g}-{hi:g})")
        elif hi is not None and hi == lo:
            points.append("flat bar history — no usable range structure yet")
        if atr:
            atr_pct = atr / price * 100
            points.append(f"ATR(14) {atr:.4f} = {atr_pct:.2f}% of price")
            if atr_pct > 1.0:
                conf = "LOW"
                points.append("volatility elevated for FX majors — widen stops or stand aside")

    regime = ms.get("regime")
    if regime == "TRENDING":
        points.append(f"regime TRENDING (momentum {ms.get('momentum_score')})")
    elif regime:
        points.append(f"regime {regime}")

    corr = ctx.get("correlations") or {}
    dxy_key = next((k for k in corr if k.endswith("/DXY")), None)
    if dxy_key:
        dxy_corr = _val(corr[dxy_key])
        if isinstance(dxy_corr, (int, float)):
            points.append(f"DXY correlation {dxy_corr:+.2f}")
            if dxy_corr > -0.3:
                points.append("correlation weaker than the usual inverse-USD relationship — flag divergence")

    extras = ctx.get("extra_quotes") or {}
    dxy_status = _status(extras.get("DXY"))
    if dxy_status not in ("LIVE", "STALE", "DELAYED"):
        points.append("DXY quote unavailable — USD leg of thesis unverified")
    us10y = _val(extras.get("US10Y"))
    if isinstance(us10y, (int, float)):
        points.append(f"US10Y {us10y:g} (rate-differential context)")

    session = _val(ctx.get("session")) or {}
    active = session.get("active") if isinstance(session, dict) else None
    if isinstance(active, list) and not any(s in active for s in ("LONDON", "NEW_YORK")):
        conf = "LOW"
        points.append("outside London/NY hours — thin liquidity, treat levels cautiously")

    return SpecialistOpinion(
        agent, stance, conf,
        f"FX technical read at {price:g}: {stance}, {conf.lower()} confidence.",
        points,
    )


def macro_strategist(ctx: dict) -> SpecialistOpinion:
    agent = "macro-strategist"
    ms = ctx.get("market_state") or {}
    score = ms.get("macro_score")
    points: list[str] = []
    extras = ctx.get("extra_quotes") or {}
    dxy = _val(extras.get("DXY"))
    us10y = _val(extras.get("US10Y"))
    if isinstance(dxy, (int, float)):
        points.append(f"DXY {dxy:g}")
    else:
        points.append("DXY NOT AVAILABLE")
    if isinstance(us10y, (int, float)):
        points.append(f"US10Y {us10y:g}")
    else:
        points.append("US10Y NOT AVAILABLE")
    session = _val(ctx.get("session")) or {}
    active = session.get("active") if isinstance(session, dict) else None
    if active is not None:
        points.append("active sessions: " + (",".join(active) or "none"))
    stance = "INFORMATIVE"
    conf = "MODERATE" if score is not None else "LOW"
    if score is not None:
        points.append(f"macro composite {score}/100")
    return SpecialistOpinion(agent, stance, conf,
                             "Macro backdrop assessed from verified feeds only.", points)


def liquidity_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "liquidity-analyst"
    price_block = ctx.get("price") or {}
    bid, ask = price_block.get("bid"), price_block.get("ask")
    points: list[str] = []
    if isinstance(bid, (int, float)) and isinstance(ask, (int, float)) and ask > bid > 0:
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10000
        status = "PASS" if spread_bps < 5 else ("CAUTION" if spread_bps < 20 else "REJECT")
        points.append(f"spread {spread_bps:.1f} bps")
    else:
        status = "CAUTION"
        points.append("no two-sided quote stored — spread unverified")
    candles = _val(ctx.get("candles"))
    if isinstance(candles, dict):
        hi, lo = candles.get("swing_high_20"), candles.get("swing_low_20")
        if hi and lo and hi > lo:
            points.append(f"liquidity shelf {lo:g}-{hi:g}")
        else:
            points.append("range structure flat — no shelf defined")
    return SpecialistOpinion(agent, status, "MODERATE",
                             "Execution liquidity assessment.", points)


def positioning_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "positioning-analyst"
    cot = ctx.get("positioning_cftc") or {}
    val = cot.get("value") if isinstance(cot, dict) else None
    if not isinstance(val, dict):
        reason = cot.get("reason") if isinstance(cot, dict) else "unknown"
        return SpecialistOpinion(agent, "INFORMATIVE", "LOW",
                                 f"CFTC positioning NOT AVAILABLE ({reason}).", [])
    mm = val.get("managed_money_net")
    nc = val.get("noncommercial_net")
    oi = val.get("open_interest")
    date = val.get("report_date")
    points = [f"COT report {date} (weekly snapshot)", f"open interest {oi:,}" if oi else ""]
    stance, conf = "INFORMATIVE", "MODERATE"
    net = mm if mm is not None else nc
    if net is not None:
        label = "Managed Money" if mm is not None else "Non-commercial"
        points.append(f"{label} net {'LONG' if net > 0 else 'SHORT'} {abs(net):,}")
        share = abs(net) / oi * 100 if oi else None
        if share is not None and share > 30:
            conf = "HIGH"
            points.append(f"net position = {share:.0f}% of OI — crowded")
    return SpecialistOpinion(agent, stance, conf,
                             "CFTC weekly positioning loaded from Socrata API.", points)


def crossasset_analyst(ctx: dict) -> SpecialistOpinion:
    agent = "crossasset-analyst"
    corr = ctx.get("correlations") or {}
    points: list[str] = []
    for pair, block in corr.items():
        rho = _val(block) if isinstance(block, dict) else None
        if isinstance(rho, (int, float)):
            points.append(f"{pair} ρ={rho:+.2f}")
        else:
            points.append(f"{pair} insufficient overlap — NOT AVAILABLE")
    ms = ctx.get("market_state") or {}
    if ms.get("risk_mode"):
        points.append(f"cross-asset regime {ms['risk_mode']}")
    return SpecialistOpinion(agent, "INFORMATIVE", "MODERATE",
                             "Cross-asset relationships computed on stored closes.",
                             points)


def news_specialist(ctx: dict) -> SpecialistOpinion:
    agent = "news-intelligence"
    news = ctx.get("news") or []
    if not news:
        return SpecialistOpinion(agent, "INFORMATIVE", "LOW",
                                 "No relevant verified headlines in last 48h.", [])
    points = [
        f"[{n.get('relevance', '')}] {str(n.get('value'))[:90]}"
        for n in news[:4] if isinstance(n, dict)
    ]
    return SpecialistOpinion(agent, "INFORMATIVE", "MODERATE",
                             f"{len(news)} verified headline(s) in window.", points)


def quant_architect(ctx: dict) -> SpecialistOpinion:
    agent = "quant-architect"
    ms = ctx.get("market_state") or {}
    dq = ms.get("data_quality", 0.0)
    candles = _val(ctx.get("candles"))
    points = [f"data_quality {dq:.0%}"]
    if dq < 0.4:
        return SpecialistOpinion(agent, "REJECT", "HIGH",
                                 "Data quality below institutional floor.", points)
    if not isinstance(candles, dict) or not candles.get("atr"):
        points.append("insufficient candle history for signal math")
        return SpecialistOpinion(agent, "CAUTION", "MODERATE",
                                 "Not enough bars to validate a systematic setup.", points)
    price = _val(ctx.get("price"))
    if not isinstance(price, (int, float)):
        points.append("no price anchor")
        return SpecialistOpinion(agent, "REJECT", "HIGH", "Cannot compute levels.", points)
    hi, lo = candles.get("swing_high_20"), candles.get("swing_low_20")
    if not hi or not lo:
        return SpecialistOpinion(agent, "CAUTION", "MODERATE",
                                 "Swing structure incomplete.", points)
    points.append(f"structural levels {lo:g} / {hi:g} valid vs spot {price:g}")
    regime = ms.get("regime")
    if regime == "HIGH_VOLATILITY":
        return SpecialistOpinion(agent, "CAUTION", "HIGH",
                                 "Vol regime invalidates default sizing assumptions.",
                                 points)
    return SpecialistOpinion(agent, "PASS", "HIGH",
                             "Levels and volatility internally consistent.", points)


SPECIALIST_FUNCS = {
    "metals-analyst": metals_analyst,
    "crypto-analyst": crypto_analyst,
    "equities-analyst": equities_analyst,
    "forex-analyst": forex_analyst,
    "macro-strategist": macro_strategist,
    "liquidity-analyst": liquidity_analyst,
    "positioning-analyst": positioning_analyst,
    "crossasset-analyst": crossasset_analyst,
    "news-intelligence": news_specialist,
    "quant-architect": quant_architect,
}
