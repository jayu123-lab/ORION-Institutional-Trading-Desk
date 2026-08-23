"""CIO operating modes (P15): ORION PRE-LONDON, PRE-NY, DAILY CLOSE.

Each mode assembles a structured brief from REAL stored data and
persists it to Memory (analyses table, kind='cio_brief').
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select

from core.desk.context import ContextBuilder
from core.playbooks.base import assemble_technicals


@dataclass(frozen=True)
class ModeSpec:
    key: str
    title: str
    keywords: tuple[str, ...]


MODES: dict[str, ModeSpec] = {
    "PRE_LONDON": ModeSpec("PRE_LONDON", "ORION PRE-LONDON",
                           ("pre-london", "prelondres", "pre londres",
                            "pre-londres", "prelondon")),
    "PRE_NY": ModeSpec("PRE_NY", "ORION PRE-NY",
                       ("pre-ny", "pre ny", "preny", "pre new york",
                        "pre-nueva york")),
    "DAILY_CLOSE": ModeSpec("DAILY_CLOSE", "ORION DAILY CLOSE",
                            ("daily close", "cierre del dia", "cierre del día",
                             "cierre diario", "cierre de jornada")),
}

DEFAULT_MODE_ASSET = {"PRE_LONDON": "XAUUSD", "PRE_NY": "XAUUSD",
                      "DAILY_CLOSE": "XAUUSD"}


def detect_mode(question: str) -> str | None:
    q = question.lower()
    for spec in MODES.values():
        if any(kw in q for kw in spec.keywords):
            return spec.key
    return None


async def build_mode_brief(session_factory, mode_key: str, symbol: str | None = None) \
        -> dict:
    """Assemble the mode-specific brief. Returns dict(reply=..., stack=...)."""
    spec = MODES[mode_key]
    asset = (symbol or DEFAULT_MODE_ASSET[mode_key]).upper()
    builder = ContextBuilder(session_factory)
    stack = await assemble_technicals(builder, asset)
    ctx = stack.ctx
    ms = ctx.get("market_state") or {}

    lines: list[str] = [spec.title, f"ASSET: {asset}", ""]
    clock_block = ctx.get("session") or {}
    clock = clock_block.get("value") or {}
    lines.append(f"SESSION: {', '.join(clock.get('active') or []) or 'CLOSED / thin'}")

    # --- shared header block: macro cross-asset quotes
    price_block = ctx.get("price") or {}
    v = price_block.get("value")
    lines.append("")
    lines.append("MACRO SNAPSHOT:")
    lines.append(f"- {asset}: {v:g} [{price_block.get('status')}]"
                 if isinstance(v, (int, float)) else f"- {asset}: NOT AVAILABLE")
    extras = ctx.get("extra_quotes") or {}
    order = ("DXY", "US10Y", "US02Y", "VIX", "SPX", "NQ", "BTCUSD")
    for sym in order:
        block = extras.get(sym)
        if not isinstance(block, dict):
            continue
        val = block.get("value")
        lines.append(f"- {sym}: {val:g} [{block.get('status')}]"
                     if isinstance(val, (int, float)) else f"- {sym}: NOT AVAILABLE")
    cot = ctx.get("positioning_cftc") or {}
    cv = cot.get("value") or {}
    if isinstance(cv, dict) and cv.get("managed_money_net") is not None:
        lines.append(f"- CFTC managed money net: {cv['managed_money_net']:,.0f}")
    else:
        lines.append("- CFTC: NOT AVAILABLE")

    # --- session levels + liquidity state
    smap = stack.session_map if stack.session_map else None
    lines.append("")
    if smap:
        avail = [lv for lv in smap["levels"] if isinstance(lv["value"], (int, float))]
        lines.append("SESSION MAP (DERIVED):")
        if avail:
            for lv in avail:
                lines.append(f"- {lv['name']}: {lv['value']:g}")
        else:
            lines.append("- no levels computable from stored candles yet")
        for miss in smap.get("missing", []):
            lines.append(f"- {miss}: NOT AVAILABLE")

    lq = stack.liquidity if stack.liquidity else {}
    taken = [s for s in (stack.sweeps or [])]
    lines.append("")
    lines.append("LIQUIDITY:")
    pools = [f"{p['kind']}@{p['price']:g}" for p in lq.get("buy_side", [])[:3]] + \
            [f"{p['kind']}@{p['price']:g}" for p in lq.get("sell_side", [])[:3]]
    lines.append("- pending pools: " + (", ".join(pools) or "none mapped"))
    if taken:
        lines.append("- liquidity TAKEN recently: "
                     + ", ".join(f"{s['kind']}@{s['level']:g}" for s in taken[-3:]))
    else:
        lines.append("- liquidity TAKEN recently: none detected")

    bias = stack.bias_score or {}
    tq = stack.trade_quality or {}

    if mode_key == "PRE_LONDON":
        lines += _pre_london_sections(ctx, ms, bias, tq)
    elif mode_key == "PRE_NY":
        lines += _pre_ny_sections(ctx, ms, bias, tq, bool(taken))
    else:
        lines += _daily_close_sections(session_factory, ctx, ms, bias)

    reply = "\n".join(lines)
    return {"reply": reply, "mode": mode_key, "symbol": asset,
            "stack": stack.to_dict()}


# ------------------------------------------------------------------ sections
def _scenario_lines(bias_score: dict) -> tuple[list[str], list[str]]:
    band = bias_score.get("band", "NEUTRAL")
    total = bias_score.get("total", 50)
    bull = [
        f"bull scenario: score {total} ({band}) holds above mapped sell-side pools; "
        "reaction + confirmation at demand keeps long thesis alive",
        "invalidation: loss of range low with displacement",
    ]
    bear = [
        f"bear scenario: score {total} ({band}) fails at buy-side pools; "
        "sweep of highs without acceptance favors shorts",
        "invalidation: acceptance above range high on volume",
    ]
    return bull, bear


def _pre_london_sections(ctx, ms, bias, tq) -> list[str]:
    news = ctx.get("news") or []
    bull, bear = _scenario_lines(bias)
    alert_items = [f"- [{n.get('relevance', '?')}] {str(n.get('value'))[:100]} "
                   f"[{n.get('source')}]" for n in news[:3]]
    return [
        "",
        "ALERTA DEL DÍA:",
        *(alert_items if alert_items else ["- sin titulares verificados en ventana"]),
        "",
        f"REGIME: {ms.get('regime')} | vol={ms.get('volatility')} | "
        f"data_quality={(ms.get('data_quality') or 0):.0%}",
        "",
        f"BIAS SCORE: {bias.get('total', '?')} ({bias.get('band')}) "
        f"[missing: {', '.join(bias.get('missing_inputs') or []) or 'none'}]",
        f"TRADE QUALITY: {tq.get('total', '?')}",
        "",
        "BULL SCENARIO:",
        *(f"- {b}" for b in bull),
        "",
        "BEAR SCENARIO:",
        *(f"- {b}" for b in bear),
        "",
        "NO-TRADE CONDITIONS:",
        "- quote STALE o spread inviable",
        "- nivel clave sin reacción (doctrine: NO TRADE)",
        "- R:R < 2:1 o extensión > 2 ATR (no chase)",
        "- veto activo del risk-manager",
    ]


def _pre_ny_sections(ctx, ms, bias, tq, liquidity_taken: bool) -> list[str]:
    bull, bear = _scenario_lines(bias)
    event_items = [f"- [{n.get('relevance', '?')}] {str(n.get('value'))[:100]}"
                   for n in (ctx.get("news") or [])[:3]]
    return [
        "",
        "REVISIÓN DE SESIONES:",
        "- Asia/London H-L: ver SESSION MAP arriba (DERIVED)",
        f"- liquidez tomada: {'SÍ — ver sweeps' if liquidity_taken else 'no detectada'}",
        "- liquidez pendiente: ver LIQUIDITY arriba",
        "",
        "EVENT RISK:",
        *(event_items if event_items else ["- sin eventos verificados"]),
        "",
        f"BIAS SCORE: {bias.get('total', '?')} ({bias.get('band')}) "
        f"[missing: {', '.join(bias.get('missing_inputs') or []) or 'none'}]",
        f"TRADE QUALITY: {tq.get('total', '?')}",
        "",
        "BULL SCENARIO (NY target):",
        *(f"- {b}" for b in bull),
        "",
        "BEAR SCENARIO:",
        *(f"- {b}" for b in bear),
        "",
        "ENTRY CONDITIONS (all required):",
        "- precio EN zona con reacción verificada",
        "- confirmación estructural (displacement/CHoCH)",
        "- R:R ≥ 2:1 hacia liquidez pendiente",
        "- quote LIVE y veto riesgo despejado",
    ]


def _daily_close_sections(session_factory, ctx, ms, bias) -> list[str]:  # noqa: ANN001
    from core.memory.models import Analysis

    with session_factory() as session:
        rows = session.execute(
            select(Analysis).where(Analysis.kind.in_(("cio", "debate")))
            .order_by(desc(Analysis.ts)).limit(6)
        ).scalars().all()
    expected = next((r.output_summary.splitlines()[0] for r in reversed(rows)
                     if r.output_summary), "sin lecturas previas hoy")
    last = rows[0] if rows else None
    return [
        "",
        "QUÉ ESPERABA ORION:",
        f"- última lectura registrada: {expected[:160]}",
        "",
        "QUÉ OCURRIÓ:",
        f"- cierre de sesión activo; regime={ms.get('regime')} "
        f"| vol={ms.get('volatility')} | dq={(ms.get('data_quality') or 0):.0%}",
        f"- último análisis persistido: {last.ts.isoformat()[:16] if last else 'ninguno'}"
        f" ({last.kind if last else '-'})",
        "",
        "DRIVERS QUE FUNCIONARON / FALLARON:",
        "- evaluación honesta requiere outcome loop: los drivers se marcan al "
        "evaluar DoctrineJournal (MFE/MAE); sin velas suficientes queda PENDING.",
        "",
        "LESSON LEARNED:",
        "- se registra en doctrine_journal al evaluar el outcome (P16).",
    ]
