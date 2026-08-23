"""XRP PLAYBOOK (P4) — XRPUSD.

Reads: XRPUSD, BTCUSD, ETHUSD (when relevant), NASDAQ/NDX, DXY, US10Y,
BTC correlation, relative strength vs BTC, momentum, volatility, regime,
crypto news incl. verified Ripple/XRPL/RLUSD items, Polymarket
availability flag.

RULE: a Ripple headline is NEVER automatically a BUY. News only enters
as event-risk context; direction requires the full doctrine stack.
"""

from __future__ import annotations

from core.desk.context import ContextBuilder, not_available
from core.playbooks.base import assemble_technicals

XRP_CONTEXT_QUOTES = ("BTCUSD", "ETHUSD", "NDX", "DXY", "US10Y")
RIPPLE_KEYWORDS = ("ripple", "xrpl", "rlusd", "sec", "etf")


async def run_xrp_playbook(session_factory) -> dict:
    builder = ContextBuilder(session_factory)
    stack = await assemble_technicals(builder, "XRPUSD")
    ctx = stack.ctx

    extras = ctx.get("extra_quotes") or {}
    for sym in XRP_CONTEXT_QUOTES:
        if sym not in extras:
            q = builder._latest_quote(sym)
            extras[sym] = builder._quote_tag(sym) if q else not_available(
                f"no stored quote for {sym}")
    ctx["extra_quotes"] = extras

    # ETH relevance flag: only meaningful with real stored history
    eth_block = extras.get("ETHUSD") or {}
    ctx["eth_relevance"] = (
        "relevant" if isinstance(eth_block.get("value"), (int, float)) else "NOT AVAILABLE"
    )

    ripple_news = [
        n for n in (ctx.get("news") or [])
        if isinstance(n, dict)
        and any(k in str(n.get("value", "")).lower() for k in RIPPLE_KEYWORDS)
    ]
    polymarket = ctx.get("polymarket") or {}

    brief = _render_brief(stack, ripple_news, polymarket)
    return {"playbook": "XRP", "symbol": "XRPUSD",
            "stack": stack.to_dict(), "brief": brief,
            "ctx": ctx,
            "ripple_news_count": len(ripple_news),
            "news_auto_buy_rule": "Ripple news NEVER auto-converts to LONG — "
                                  "direction only via doctrine stack"}


def _render_brief(stack, ripple_news: list[dict], polymarket: dict) -> str:
    ctx = stack.ctx
    price_block = ctx.get("price") or {}
    ms = ctx.get("market_state") or {}
    bias = stack.bias_score or {}
    tq = stack.trade_quality or {}

    lines: list[str] = ["ORION XRP PLAYBOOK — XRPUSD", ""]
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

    rs = ctx.get("relative_strength_vs_btc") or {}
    rsv = rs.get("value")
    lines.append(f"- XRP/BTC relative strength: {rsv:.6g}"
                 if isinstance(rsv, (int, float)) else
                 f"- XRP/BTC relative strength: NOT AVAILABLE ({rs.get('reason', 'n/a')})")

    corr = (ctx.get("correlations") or {}).get("XRPUSD/BTCUSD") or {}
    cv = corr.get("value")
    lines.append(f"- BTC correlation: {cv:+.3f}"
                 if isinstance(cv, (int, float)) else
                 "- BTC correlation: NOT AVAILABLE (insufficient overlap)")

    pmv = polymarket.get("provenance")
    if pmv == "NOT_AVAILABLE":
        lines.append(f"- Polymarket: NOT AVAILABLE ({polymarket.get('reason', 'no feed')})")

    lines.append("")
    lines.append(f"REGIME: {ms.get('regime')} | volatility={ms.get('volatility')} | "
                 f"data_quality={(ms.get('data_quality') or 0):.0%}")

    smap = stack.session_map.to_dict() if stack.session_map else {"levels": [], "missing": []}
    avail = [lv for lv in smap["levels"] if isinstance(lv["value"], (int, float))]
    lines.append("")
    lines.append("SESSION MAP (DERIVED): "
                 + (", ".join(f"{lv['name']}={lv['value']:g}" for lv in avail[:6])
                    or "no levels computable yet"))
    lq = stack.liquidity.to_dict() if stack.liquidity else {}
    pools = [f"{p['kind']}@{p['price']:g}"
             for p in (lq.get("buy_side", []) + lq.get("sell_side", []))[:5]]
    lines.append("LIQUIDITY: " + (", ".join(pools) or "none mapped yet"))

    zone = stack.range_zone
    lines.append("")
    lines.append(
        f"ORION RANGE 2.6: zone ~{zone['zone_price']:g} "
        f"(confluences: {'; '.join(zone['confluences']) or 'none yet'})" if zone else
        "ORION RANGE 2.6: no significant range in lookback.")

    lines.append("")
    lines.append("NEWS (event-risk context ONLY — never auto-BUY):")
    if ripple_news:
        for n in ripple_news[:3]:
            lines.append(f"- [{n.get('relevance', '?')}] {str(n.get('value'))[:110]} "
                         f"[{n.get('source')}]")
    else:
        lines.append("- no verified Ripple/XRPL/RLUSD headlines in window")
    lines.append("- rule: verified Ripple news is treated as EVENT RISK input, "
                 "not as a directional signal.")

    lines.append("")
    lines.append(f"BIAS SCORE: {bias.get('total', '?')} ({bias.get('band', 'NEUTRAL')}) "
                 f"[missing inputs: {', '.join(bias.get('missing_inputs') or []) or 'none'}]")
    lines.append(f"TRADE QUALITY: {tq.get('total', '?')} "
                 f"[missing inputs: {', '.join(tq.get('missing_inputs') or []) or 'none'}]")
    lines.append("DECISION: WAIT — playbook reports context; entries require reaction + "
                 "confirmation + R:R ≥ 2 + risk clearance.")
    return "\n".join(lines)
