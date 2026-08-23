"""CIOOrchestrator — single entry point of the desk.

Pipeline (deterministic, no LLM):
route → context → specialists → RISK gate → AUDIT gate → synthesis.
Every answer separates FACTS (verified feeds) from INFERENCES (synthesis),
declares confidence, gates any PLAN behind Risk/Audit vetoes and lists
data gaps instead of inventing numbers.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select

from core.config import get_settings
from core.desk.context import ContextBuilder
from core.desk.journal import record_decision
from core.desk.modes import MODES
from core.desk.router import IntentRouter
from core.desk.specialists import SPECIALIST_FUNCS, SpecialistOpinion
from core.memory.models import Analysis, Quote

logger = logging.getLogger("orion.cio")

DEFAULT_ASSET = {
    "metal": "XAUUSD", "crypto": "BTCUSD", "index": "SPX", "macro": "DXY",
    "fx": "EURUSD",
}

_CONF_ORDER = {"LOW": 0, "MODERATE": 1, "HIGH": 2, "VERY HIGH": 3}


def _cap(confidence: str, cap: str) -> str:
    return confidence if _CONF_ORDER.get(confidence, 0) <= _CONF_ORDER.get(cap, 3) else cap


class CIOOrchestrator:
    def __init__(self, session_factory, registry) -> None:
        self.session_factory = session_factory
        self.registry = registry
        self.router = IntentRouter()
        self.context_builder = ContextBuilder(session_factory)

    # ---------------------------------------------------------------- public
    async def handle(self, question: str) -> dict:
        try:
            decision = self.router.route(question)
            activity: list[dict] = [
                {"agent": "orion-cio",
                 "action": f"routed intent={decision.intent}", "status": "ok"},
            ]

            if decision.intent == "SYSTEM":
                out = self._system_report(decision)
            elif decision.intent == "DESK_DEBATE":
                out = await self._run_debate(decision, activity)
            elif decision.intent == "GOLD_PLAYBOOK":
                out = await self._run_playbook("gold", decision.asset or "XAUUSD",
                                               activity)
            elif decision.intent == "XRP_PLAYBOOK":
                out = await self._run_playbook("xrp", "XRPUSD", activity)
            elif decision.intent in MODES:
                out = await self._run_mode(decision, activity)
            elif decision.intent == "WATCH":
                out = await self._run_watch(decision, question, activity)
            else:
                out = await self._run_pipeline(decision, question, activity)

            self.registry.record_run("orion-cio")
            self._persist_analysis(out, decision, question)
            return out
        except Exception as exc:  # noqa: BLE001 — the CIO must always answer honestly
            logger.exception("CIO pipeline failure")
            self.registry.record_error("orion-cio", str(exc))
            return {
                "reply": (
                    "CIO pipeline FAILED before producing a desk read.\n"
                    f"ERROR: {exc}\nNo analysis is offered without verified data."
                ),
                "routing": {"intent": "FAILED", "asset": None},
                "activity": [
                    {"agent": "orion-cio", "action": "pipeline error",
                     "status": "failed"}],
                "sources": [],
                "audit": {"verdict": "FAILED", "gaps": []},
            }

    # --------------------------------------------------------------- pipeline
    async def _run_pipeline(self, decision, question: str, activity: list[dict]) -> dict:  # noqa: ANN001
        asset = decision.asset or DEFAULT_ASSET.get(decision.asset_class or "", None)
        sources: list[dict] = []

        if asset is None:
            return self._macro_only_reply(activity)

        ctx = await self.context_builder.build(asset)
        activity.append({"agent": "market-data-engineer",
                         "action": f"context built for {asset}", "status": "ok"})
        self.registry.record_run("market-data-engineer")

        opinions: list[SpecialistOpinion] = []
        for agent_id in decision.required_agents:
            fn = SPECIALIST_FUNCS.get(agent_id)
            if fn is None:
                continue
            try:
                op = fn(ctx)
                opinions.append(op)
                self.registry.record_run(agent_id)
                activity.append({"agent": agent_id, "action": op.summary[:80], "status": "ok"})
            except Exception as exc:  # noqa: BLE001
                self.registry.record_error(agent_id, str(exc))
                activity.append({"agent": agent_id,
                                 "action": "specialist failed", "status": "error"})

        risk_view = self._risk_gate(ctx, opinions)
        self.registry.record_run("risk-manager")
        activity.append({
            "agent": "risk-manager",
            "action": f"gate={risk_view['gate']} ({'; '.join(risk_view['reasons'][:2])})",
            "status": "veto" if risk_view["blocked"] else "ok",
        })

        audit = self._audit_gate(ctx, decision, opinions)
        self.registry.record_run("audit-agent")
        activity.append({
            "agent": "audit-agent",
            "action": f"data gaps={len(audit['gaps'])}",
            "status": "warn" if audit["gaps"] else "ok",
        })

        # --- doctrine scoring (P11-P14) from the SAME verified context
        from core.playbooks.base import score_context

        scoring = score_context(ctx)
        activity.append({"agent": "quant-architect",
                         "action": "doctrine scored (bias/trade-quality/decision)",
                         "status": "ok"})

        reply = self._synthesize(asset, decision, ctx, opinions, risk_view, audit,
                                 scoring)
        sources = self._collect_sources(ctx)

        # --- P16 memory loop: persist the decision for later outcome review
        bias_score = scoring.get("bias_score") or {}
        tq = scoring.get("trade_quality") or {}
        dec = scoring.get("decision") or {}
        clock = ((ctx.get("session") or {}).get("value") or {})
        journal_id = record_decision(
            self.session_factory,
            symbol=asset,
            session_name=", ".join(clock.get("active") or []) or None,
            bias=next((ln.split(":")[1].strip() for ln in reply.splitlines()
                       if ln.startswith("BIAS:")), None),
            bias_score=bias_score.get("total"),
            trade_quality=tq.get("total"),
            decision=("NO_TRADE" if risk_view["blocked"]
                      else dec.get("status", "WAIT")),
            entry_conditions={"checks": dec.get("checks"), "reasons": dec.get("reasons")},
            liquidity_snapshot={
                k: tech for k, tech in ((ctx.get("technicals") or {}).items())
                if isinstance(tech, dict)},
            risk_verdict=((risk_view.get("snapshot") or {}).get("verdict")),
            reference_price=(ctx.get("price") or {}).get("value")
            if isinstance((ctx.get("price") or {}).get("value"), (int, float))
            else None,
        )
        if journal_id is not None:
            sources.append({"field": "doctrine_journal", "source": "db:journal",
                            "ts": None, "provenance": "DERIVED", "id": journal_id})
        return {
            "reply": reply,
            "routing": decision.to_dict(),
            "activity": activity,
            "sources": sources,
            "audit": audit,
            "scores": {
                "bias_score": bias_score,
                "trade_quality": tq,
                "decision": dec,
            },
        }

    def _risk_gate(self, ctx: dict, opinions: list[SpecialistOpinion]) -> dict:
        reasons: list[str] = []
        blocked = False
        gate = "GREEN"

        price = ctx.get("price") or {}
        pval, pprov, pstatus = price.get("value"), price.get("provenance"), price.get("status")
        if pval is None or pprov == "NOT_AVAILABLE":
            blocked, gate = True, "RED"
            reasons.append("no verified quote for this asset")
        elif pstatus in ("STALE", "DISCONNECTED"):
            blocked, gate = True, "RED"
            reasons.append(f"quote {pstatus} — refusing to plan on stale data")

        snap_block = ctx.get("risk_snapshot") or {}
        snap = snap_block.get("value") if isinstance(snap_block, dict) else None
        verdict = snap.get("verdict") if isinstance(snap, dict) else None
        if verdict == "RED_LIGHT":
            blocked, gate = True, "RED"
            reasons.append("desk risk verdict RED_LIGHT")
        elif verdict == "CAUTION" and not blocked:
            gate = "AMBER"
            reasons.append("desk risk verdict CAUTION — reduced size only")

        for op in opinions:
            if op.agent == "quant-architect" and op.stance == "REJECT":
                blocked, gate = True, "RED"
                reasons.append(f"quant veto: {op.summary}")
            if op.agent == "liquidity-analyst" and op.stance == "REJECT":
                blocked, gate = True, "RED"
                reasons.append("liquidity veto: spread/trading conditions unacceptable")
        return {"blocked": blocked, "gate": gate, "reasons": reasons or ["limits within tolerance"],
                "snapshot": snap}

    def _audit_gate(self, ctx: dict, decision, opinions: list[SpecialistOpinion]) -> dict:  # noqa: ANN001
        gaps: list[str] = []
        price = ctx.get("price") or {}
        if price.get("provenance") == "NOT_AVAILABLE":
            gaps.append("price")
        if not isinstance(ctx.get("candles"), dict) or not isinstance(
            (ctx.get("candles") or {}).get("value"), dict
        ):
            gaps.append("candle history")
        cot = (ctx.get("positioning_cftc") or {})
        if isinstance(cot, dict) and cot.get("provenance") == "NOT_AVAILABLE":
            gaps.append("CFTC positioning")
        news = ctx.get("news") or []
        if not news:
            gaps.append("recent headlines")

        conf_cap = "VERY HIGH"
        if len(gaps) >= 2:
            conf_cap = "LOW"
        elif gaps:
            conf_cap = "MODERATE"

        states = sorted({op.confidence for op in opinions},
                        key=lambda c: _CONF_ORDER.get(c, 0))
        overall = states[0] if states else "LOW"
        return {
            "verdict": "PASS_WITH_GAPS" if gaps else "PASS",
            "gaps": gaps,
            "confidence_cap": conf_cap,
            "weakest_specialist_confidence": overall,
            "checked_fields": ["price", "candles", "regime", "correlations",
                               "positioning_cftc", "news", "risk_snapshot", "session"],
        }

    # ------------------------------------------------------------- synthesis
    def _synthesize(self, asset, decision, ctx, opinions, risk_view, audit,
                    scoring: dict | None = None) -> str:  # noqa: ANN001
        ms = ctx.get("market_state") or {}
        bias_votes = [op.stance for op in opinions if op.stance in ("LONG", "SHORT")]
        long_n, short_n = bias_votes.count("LONG"), bias_votes.count("SHORT")
        if risk_view["blocked"]:
            bias = "WAIT"
        elif long_n > short_n:
            bias = "LONG"
        elif short_n > long_n:
            bias = "SHORT"
        else:
            bias = "NEUTRAL"

        confidence = _cap(audit["confidence_cap"], audit["confidence_cap"])
        weakest = audit["weakest_specialist_confidence"]
        confidence = _cap(weakest, confidence)

        bias_score = (scoring or {}).get("bias_score") or {}
        tq = (scoring or {}).get("trade_quality") or {}
        dec = (scoring or {}).get("decision") or {}
        doctrine_status = ("NO_TRADE" if risk_view["blocked"]
                           else dec.get("status", "WAIT"))

        price = (ctx.get("price") or {}).get("value")
        lines: list[str] = [f"ORION CIO — {asset} DESK READ", ""]
        lines.append(f"BIAS: {bias}")
        lines.append(f"BIAS SCORE: {bias_score.get('total', 'n/a')} "
                     f"({bias_score.get('band', 'NEUTRAL')}) [missing inputs: "
                     f"{', '.join(bias_score.get('missing_inputs') or []) or 'none'}]")
        lines.append(f"TRADE QUALITY: {tq.get('total', 'n/a')}")
        lines.append(f"DECISION: {doctrine_status}"
                     + (f" — {dec['reasons'][0]}" if dec.get("reasons") else ""))
        cap_note = (
            f" (capped — data gaps: {', '.join(audit['gaps'])})" if audit["gaps"] else ""
        )
        lines.append(f"CONFIDENCE: {confidence}" + cap_note)
        lines.append(
            f"MARKET STATE: regime={ms.get('regime')} | volatility={ms.get('volatility')}"
            f" | risk_mode={ms.get('risk_mode')} | data_quality={(ms.get('data_quality') or 0):.0%}"
        )
        lines.append("")
        lines.append("FACTS:")
        if isinstance(price, (int, float)):
            pb = ctx.get("price") or {}
            lines.append(f"- spot {price:g} [{pb.get('source')} · {pb.get('status')}]")
        else:
            lines.append("- spot: NOT AVAILABLE")
        extras = ctx.get("extra_quotes") or {}
        for sym, block in extras.items():
            v = block.get("value")
            if isinstance(v, (int, float)):
                lines.append(f"- {sym} {v:g} [{block.get('source')} · {block.get('status')}]")
            else:
                lines.append(f"- {sym}: NOT AVAILABLE ({block.get('reason', 'no feed')})")

        lines.append("")
        lines.append("INFERENCES (per specialist):")
        for op in opinions:
            lines.append(f"- {op.agent}: {op.stance} · {op.confidence} — {op.summary}")
            for kp in op.key_points[:3]:
                lines.append(f"    · {kp}")

        lines.append("")
        lines.append("RISK:")
        lines.append(f"- gate {risk_view['gate']}: " + "; ".join(risk_view["reasons"]))
        snap = risk_view.get("snapshot") or {}
        if snap:
            lines.append(
                f"- desk snapshot: equity {snap.get('equity')} | verdict {snap.get('verdict')}"
                f" | daily risk used {snap.get('daily_risk_used')}"
            )

        lines.append("")
        lines.append("PLAN:")
        if risk_view["blocked"]:
            lines.append("- NO TRADE — veto active. Re-evaluate after conditions clear.")
            for r in risk_view["reasons"]:
                lines.append(f"  · {r}")
        elif doctrine_status in ("WAIT", "NO_TRADE", "REJECT"):
            lines.append(f"- WAIT — doctrine gate: {doctrine_status}.")
            for r in (dec.get("reasons") or [])[:3]:
                lines.append(f"  · {r}")
            lines.append("  · a bias is NOT an entry: level + reaction + confirmation"
                         " + R:R ≥ 2 required")
        elif bias == "WAIT" or bias == "NEUTRAL":
            lines.append("- WAIT — no edge worth institutional risk right now.")
        else:
            candles = (ctx.get("candles") or {}).get("value") or {}
            hi = candles.get("swing_high_20")
            lo = candles.get("swing_low_20")
            atr = candles.get("atr")
            direction = "BUY" if bias == "LONG" else "SELL"
            lines.append(f"- PRELIMINARY {direction} setup (internal label, NOT advice):")
            if isinstance(price, (int, float)):
                lines.append(f"  · reference entry zone: near {price:g}")
            if lo and hi:
                invalidation = lo if bias == "LONG" else hi
                side = "below" if bias == "LONG" else "above"
                lines.append(f"  · structural invalidation: {side} {invalidation:g}")
            if atr and isinstance(price, (int, float)):
                stop_dist = atr * 1.5
                sl = price - stop_dist if bias == "LONG" else price + stop_dist
                t1 = price + 2 * stop_dist if bias == "LONG" else price - 2 * stop_dist
                lines.append(f"  · ATR-based SL {sl:g} / T1 {t1:g} (1.5R)")
            lines.append("  · activation: only after human approval + fresh quote re-check")

        lines.append("")
        if audit["gaps"]:
            lines.append("DATA GAPS: " + ", ".join(audit["gaps"]))
        else:
            lines.append("DATA GAPS: none — all checked fields verified.")
        clock = (ctx.get("session") or {}).get("value") or {}
        active = clock.get("active") or []
        tail = "none (thin liquidity caution)" if not active else ", ".join(active)
        lines.append(f"SESSIONS ACTIVE: {tail}")
        lines.append("")
        lines.append(self._natural_line(bias, confidence, asset, risk_view))
        return "\n".join(lines)

    @staticmethod
    def _natural_line(bias: str, confidence: str, asset: str, risk_view: dict) -> str:
        if risk_view["blocked"]:
            first = risk_view["reasons"][0] if risk_view["reasons"] else "veto activo"
            return f"En cristiano: no toco {asset} ahora mismo — {first}."
        if bias == "WAIT":
            return f"En cristiano: {asset} sin ventaja clara; me espero."
        if bias == "NEUTRAL":
            return (f"En cristiano: {asset} sin sesgo definido aún "
                    f"(confianza {confidence.lower()}); espero confirmación antes de idea.")
        verb = "sesgo comprador" if bias == "LONG" else "sesgo vendedor"
        return (f"En cristiano: veo {verb} en {asset} con confianza "
                f"{confidence.lower()}, sujeto al veto de riesgo.")

    def _collect_sources(self, ctx: dict) -> list[dict]:
        out: list[dict] = []
        for key in ("price", "candles", "positioning_cftc", "risk_snapshot", "session"):
            block = ctx.get(key)
            if isinstance(block, dict) and block.get("provenance") != "NOT_AVAILABLE":
                out.append({"field": key, "source": block.get("source"),
                            "ts": block.get("ts"), "provenance": block.get("provenance")})
        for pair, block in (ctx.get("correlations") or {}).items():
            if isinstance(block, dict) and isinstance(block.get("value"), (int, float)):
                out.append({"field": f"corr:{pair}", "source": block.get("source"),
                            "ts": block.get("ts"), "provenance": "DERIVED"})
        for n in (ctx.get("news") or [])[:4]:
            if isinstance(n, dict):
                out.append({"field": "news", "source": n.get("source"),
                            "ts": n.get("ts"), "provenance": "VERIFIED"})
        return out

    # ---------------------------------------------------------------- debate
    async def _run_debate(self, decision, activity: list[dict]) -> dict:  # noqa: ANN001
        from core.debate.engine import DeskDebateEngine

        asset = decision.asset or DEFAULT_ASSET.get(decision.asset_class or "", "XAUUSD")
        engine = DeskDebateEngine(self.session_factory)
        debate = await engine.convene(asset)
        for agent in ("macro-strategist", "liquidity-analyst", "crossasset-analyst",
                      "quant-architect", "news-intelligence", "positioning-analyst",
                      "metals-analyst", "crypto-analyst", "equities-analyst",
                      "risk-manager", "audit-agent"):
            self.registry.record_run(agent)
        activity.append({"agent": "desk", "action": f"debate convened on {asset}", "status": "ok"})
        s = debate.cio_synthesis
        votes = ", ".join(f"{o.agent.split('-')[0]}:{o.bias}" for o in debate.opinions)
        reply_lines = [
            f"ORION DESK DEBATE — {asset}",
            f"DEBATE ID: {debate.debate_id} · convened {debate.convened_at.isoformat()}",
            "",
            "OPINIONS:",
        ]
        for o in debate.opinions:
            reply_lines.append(
                f"- {o.agent}: {o.bias} · {o.confidence} · strength {o.strength:.0f}")
        reply_lines += [
            "",
            f"CONSENSUS: score {debate.consensus.get('score')} ({debate.consensus.get('label')}, "
            f"agreement {debate.consensus.get('agreement')}) [internal tag]",
            f"AUDIT OVERALL: {debate.audit_overall}",
            "RISK CONSTRAINTS: "
            f"verdict={debate.risk_constraints.verdict} notes={debate.risk_constraints.notes}",
            "",
            "CIO SYNTHESIS:",
            f"BIAS: {s.bias_label}",
            f"SCENARIO: {s.scenario}",
            "KEY CONDITIONS: " + ("; ".join(s.key_conditions) if s.key_conditions else "—"),
            f"DISSENT: {s.dissent_summary}",
            f"PROVENANCE: {s.provenance}",
            "",
            f"(votes: {votes})",
            f"En cristiano: la mesa debate {asset}; consenso interno '{s.bias_label}' "
            f"y auditoría '{debate.audit_overall}'. Nada se ejecuta sin aprobación humana.",
        ]
        sources = [{
            "field": "debate", "source": "DeskDebateEngine",
            "ts": debate.convened_at.isoformat(), "provenance": "DERIVED",
        }]
        return {"reply": "\n".join(reply_lines), "routing": decision.to_dict(),
                "activity": activity, "sources": sources,
                "audit": {"verdict": debate.audit_overall, "gaps": debate.discrepancies}}

    # ------------------------------------------------------- doctrine modes
    async def _run_playbook(self, kind: str, asset: str, activity: list[dict]) -> dict:
        """P3/P4 — Gold & XRP playbooks."""
        if kind == "gold":
            from core.playbooks.gold import run_gold_playbook

            result = await run_gold_playbook(self.session_factory, asset)
            primary = "metals-analyst"
        else:
            from core.playbooks.xrp import run_xrp_playbook

            result = await run_xrp_playbook(self.session_factory)
            primary = "crypto-analyst"
            asset = "XRPUSD"

        for agent in (primary, "macro-strategist", "liquidity-analyst",
                      "positioning-analyst", "crossasset-analyst",
                      "news-intelligence", "quant-architect", "risk-manager",
                      "audit-agent"):
            self.registry.record_run(agent)
        activity.append({"agent": primary,
                         "action": f"{kind.upper()} playbook assembled",
                         "status": "ok"})
        activity.append({"agent": "quant-architect",
                         "action": "doctrine scores computed", "status": "ok"})

        stack = result.get("stack") or {}
        smap = stack.get("session_levels") or {}
        gaps: list[str] = ["volume/order-flow feed (NOT AVAILABLE)"]
        if smap.get("missing"):
            gaps.append(f"session candle history ({len(smap['missing'])} levels)")
        sources = self._collect_sources(result.get("ctx") or {})
        return {
            "reply": result["brief"],
            "routing": {"intent": f"{kind.upper()}_PLAYBOOK", "asset": asset,
                        "asset_class": "metal" if kind == "gold" else "crypto"},
            "activity": activity,
            "sources": sources,
            "audit": {"verdict": "PASS_WITH_GAPS", "gaps": gaps,
                      "confidence_cap": "MODERATE"},
            "scores": {"bias_score": stack.get("bias_score"),
                       "trade_quality": stack.get("trade_quality"),
                       "decision": stack.get("decision")},
            "doctrine": stack,
        }

    async def _run_mode(self, decision, activity: list[dict]) -> dict:  # noqa: ANN001
        """P15 — PRE-LONDON / PRE-NY / DAILY CLOSE briefs."""
        from core.desk.modes import build_mode_brief

        result = await build_mode_brief(self.session_factory, decision.intent,
                                        decision.asset)
        for agent in ("macro-strategist", "liquidity-analyst", "news-intelligence",
                      "risk-manager", "audit-agent"):
            self.registry.record_run(agent)
        activity.append({"agent": "macro-strategist",
                         "action": f"{decision.intent} brief compiled", "status": "ok"})
        # persist to Memory (analyses.kind='cio_brief')
        try:
            with self.session_factory() as session:
                session.add(Analysis(
                    agent="orion-cio", asset=result["symbol"], kind="cio_brief",
                    input_data={"mode": decision.intent},
                    output_summary=result["reply"][:1000],
                    full_output=result["reply"], stance=None, confidence=None,
                    model="deterministic-cio-v1"))
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not persist CIO mode brief")
        return {
            "reply": result["reply"],
            "routing": decision.to_dict(),
            "activity": activity,
            "sources": [{"field": "session_map", "source": "core.doctrine",
                         "ts": None, "provenance": "DERIVED"}],
            "audit": {"verdict": "PASS_WITH_GAPS",
                      "gaps": ["outcome evaluation pending (memory loop)"]},
            "scores": {
                "bias_score": (result.get("stack") or {}).get("bias_score"),
                "trade_quality": (result.get("stack") or {}).get("trade_quality"),
                "decision": (result.get("stack") or {}).get("decision")},
            "doctrine": result.get("stack"),
        }

    async def _run_watch(self, decision, question: str, activity: list[dict]) -> dict:
        """P34 — WATCH MODE. Surveillance only, NEVER executes."""
        from core.desk.watch import create_watch, evaluate_watches

        asset = decision.asset or "XAUUSD"
        note = question[:500]
        zone_low = zone_high = None
        try:
            ctx = await self.context_builder.build(asset)
            zone = ((ctx.get("technicals") or {}).get("orion_range_2_6") or {})
            band = zone.get("zone_band")
            if isinstance(band, (list, tuple)) and len(band) == 2:
                zone_low, zone_high = float(band[0]), float(band[1])
        except Exception as exc:  # noqa: BLE001 — provisional band is acceptable
            logger.info("watch zone derivation fell back to provisional: %s", exc)
        watch = create_watch(self.session_factory, asset, note,
                             zone_low=zone_low, zone_high=zone_high)
        states = evaluate_watches(self.session_factory)
        self.registry.record_run("market-data-engineer")
        activity.append({"agent": "market-data-engineer",
                         "action": f"watch #{watch['id']} on {asset}",
                         "status": "ok"})
        lines = [
            f"ORION WATCH MODE — {asset}",
            f"- watch id: {watch['id']} · state: {watch['state']}",
            f"- reaction zone: {watch['zone']}" if watch["zone"] else
            "- reaction zone: provisional (±band around live quote until "
            "candles allow ORION_RANGE_2_6)",
            "- sequence: WATCHING → ARMED (price in zone) → CONFIRMED (mechanical "
            "reaction) | INVALIDATED/CANCELLED by you",
            "- WATCH MODE NEVER EXECUTES ORDERS.",
            f"- active watches: {len(states)}",
        ]
        return {
            "reply": "\n".join(lines),
            "routing": decision.to_dict(),
            "activity": activity,
            "sources": [{"field": "watch", "source": "db:watch_requests",
                         "ts": watch["ts"], "provenance": "VERIFIED"}],
            "audit": {"verdict": "PASS",
                      "gaps": [] if watch["zone"] else ["no stored candles yet — "
                                                        "provisional band"]},
            "watch": watch,
        }

    # ----------------------------------------------------------------- macro
    def _macro_only_reply(self, activity: list[dict]) -> dict:
        from core.sessions import desk_clock

        clock = desk_clock()
        with self.session_factory() as session:
            total = len(session.execute(select(Quote.id)).scalars().all())
        macro_lines = [
            "ORION MACRO BRIEF",
            f"- sessions active: {', '.join(clock.active_sessions) or 'none'}"
            f" | next event: {clock.next_event_name}",
            f"- stored quotes rows: {total:,}",
        ]
        self.registry.record_run("macro-strategist")
        activity.append({"agent": "macro-strategist",
                         "action": "macro brief compiled", "status": "ok"})
        return {
            "reply": "\n".join(macro_lines),
            "routing": {"intent": "MACRO", "asset": None},
            "activity": activity,
            "sources": [{"field": "session", "source": "core.sessions.desk_clock",
                         "ts": clock.utc.isoformat(), "provenance": "VERIFIED"}],
            "audit": {"verdict": "PASS_WITH_GAPS",
                      "gaps": ["no specific asset requested — ask e.g. 'analiza XAUUSD'"]},
        }

    # ---------------------------------------------------------------- system
    def _system_report(self, decision) -> dict:  # noqa: ANN001
        from datetime import timedelta

        stale_after = get_settings().monitor_quote_staleness_sec
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_after * 5)
        with self.session_factory() as session:
            symbols = session.execute(
                select(Quote.symbol).distinct()
            ).scalars().all()
            recent = session.execute(
                select(Quote.symbol, Quote.ts_received)
                .order_by(desc(Quote.ts_received)).limit(400)
            ).scalars().all()
        fresh_symbols = sorted({
            sym for sym, ts in recent
            if (ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts) >= cutoff
        })
        lines = [
            "ORION SYSTEM STATUS",
            f"- distinct symbols ever stored: {len(symbols)}",
            f"- symbols with fresh quotes (<{stale_after * 5}s): {len(fresh_symbols)}",
            f"- fresh sample: {', '.join(fresh_symbols[:12])}",
            "- pipeline: quotes/news ingestion via background monitor; desk API up.",
        ]
        self.registry.record_run("market-data-engineer")
        return {
            "reply": "\n".join(lines),
            "routing": decision.to_dict(),
            "activity": [{"agent": "market-data-engineer",
                          "action": "feed freshness scan", "status": "ok"}],
            "sources": [{"field": "quotes", "source": "db", "ts": datetime.now(UTC).isoformat(),
                         "provenance": "VERIFIED"}],
            "audit": {"verdict": "PASS", "gaps": []},
        }

    # ------------------------------------------------------------ persistence
    def _persist_analysis(self, out: dict, decision, question: str) -> None:  # noqa: ANN001
        if decision.intent in ("SYSTEM", "WATCH"):
            return
        try:
            with self.session_factory() as session:
                session.add(Analysis(
                    agent="orion-cio",
                    asset=(decision.asset or DEFAULT_ASSET.get(decision.asset_class or "")) or None,
                    kind="cio",
                    input_data={"question": question[:500], "routing": decision.to_dict()},
                    output_summary=out["reply"][:1000],
                    full_output=out["reply"],
                    stance=next((ln.split(":")[1].strip() for ln in out["reply"].splitlines()
                                 if ln.startswith("BIAS:")), None),
                    confidence=next((ln.split("CONFIDENCE:")[1].split()[0].strip()
                                     for ln in out["reply"].splitlines()
                                     if ln.startswith("CONFIDENCE:")), None),
                    model="deterministic-cio-v1",
                ))
                session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("could not persist CIO analysis")
