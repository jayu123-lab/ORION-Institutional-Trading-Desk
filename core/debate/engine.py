"""DeskDebateEngine — convenes the desk for one asset (spec PRIORITY 7).

Flow:
1. MarketBrain builds the deterministic MarketState (CIO input).
2. Each deterministic analyst produces a data-backed opinion.
3. WeightedConsensus computes the desk score; dissent is preserved.
4. Risk layer adds constraints from the latest snapshot.
5. Audit verifier stamps every opinion with a VerificationState.
6. CIO synthesis assembles the scenario from verified facts only.

Everything is persisted: Analysis(kind='debate') + AgentOpinion rows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.audit.verifier import AuditVerifier
from core.debate import analysts
from core.debate.schemas import (
    AgentOpinionSchema,
    CioSynthesis,
    DeskDebate,
    RiskConstraints,
)
from core.market_brain.brain import MarketBrain
from core.memory.models import AgentOpinion as DBAgentOpinion
from core.memory.models import Analysis, NewsItem, RiskSnapshot
from core.orchestration.consensus import ConsensusInput, compute_consensus

logger = logging.getLogger("orion.debate")

ROLE_MAP = {
    "orion-macro": "macro",
    "orion-metals": "technical",
    "orion-liquidity": "liquidity",
    "orion-positioning": "order_flow",
    "orion-crossasset": "technical",
    "orion-news": "news",
    "orion-quant": "quant",
}


class DeskDebateEngine:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.brain = MarketBrain(session_factory)
        self.auditor = AuditVerifier(session_factory)

    async def convene(self, asset: str) -> DeskDebate:
        asset = asset.upper()
        ms = await self.brain.build(asset)
        macro_closes = {s: self.brain._closes_from_db(s) for s in ("DXY", "US10Y", "VIX", "SPX")}
        gold_closes = self._closes_for_gold(asset)

        opinions = self._gather_opinions(asset, ms, macro_closes, gold_closes)
        consensus = self._consensus(opinions)
        risk_constraints = self._risk_constraints()
        discrepancies = self._feed_discrepancies(asset)
        audit_states = self._audit(opinions)

        synthesis = _cio_synthesis(ms, consensus, audit_states, opinions, discrepancies)

        debate = DeskDebate(
            debate_id=uuid.uuid4().hex[:16],
            asset=asset,
            convened_at=datetime.now(UTC),
            market_state=ms.model_dump(mode="json"),
            opinions=opinions,
            consensus={
                "score": consensus.score,
                "label": consensus.label,
                "agreement": consensus.agreement,
                "weights_used": consensus.weights_used,
                "n_inputs": consensus.n_inputs,
                "internal_tag_only": True,
            },
            risk_constraints=risk_constraints,
            audit_overall=_worst_state(audit_states, discrepancies),
            discrepancies=discrepancies,
            cio_synthesis=synthesis,
        )
        self._persist(debate)
        return debate

    # ------------------------------------------------------------- opinions
    def _gather_opinions(
        self,
        asset: str,
        ms,
        macro_closes: dict[str, list[float]],
        gold_closes: list[float],
    ) -> list[AgentOpinionSchema]:
        dxy_drag = bool(
            macro_closes.get("DXY")
            and len(macro_closes["DXY"]) >= 11
            and _roc(macro_closes["DXY"], 10) is not None
            and _roc(macro_closes["DXY"], 10) > 0
        )
        correlations = _asset_correlations(gold_closes, macro_closes)
        high_titles, total_news = self._recent_news()

        opinions = [
            analysts.macro_opinion(ms, macro_closes),
            analysts.quant_opinion(ms),
            analysts.liquidity_opinion(ms),
            analysts.positioning_opinion(ms),
            analysts.news_opinion(ms, high_titles, total_news),
            analysts.cross_asset_opinion(ms, correlations),
            analysts.metals_opinion(ms, dxy_drag=dxy_drag) if _is_metal(asset)
            else analysts.cross_asset_opinion(ms, correlations),
        ]
        for op in opinions:
            op.validate_bias()
        return opinions

    def _consensus(self, opinions: list[AgentOpinionSchema]):
        inputs = [
            ConsensusInput(
                agent=o.agent,
                role=ROLE_MAP.get(o.agent, "technical"),
                stance=o.bias,
                strength=o.strength,
            )
            for o in opinions
        ]
        return compute_consensus(inputs, asset_class=_asset_class(opinions[0].asset))

    def _risk_constraints(self) -> RiskConstraints:
        with self.session_factory() as session:
            snap = (
                session.execute(select(RiskSnapshot).order_by(RiskSnapshot.id.desc()).limit(1))
                .scalars()
                .first()
            )
        if snap is None:
            return RiskConstraints(verdict=None, notes=["no risk snapshot yet"])
        notes = [f"equity {snap.equity}, exposure {snap.exposure_total}"]
        if snap.verdict and snap.verdict != "GREEN_LIGHT":
            notes.append(f"risk verdict {snap.verdict} — sizing restricted")
        return RiskConstraints(verdict=snap.verdict, notes=notes)

    def _feed_discrepancies(self, asset: str) -> list[str]:
        try:
            return self.auditor.cross_feed_check(asset)
        except Exception:  # noqa: BLE001 - audit failure must not kill the debate
            logger.exception("cross-feed check failed")
            return []

    def _audit(self, opinions: list[AgentOpinionSchema]) -> dict[str, str]:
        states: dict[str, str] = {}
        for op in opinions:
            payload = op.model_dump(mode="json")
            states[op.agent] = self.auditor.audit_opinion(payload)
            op.verification_state = states[op.agent]
        return states

    # ------------------------------------------------------------------ io
    def _closes_for_gold(self, asset: str) -> list[float]:
        """Series used for GOLD correlation checks when the scope is a metal."""
        if _is_metal(asset):
            return self.brain._closes_from_db(asset)
        return self.brain._closes_from_db("XAUUSD") or self.brain._closes_from_db("GC")

    def _recent_news(self, hours: int = 24) -> tuple[list[str], int]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        with self.session_factory() as session:
            rows = (
                session.execute(
                    select(NewsItem).where(NewsItem.published_at >= since).limit(200)
                )
                .scalars()
                .all()
            )
        high = [r.title for r in rows if r.relevance == "HIGH"]
        return high, len(rows)

    def _persist(self, debate: DeskDebate) -> None:
        with self.session_factory() as session:
            analysis = Analysis(
                agent="orion-cio",
                asset=debate.asset,
                kind="debate",
                input_data={"debate_id": debate.debate_id},
                data_sources=[
                    {"symbol": s.symbol, "provider": s.provider, "ts": s.ts}
                    for op in debate.opinions
                    for s in op.data_sources
                ],
                output_summary=f"{debate.consensus['label']} | audit {debate.audit_overall}",
                full_output=debate.model_dump_json(),
                stance=debate.consensus["label"],
                confidence=_confidence_from_agreement(debate.consensus["agreement"]),
                model="deterministic-v1",
            )
            session.add(analysis)
            session.flush()
            for op in debate.opinions:
                session.add(
                    DBAgentOpinion(
                        analysis_id=analysis.id,
                        debate_id=debate.debate_id,
                        agent=op.agent,
                        asset=op.asset,
                        stance=op.bias,
                        strength=op.strength,
                        rationale=" | ".join(op.arguments)[:4000],
                        ts=op.timestamp,
                    )
                )
            session.commit()


# ------------------------------------------------------------------ helpers


def _is_metal(asset: str) -> bool:
    return any(m in asset.upper() for m in ("XAU", "XAG", "GC", "MGC", "SI"))


def _asset_class(asset: str) -> str:
    upper = asset.upper()
    if any(c in upper for c in ("BTC", "ETH", "SOL", "XRP")):
        return "crypto"
    if _is_metal(upper):
        return "metal"
    return "_default"


def _cio_synthesis(
    ms,
    consensus,
    audit_states: dict[str, str],
    opinions: list[AgentOpinionSchema],
    discrepancies: list[str],
) -> CioSynthesis:
    dissent_txt = (
        ", ".join(f"{a}:{s}" for a, s in consensus.dissent) if consensus.has_dissent else "none"
    )
    conditions = sorted({cond for o in opinions for cond in o.required_conditions})
    parts = [
        f"Desk score {consensus.score:+.2f} ({consensus.label}) "
        f"agreement {consensus.agreement:.0%}.",
        f"Regime {ms.regime.value}, volatility {ms.volatility.value}, "
        f"risk mode {ms.risk_mode.value}.",
    ]
    if ms.macro_score is not None:
        parts.append(f"Macro gauge {ms.macro_score:+.2f}.")
    else:
        parts.append("Macro gauge NOT AVAILABLE.")
    if discrepancies:
        parts.append(f"FEED DISCREPANCIES DETECTED: {'; '.join(discrepancies)}")
        parts.append("No new execution until feeds reconcile (DIVERGENT block applies).")
    unverified = [a for a, s in audit_states.items() if s != "VERIFIED"]
    if unverified:
        parts.append(f"Audit flags insufficient/unverified evidence from: {', '.join(unverified)}.")
    scenario = " ".join(parts)
    return CioSynthesis(
        bias_label=consensus.label,
        scenario=scenario,
        key_conditions=conditions[:8],
        dissent_summary=dissent_txt,
        provenance="INFERRED",
    )


def _confidence_from_agreement(agreement: float) -> str:
    if agreement >= 0.9:
        return "HIGH"
    if agreement >= 0.7:
        return "MODERATE"
    return "LOW"


def _roc(closes: list[float], lookback: int):
    import math

    if len(closes) <= lookback:
        return None
    a, b = closes[-(lookback + 1)], closes[-1]
    return math.log(b / a) if a > 0 and b > 0 else None


def _pearson(a: list[float], b: list[float]) -> float | None:
    n = min(len(a), len(b))
    if n < 10:
        return None
    x, y = a[-n:], b[-n:]
    mx, my = sum(x) / n, sum(y) / n
    vx = sum((v - mx) ** 2 for v in x)
    vy = sum((v - my) ** 2 for v in y)
    if not vx or not vy:
        return None
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    return cov / (vx**0.5 * vy**0.5)


def _asset_correlations(
    gold_closes: list[float], macro_closes: dict[str, list[float]]
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    dxy = macro_closes.get("DXY") or []
    spx = macro_closes.get("SPX") or []
    vix = macro_closes.get("VIX") or []
    out["GOLD_DXY"] = _pearson(gold_closes, dxy)
    out["SPX_VIX"] = _pearson(spx, vix)
    return out


def _worst_state(states: dict[str, str], discrepancies: list[str]) -> str:
    if discrepancies:
        return "CONFLICTING_DATA"
    order = [
        "VERIFIED",
        "PARTIALLY_VERIFIED",
        "INSUFFICIENT_EVIDENCE",
        "UNVERIFIED",
        "STALE_DATA",
        "CONFLICTING_DATA",
    ]
    vals = list(states.values()) or ["INSUFFICIENT_EVIDENCE"]
    worst_idx = max(order.index(v) if v in order else 2 for v in vals)
    return order[worst_idx]
