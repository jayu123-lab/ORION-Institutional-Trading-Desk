"""Programmatic agent responders powering the Desk Room chat API.

These are NOT the LLM personas (.opencode/agents/*). They are deterministic
data-backed respondents used by apps/api so chat works without an LLM key:
they read real DB state and answer factually, declaring NO DATA AVAILABLE
when feeds are empty/stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from core.market_data.base import DataStatus
from core.memory.models import Analysis, Quote


@dataclass(frozen=True)
class AgentReply:
    agent: str
    content: str
    facts_used: list[dict] = field(default_factory=list)


def _latest_quotes(session: Session, symbols: list[str]) -> list[Quote]:
    quotes: list[Quote] = []
    for sym in symbols:
        q = session.execute(
            select(Quote).where(Quote.symbol == sym).order_by(desc(Quote.ts_received)).limit(1)
        ).scalar_one_or_none()
        if q is not None:
            quotes.append(q)
    return quotes


def _fmt_quote(q: Quote) -> str:
    return f"{q.symbol} {q.price} [{q.status}/{q.provider}] ts={q.ts_received:%Y-%m-%d %H:%M UTC}"


def _no_data(symbols: list[str]) -> str:
    return (
        f"NO DATA AVAILABLE para {', '.join(symbols)}. "
        "No hay quote fresco en la base de datos: conecta un feed real o el monitor "
        "(python -m apps.monitor.main) y reintenta. No inventaré precios."
    )


class BaseResponder:
    name = "base"
    symbols: list[str] = []

    def respond(self, question: str, session: Session) -> AgentReply:
        raise NotImplementedError


class DataAwareResponder(BaseResponder):
    """Shared behavior: quote check + last own analysis."""

    role_description = ""

    def respond(self, question: str, session: Session) -> AgentReply:
        quotes = _latest_quotes(session, self.symbols)
        if not quotes:
            return AgentReply(self.name, _no_data(self.symbols))

        lines = [f"FACTS: {', '.join(_fmt_quote(q) for q in quotes)}"]
        stale = [q.symbol for q in quotes if q.status != DataStatus.LIVE]
        if stale:
            lines.append(f"DATA WARNING: {', '.join(stale)} sin feed LIVE — tratar como STALE.")

        last_analysis = session.execute(
            select(Analysis).where(Analysis.agent == self.name).order_by(desc(Analysis.ts)).limit(1)
        ).scalar_one_or_none()
        if last_analysis is not None:
            lines.append(
                f"Último análisis registrado ({last_analysis.ts:%Y-%m-%d %H:%M}): "
                f"{last_analysis.output_summary[:400]}"
            )
        else:
            lines.append("Sin análisis registrados aún en la DB.")

        stance_hint = f"\nINFERENCES: {self.role_description}" if self.role_description else ""
        return AgentReply(self.name, "\n".join(lines) + stance_hint)
