"""Specialist responders — one per desk role (data-backed, deterministic)."""

from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from agents.base import AgentReply, BaseResponder, DataAwareResponder
from core.memory.models import Alert, NewsItem, Position, RiskSnapshot


class MacroResponder(DataAwareResponder):
    name = "macro"
    symbols = ["DXY", "US10Y", "US02Y", "SPX"]
    role_description = (
        "tipos/yields/DXY/inflacion; cross-asset (DXY down + real yields down -> "
        "tailwind GOLD; yields up -> presion growth)."
    )


class MetalsResponder(DataAwareResponder):
    name = "metals"
    symbols = ["XAUUSD", "XAGUSD"]
    role_description = "oro/plata: DXY, real yields, COT Managed Money/Commercials, ETF flows."


class CryptoResponder(DataAwareResponder):
    name = "crypto"
    symbols = ["BTCUSD", "ETHUSD", "XRPUSD", "SOLUSD"]
    role_description = "spot vs perps siempre distinguidos: funding, OI, liquidations, flujos."


class EquitiesResponder(DataAwareResponder):
    name = "equities"
    symbols = ["SPX", "NASDAQ", "NQ", "ES", "DAX"]
    role_description = "breadth, rotacion sectorial, gamma, relative strength vs SPX."


class LiquidityResponder(DataAwareResponder):
    name = "liquidity"
    symbols = ["XAUUSD", "NQ", "BTCUSD"]
    role_description = (
        "perfil de volumen, VWAP anclado, pools de liquidez y zonas dealer "
        "(solo con datos reales del feed; sin feed tick-a-tick lo declaro)."
    )


class NewsResponder(BaseResponder):
    name = "news"

    def respond(self, question: str, session: Session) -> AgentReply:
        rows = (
            session.execute(select(NewsItem).order_by(desc(NewsItem.published_at)).limit(5))
            .scalars()
            .all()
        )
        if not rows:
            return AgentReply(
                self.name,
                "NO DATA AVAILABLE: no hay noticias ingestadas todavia.",
            )
        lines = ["FACTS: ultimas noticias ingestadas:"]
        for n in rows:
            lines.append(f"- [{n.relevance}] {n.title} ({n.source})")
        return AgentReply(self.name, "\n".join(lines))


class RiskResponder(BaseResponder):
    name = "risk"

    def respond(self, question: str, session: Session) -> AgentReply:
        snap = session.execute(
            select(RiskSnapshot).order_by(desc(RiskSnapshot.ts)).limit(1)
        ).scalar_one_or_none()
        open_pos = (
            session.execute(
                select(func.count()).select_from(Position).where(Position.status == "OPEN")
            ).scalar()
            or 0
        )
        if snap is None:
            return AgentReply(
                self.name,
                f"Posiciones abiertas: {open_pos}. NO RISK SNAPSHOT AVAILABLE: "
                "no hay snapshot aun; el monitor genera uno por ciclo. "
                "No inventare metricas de equity.",
            )
        content = (
            f"FACTS: equity={snap.equity:.2f} drawdown={snap.drawdown_pct:.1f}% "
            f"riesgo diario usado={snap.daily_risk_used:.2f}% "
            f"semanal={snap.weekly_risk_used:.2f}% exposicion={snap.exposure_total:.0f} "
            f"abiertas={open_pos}\nVEREDICTO GLOBAL: {snap.verdict or 'N/A'}"
        )
        if snap.expectancy_r is not None:
            content += (
                f" | win_rate={snap.win_rate} PF={snap.profit_factor} exp={snap.expectancy_r}R"
            )
        pending = (
            session.execute(select(Alert).where(Alert.acknowledged_at.is_(None)).limit(5))
            .scalars()
            .all()
        )
        if pending:
            content += "\nALERTAS PENDIENTES: " + "; ".join(a.rule_name for a in pending)
        return AgentReply(self.name, content)


class CIOResponder(BaseResponder):
    """Coordinates specialists and reports desk-wide state."""

    name = "orion-cio"

    def __init__(self) -> None:
        self.specialists: tuple[BaseResponder, ...] = (
            MacroResponder(),
            MetalsResponder(),
            CryptoResponder(),
            EquitiesResponder(),
            NewsResponder(),
            RiskResponder(),
        )

    def respond(self, question: str, session: Session) -> AgentReply:
        sections = [f"ORION-CIO — estado de la mesa ({len(self.specialists)} especialistas)"]
        any_data = False
        for spec in self.specialists:
            reply = spec.respond(question, session)
            first_line = reply.content.splitlines()[0]
            sections.append(f"@{spec.name}: {first_line}")
            if "NO DATA" not in first_line:
                any_data = True
        if not any_data:
            sections.append(
                "MISSING DATA: ningun feed aporta datos frescos. La mesa NO PUEDE OPINAR "
                "hasta tener datos validos; arranca el monitor o conecta un provider."
            )
        else:
            sections.append("Desacuerdos y debate profundo: convoca la mesa completa (/desk).")
        return AgentReply(self.name, "\n".join(sections))


def build_responders() -> dict[str, BaseResponder]:
    responders: list[BaseResponder] = [
        CIOResponder(),
        MacroResponder(),
        NewsResponder(),
        EquitiesResponder(),
        CryptoResponder(),
        MetalsResponder(),
        LiquidityResponder(),
        RiskResponder(),
    ]
    return {r.name: r for r in responders}
