"""Single AgentRegistry — the ONLY source of truth for desk agent metadata.

Backend specialists (deterministic responders/orchestrator members) and their
public identity live here. The `.opencode/agents/*.md` files remain LLM persona
prompts for the opencode CLI; this registry mirrors the same roles so both
layers stay aligned without duplicating logic (registry = metadata, .opencode =
prompt text).

Dynamic state (last_run / last_error / last_sources) is recorded by the CIO
orchestrator whenever an specialist actually executes, so the /agents page
reflects reality — never fabricated status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock


@dataclass
class AgentSpec:
    agent_id: str
    name: str
    role: str
    capabilities: list[str]
    asset_classes: list[str]
    dependencies: list[str] = field(default_factory=list)
    # dynamic state
    last_run: datetime | None = None
    last_error: str | None = None
    last_sources: list[dict] = field(default_factory=list)

    def record_run(self, sources: list[dict] | None = None) -> None:
        self.last_run = datetime.now(UTC)
        self.last_error = None
        if sources is not None:
            self.last_sources = sources[:12]

    def record_error(self, error: str) -> None:
        self.last_run = datetime.now(UTC)
        self.last_error = error[:500]

    @property
    def status(self) -> str:
        """READY / DEGRADED / OFFLINE. BUSY only meaningful mid-execution."""
        if self.last_error and self.last_run and self.last_error:
            return "DEGRADED"
        return "READY"

    @property
    def health(self) -> str:
        """Evidence-based freshness of the last actual run."""
        if self.last_run is None:
            return "NEVER_RUN"
        age_h = (datetime.now(UTC) - self.last_run).total_seconds() / 3600
        if age_h <= 24:
            return "HEALTHY"
        if age_h <= 72:
            return "STALE"
        return "IDLE"

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "capabilities": self.capabilities,
            "asset_classes": self.asset_classes,
            "dependencies": self.dependencies,
            "status": self.status,
            "health": self.health,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_error": self.last_error,
            "last_sources": self.last_sources,
        }


def _spec(agent_id: str, name: str, role: str, caps: list[str], classes: list[str],
          deps: list[str] | None = None) -> AgentSpec:
    return AgentSpec(
        agent_id=agent_id, name=name, role=role, capabilities=caps,
        asset_classes=classes, dependencies=deps or [],
    )


_DEFAULT_SPECS: list[AgentSpec] = [
    _spec("orion-cio", "ORION CIO", "Desk Head & Chief Investment Officer",
          ["intent routing", "specialist orchestration", "synthesis", "trade plan framing"],
          ["all"]),
    _spec("risk-manager", "Chief Risk Manager", "Veto power over any executable idea",
          ["portfolio limits", "R:R check", "data freshness gate",
           "verdict GREEN/WAIT/REDUCE/REJECT"],
          ["all"], deps=["market-data-engineer"]),
    _spec("macro-strategist", "Macro Strategist", "Rates/Dollar/Vol regime read",
          ["DXY", "US10Y", "VIX", "SPX relations"], ["fx", "rates", "index"]),
    _spec("news-intelligence", "News Intelligence", "Headline flow & relevance",
          ["RSS ingestion review", "HIGH relevance flags"], ["all"], deps=["research-memory"]),
    _spec("metals-analyst", "Metals Analyst", "Gold/Silver complex",
          ["XAUUSD", "GC", "MGC", "DXY drag", "CFTC gold"], ["metal"]),
    _spec("crypto-analyst", "Crypto Analyst", "BTC/ETH/XRP/SOL majors",
          ["spot quotes", "BTC correlation", "relative strength"], ["crypto"]),
    _spec("equities-analyst", "Equities Analyst", "Indices & megacaps",
          ["SPX", "NASDAQ", "NQ", "ES"], ["index", "stock"]),
    _spec("liquidity-analyst", "Liquidity Analyst", "Honest derived liquidity",
          ["swing highs/lows", "range extremes", "ATR extension", "relative volume"],
          ["all"]),
    _spec("quant-architect", "Quant Architect", "Statistical gate",
          ["regime", "momentum", "volatility", "PASS/CAUTION/REJECT"], ["all"]),
    _spec("crossasset-analyst", "Cross-Asset Analyst", "Relations & divergences",
          ["GOLD vs DXY", "NQ vs US10Y", "BTC vs NASDAQ", "XRP vs BTC"], ["all"]),
    _spec("positioning-analyst", "Institutional Positioning Analyst",
          "CFTC COT verified positioning",
          ["managed money", "commercials", "open interest", "weekly change"], ["metal", "crypto"]),
    _spec("audit-agent", "Audit / Verification", "Independent verification layer",
          ["source existence/freshness", "numeric coherence", "claim provenance"],
          ["all"]),
    _spec("execution-trader", "Execution Trader", "Paper-mode execution preview",
          ["order staging", "slippage awareness"], ["all"], deps=["risk-manager"]),
    _spec("market-data-engineer", "Market Data Engineer", "Feed health & ingestion",
          ["yahoo", "coinbase", "embedded service", "reconciliation"],
          ["all"]),
    _spec("research-memory", "Research / Memory", "Debate & analysis persistence",
          ["chat history", "analysis archive", "agent opinions"], ["all"]),
]


class AgentRegistry:
    _lock = Lock()
    _specs: dict[str, AgentSpec] | None = None

    @classmethod
    def all(cls) -> list[AgentSpec]:
        with cls._lock:
            if cls._specs is None:
                cls._specs = {s.agent_id: s for s in _DEFAULT_SPECS}
            return list(cls._specs.values())

    @classmethod
    def get(cls, agent_id: str) -> AgentSpec | None:
        for s in cls.all():
            if s.agent_id == agent_id:
                return s
        return None

    @classmethod
    def reset(cls) -> None:
        """Rebuild pristine specs (fresh dynamic state). Used at boot & in tests."""
        with cls._lock:
            cls._specs = {
                s.agent_id: AgentSpec(
                    agent_id=s.agent_id, name=s.name, role=s.role,
                    capabilities=list(s.capabilities),
                    asset_classes=list(s.asset_classes),
                    dependencies=list(s.dependencies),
                )
                for s in _DEFAULT_SPECS
            }

    @classmethod
    def record_run(cls, agent_id: str, sources: list[dict] | None = None) -> None:
        spec = cls.get(agent_id)
        if spec is not None:
            spec.record_run(sources)

    @classmethod
    def record_error(cls, agent_id: str, error: str) -> None:
        spec = cls.get(agent_id)
        if spec is not None:
            spec.record_error(error)

    @classmethod
    def to_list(cls) -> list[dict]:
        return [s.to_dict() for s in cls.all()]
