"""GOLD PLAYBOOK (P3) — XAUUSD / GC / MGC.

Automatically reads: DXY, US10Y, US02Y (when stored), VIX, SPX, NQ,
CFTC Gold, macro news, session map, market regime, market brain,
liquidity and structure. MGC is the preferred OPERATIONAL instrument
when a real fresh feed exists; spot XAUUSD sourced via GC=F is clearly
labelled as a proxy.
"""

from __future__ import annotations

from core.desk.context import ContextBuilder, not_available
from core.playbooks.base import assemble_technicals

GOLD_SYMBOLS = ("XAUUSD", "GC", "MGC")
MACRO_CONTEXT_QUOTES = ("DXY", "US10Y", "US02Y", "VIX", "SPX", "NQ")


async def run_gold_playbook(session_factory, symbol: str = "XAUUSD") -> dict:
    """Return the full gold playbook: structured stack + human-readable brief."""
    builder = ContextBuilder(session_factory)
    symbol = symbol.upper() if symbol.upper() in GOLD_SYMBOLS else "XAUUSD"
    stack = await assemble_technicals(builder, symbol)
    ctx = stack.ctx

    # --- operational instrument decision (MGC priority when REAL + FRESH)
    mgc_quote = builder._latest_quote("MGC")
    instrument = symbol
    proxy_label: str | None = None
    if symbol == "XAUUSD":
        proxy_label = ("spot XAUUSD priced via GC=F Yahoo proxy — futures "
                       "reference, not OTC spot")
        if mgc_quote is not None:
            from datetime import UTC, datetime

            age = (datetime.now(UTC) - (
                mgc_quote.ts_received.replace(tzinfo=UTC)
                if mgc_quote.ts_received.tzinfo is None else mgc_quote.ts_received)
            ).total_seconds()
            if age < 600:
                instrument = ("MGC (micro gold futures) — real fresh feed, "
                              "preferred operational instrument")

    # --- extra macro context quotes not already in ctx.extra_quotes
    extras = ctx.get("extra_quotes") or {}
    for sym in MACRO_CONTEXT_QUOTES:
        if sym not in extras:
            q = builder._latest_quote(sym)
            extras[sym] = builder._quote_tag(sym) if q else not_available(
                f"no stored quote for {sym}")
    ctx["extra_quotes"] = extras

    brief = _render_brief(stack, instrument, proxy_label)
    return {"playbook": "GOLD", "symbol": symbol, "instrument": instrument,
            "proxy": proxy_label, "stack": stack.to_dict(), "brief": brief,
            "ctx": ctx}


def _render_brief(stack, instrument: str, proxy: str | None) -> str:
    ctx = stack.ctx
    price_block = ctx.get("price") or {}
    ms = ctx.get("market_state") or {}
    bias = stack.bias_score or {}
    tq = stack.trade_quality or {}

    lines: list[str] = [f"ORION GOLD PLAYBOOK — {instrument}", ""]
    if proxy:
        lines.append(f"PROXY NOTE: {proxy}")
        lines.append("")

    v = price_block.get("value")
    lines.append("CONTEXT:")
    lines.append(f"- spot: {v:g} [{price_block.get('source')} · "
                 f"{price_block.get('status')}]"
                 if isinstance(v, (int, float)) else "- spot: NOT AVAILABLE")
    for sym, block in ((ctx.get("extra_quotes") or {}).items()):
        val = block.get("value")
        lines.append(f"- {sym}: {val:g} [{block.get('status')}]"
                     if isinstance(val, (int, float))
                     else f"- {sym}: NOT AVAILABLE")
    cot = ctx.get("positioning_cftc") or {}
    cv = cot.get("value") or {}
    if isinstance(cv, dict) and cv.get("managed_money_net") is not None:
        lines.append(f"- CFTC managed money net: {cv['managed_money_net']:,.0f} "
                     f"(report {cv.get('report_date')})")
    else:
        lines.append(f"- CFTC: NOT AVAILABLE ({cot.get('reason', 'no series')})")

    smap = stack.session_map.to_dict() if stack.session_map else {"levels": []}
    lines.append("")
    lines.append("SESSION MAP (all DERIVED):")
    for lv in smap["levels"]:
        if lv["value"] is not None and isinstance(lv["value"], (int, float)):
            lines.append(f"- {lv['name']}: {lv['value']:g}")
    for miss in smap.get("missing", []):
        lines.append(f"- {miss}: NOT AVAILABLE (insufficient candle history)")

    lq = stack.liquidity.to_dict() if stack.liquidity else {}
    lines.append("")
    lines.append("LIQUIDITY (derived pools, NOT confirmed institutional orders):")
    for side in ("buy_side", "sell_side"):
        top = lq.get(side, [])[:4]
        label = "BUY-SIDE" if side == "buy_side" else "SELL-SIDE"
        if top:
            joined = ", ".join(f"{p['kind']}@{p['price']:g}" for p in top)
            lines.append(f"- {label}: {joined}")
        else:
            lines.append(f"- {label}: none mapped yet")

    zone = stack.range_zone
    lines.append("")
    if zone:
        lines.append(
            f"ORION RANGE 2.6: range {zone['range_low']:g} – {zone['range_high']:g} → "
            f"reaction zone ~{zone['zone_price']:g} "
            f"(confluences: {'; '.join(zone['confluences']) or 'none yet'})")
        lines.append(f"- {zone['note']}")
    else:
        lines.append("ORION RANGE 2.6: no significant range in lookback — zone skipped.")

    sweeps = stack.sweeps or []
    lines.append("")
    if sweeps:
        lines.append("SWEEPS:")
        for s in sweeps[-3:]:
            lines.append(f"- {s['kind']} @ {s['level']:g} ({s['bar_ts'][:16]}) — "
                         "sweep ≠ entry; await reaction/confirmation")
    else:
        lines.append("SWEEPS: none detected in recent bars.")

    lines.append("")
    lines.append(f"BIAS SCORE: {bias.get('total', '?')} ({bias.get('band', 'NEUTRAL')}) "
                 f"[missing inputs: {', '.join(bias.get('missing_inputs') or []) or 'none'}]")
    lines.append(f"TRADE QUALITY: {tq.get('total', '?')} "
                 f"[missing inputs: {', '.join(tq.get('missing_inputs') or []) or 'none'}]")
    lines.append("DECISION: WAIT — playbook reports context; entries require reaction + "
                 "confirmation + R:R ≥ 2 + risk clearance.")
    regime = ms.get("regime")
    lines.append("")
    lines.append(f"REGIME: {regime} | volatility={ms.get('volatility')} | "
                 f"data_quality={(ms.get('data_quality') or 0):.0%}")
    return "\n".join(lines)
