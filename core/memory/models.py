"""ORION persistence model — spec §16 tables.

Every meaningful record carries: timestamp, source, agent, confidence, asset.
Enums are stored as constrained strings for painless SQLite/Postgres parity.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- sources/assets
class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[str] = mapped_column(String(32))  # REST | WS | WEBHOOK | MANUAL
    status: Mapped[str] = mapped_column(String(16), default="DISCONNECTED")
    base_url: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True)  # XAUUSD, BTCUSD...
    asset_class: Mapped[str] = mapped_column(String(24))  # metal|crypto|index|fx|rate|prediction
    venue_hint: Mapped[str | None] = mapped_column(String(64))
    instrument_type: Mapped[str] = mapped_column(
        String(16), default="SPOT"
    )  # SPOT|PERP|FUTURE|OPTION
    watchlist: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- market data
class Quote(Base):
    __tablename__ = "quotes"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    provider: Mapped[str] = mapped_column(String(48))
    price: Mapped[float] = mapped_column(Float)
    bid: Mapped[float | None] = mapped_column(Float)
    ask: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    ts_source: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # exchange time
    ts_received: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    quality: Mapped[str] = mapped_column(String(8), default="UNKNOWN")  # A|B|C|UNKNOWN
    status: Mapped[str] = mapped_column(
        String(16), default="LIVE"
    )  # LIVE|DELAYED|STALE|DISCONNECTED|SIMULATED

    __table_args__ = (Index("ix_quotes_symbol_ts", "symbol", "ts_received"),)


class Candle(Base):
    __tablename__ = "candles"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))  # M1 M5 M15 H1 H4 D1
    provider: Mapped[str] = mapped_column(String(48))
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    ts_open: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="LIVE")

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "ts_open", "provider", name="uq_candle"),
    )


class MarketRegime(Base):
    __tablename__ = "market_regimes"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    regime: Mapped[str] = mapped_column(String(32))  # TRENDING|RANGING|HIGH_VOLATILITY|...
    risk_state: Mapped[str] = mapped_column(String(16))  # RISK_ON|RISK_OFF
    method: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- news / macro
class NewsItem(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(96))
    url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    relevance: Mapped[str] = mapped_column(
        String(12), default="MEDIUM"
    )  # CRITICAL|HIGH|MEDIUM|LOW|NOISE
    assets: Mapped[list | None] = mapped_column(JSON)  # [symbols]
    expected_impact: Mapped[str | None] = mapped_column(Text)
    actual_reaction: Mapped[str | None] = mapped_column(Text)
    diagnosis: Mapped[str | None] = mapped_column(Text)  # BTRSTN|PRICED_IN|SQUEEZE|LIQUIDITY_EVENT
    agent: Mapped[str | None] = mapped_column(String(48))


class MacroEvent(Base):
    __tablename__ = "macro_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_name: Mapped[str] = mapped_column(String(128))  # CPI m/m, NFP...
    region: Mapped[str] = mapped_column(String(16))  # US|EU|UK|JP|CN
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    actual: Mapped[str | None] = mapped_column(String(64))
    consensus: Mapped[str | None] = mapped_column(String(64))
    previous: Mapped[str | None] = mapped_column(String(64))
    surprise: Mapped[str | None] = mapped_column(String(32))
    market_impact_expected: Mapped[str | None] = mapped_column(Text)
    market_reaction_actual: Mapped[str | None] = mapped_column(Text)
    importance: Mapped[str] = mapped_column(String(12), default="HIGH")


# ---------------------------------------------------------------- analyses
class Analysis(Base):
    """Output of any analyst run — the audit anchor (spec §27)."""

    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(48), index=True)
    asset: Mapped[str | None] = mapped_column(String(24), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # macro|technical|news|liquidity|quant|debate
    input_data: Mapped[dict | None] = mapped_column(JSON)
    data_sources: Mapped[list | None] = mapped_column(JSON)  # [{provider,ts,status}]
    output_summary: Mapped[str] = mapped_column(Text)
    full_output: Mapped[str | None] = mapped_column(Text)
    stance: Mapped[str | None] = mapped_column(String(24))  # LONG|SHORT|WAIT|NEUTRAL...
    probability: Mapped[float | None] = mapped_column(Float)  # 0-100
    confidence: Mapped[str | None] = mapped_column(String(12))  # LOW|MODERATE|HIGH|VERY HIGH
    model: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(16), default="0.1.0")
    outcome: Mapped[str | None] = mapped_column(String(24))  # filled post-hoc only
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AgentOpinion(Base):
    """One agent's vote inside a debate/consensus round."""

    __tablename__ = "agent_opinions"
    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("analyses.id"))
    debate_id: Mapped[str | None] = mapped_column(String(64), index=True)
    agent: Mapped[str] = mapped_column(String(48))
    asset: Mapped[str | None] = mapped_column(String(24))
    stance: Mapped[str] = mapped_column(String(24))  # LONG|SHORT|WAIT|NO_ENTRY...
    strength: Mapped[float] = mapped_column(Float)  # 0-100 conviction
    rationale: Mapped[str | None] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- trading flow
class TradeIdea(Base):
    __tablename__ = "trade_ideas"
    id: Mapped[int] = mapped_column(primary_key=True)
    proposed_by: Mapped[str] = mapped_column(String(48))
    asset: Mapped[str] = mapped_column(String(24), index=True)
    direction: Mapped[str] = mapped_column(String(8))  # LONG|SHORT|FLAT
    timeframe: Mapped[str | None] = mapped_column(String(8))
    entry: Mapped[float | None] = mapped_column(Float)
    invalidation: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    tp1: Mapped[float | None] = mapped_column(Float)
    tp2: Mapped[float | None] = mapped_column(Float)
    tp3: Mapped[float | None] = mapped_column(Float)
    probability: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(12))
    horizon: Mapped[str | None] = mapped_column(String(16))
    technical_thesis: Mapped[str | None] = mapped_column(Text)
    fundamental_thesis: Mapped[str | None] = mapped_column(Text)
    catalysts: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    liquidity_notes: Mapped[str | None] = mapped_column(Text)
    activation_conditions: Mapped[str | None] = mapped_column(Text)
    cancel_conditions: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str | None] = mapped_column(String(128))
    price_used: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(
        String(24), default="PROPOSED"
    )  # PROPOSED|RISK_REVIEW|APPROVED|REJECTED...
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RiskDecision(Base):
    """Risk manager verdict attached to an idea/proposal."""

    __tablename__ = "risk_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    trade_idea_id: Mapped[int] = mapped_column(ForeignKey("trade_ideas.id"), index=True)
    decision: Mapped[str] = mapped_column(String(16))  # APPROVED|REDUCE_SIZE|WAIT|REJECTED
    reasons: Mapped[list | None] = mapped_column(JSON)
    conditions: Mapped[list | None] = mapped_column(JSON)
    suggested_size: Mapped[float | None] = mapped_column(Float)
    snapshot_id: Mapped[int | None] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    trade_idea_id: Mapped[int | None] = mapped_column(ForeignKey("trade_ideas.id"))
    asset: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(4))  # BUY|SELL
    order_type: Mapped[str] = mapped_column(String(12))  # MARKET|LIMIT|STOP|STOP_LIMIT
    qty: Mapped[float] = mapped_column(Float)
    limit_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    sl_price: Mapped[float | None] = mapped_column(Float)
    tp1: Mapped[float | None] = mapped_column(Float)
    tp2: Mapped[float | None] = mapped_column(Float)
    tp3: Mapped[float | None] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(8), default="PAPER")  # PAPER|LIVE(locked)
    state: Mapped[str] = mapped_column(String(28), default="PROPOSED", index=True)
    # PROPOSED RISK_REVIEW APPROVED AWAITING_HUMAN_CONFIRMATION SUBMITTED
    # PARTIAL_FILL FILLED STOPPED CLOSED CANCELLED REJECTED
    human_confirmed_by: Mapped[str | None] = mapped_column(String(64))
    human_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Execution(Base):
    __tablename__ = "executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    fill_qty: Mapped[float] = mapped_column(Float)
    fill_price: Mapped[float] = mapped_column(Float)
    commission: Mapped[float] = mapped_column(Float, default=0.0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0.0)
    venue: Mapped[str] = mapped_column(String(32), default="PAPER")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(4))
    qty: Mapped[float] = mapped_column(Float)
    avg_price: Mapped[float] = mapped_column(Float)
    sl_price: Mapped[float | None] = mapped_column(Float)
    tp_price: Mapped[float | None] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_price: Mapped[float | None] = mapped_column(Float)
    realized_pnl: Mapped[float | None] = mapped_column(Float)
    realized_r: Mapped[float | None] = mapped_column(Float)
    mode: Mapped[str] = mapped_column(String(8), default="PAPER")
    status: Mapped[str] = mapped_column(String(8), default="OPEN")  # OPEN|CLOSED


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    equity: Mapped[float] = mapped_column(Float)
    balance: Mapped[float] = mapped_column(Float)
    open_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, default=0.0)
    daily_risk_used: Mapped[float] = mapped_column(Float, default=0.0)
    weekly_risk_used: Mapped[float] = mapped_column(Float, default=0.0)
    exposure_total: Mapped[float] = mapped_column(Float, default=0.0)
    exposures_by_asset: Mapped[dict | None] = mapped_column(JSON)
    win_rate: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    expectancy_r: Mapped[float | None] = mapped_column(Float)
    sharpe: Mapped[float | None] = mapped_column(Float)
    sortino: Mapped[float | None] = mapped_column(Float)
    verdict: Mapped[str | None] = mapped_column(String(16))  # GREEN_LIGHT|CAUTION|RED_LIGHT
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(96), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSON)
    instruments: Mapped[list | None] = mapped_column(JSON)
    regime_fit: Mapped[list | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BacktestRun(Base):
    __tablename__ = "backtests"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    n_trades: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    expectancy_r: Mapped[float | None] = mapped_column(Float)
    max_dd_pct: Mapped[float | None] = mapped_column(Float)
    sharpe: Mapped[float | None] = mapped_column(Float)
    results: Mapped[dict | None] = mapped_column(JSON)  # IS/WFS/OOS/MC breakdown
    overfit_verdict: Mapped[str | None] = mapped_column(String(24))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    rule_name: Mapped[str] = mapped_column(String(96))
    rule_kind: Mapped[str] = mapped_column(String(32))  # LEVEL_CROSS|BPS_MOVE|SPIKE|NEWS|CONSENSUS
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(12), default="INFO")  # INFO|WARN|CRITICAL
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class OpportunityCandidate(Base):
    """Every scanner candidate, including rejected or incomplete setups."""

    __tablename__ = "opportunity_candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    setup_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    setup: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(24), default="WATCHING")
    direction: Mapped[str] = mapped_column(String(8), default="NEUTRAL")
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    bias_score: Mapped[float | None] = mapped_column(Float)
    trade_quality: Mapped[float | None] = mapped_column(Float)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    subscores: Mapped[dict] = mapped_column(JSON, default=dict)
    statistical_edge: Mapped[dict | None] = mapped_column(JSON)
    risk_verdict: Mapped[str | None] = mapped_column(String(24))
    audit_verdict: Mapped[str | None] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(Text, default="")
    outcome: Mapped[dict | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class OpportunityTransition(Base):
    """Append-only candidate state history, separate from the active radar row."""

    __tablename__ = "opportunity_transitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    setup_id: Mapped[str] = mapped_column(String(128), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    setup: Mapped[str] = mapped_column(String(64))
    previous_state: Mapped[str | None] = mapped_column(String(24))
    new_state: Mapped[str] = mapped_column(String(24))
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SetupStatistics(Base):
    """Historical setup statistics, kept separate from live opportunity scores."""

    __tablename__ = "setup_statistics"
    id: Mapped[int] = mapped_column(primary_key=True)
    setup: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))
    context_key: Mapped[str | None] = mapped_column(String(128))
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float)
    average_r: Mapped[float | None] = mapped_column(Float)
    median_r: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    expectancy_r: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    mfe: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    median_time_to_t1: Mapped[float | None] = mapped_column(Float)
    failure_modes: Mapped[dict | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class FeatureDatasetRow(Base):
    """Point-in-time feature row for future temporal ML, never trained live."""

    __tablename__ = "feature_dataset"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    asset: Mapped[str] = mapped_column(String(24), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))
    features: Mapped[dict] = mapped_column(JSON)
    setup: Mapped[str | None] = mapped_column(String(64))
    entry_zone: Mapped[dict | None] = mapped_column(JSON)
    trigger: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str | None] = mapped_column(String(24))
    mfe: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    future_return_1m: Mapped[float | None] = mapped_column(Float)
    future_return_5m: Mapped[float | None] = mapped_column(Float)
    future_return_15m: Mapped[float | None] = mapped_column(Float)
    future_return_30m: Mapped[float | None] = mapped_column(Float)
    future_return_1h: Mapped[float | None] = mapped_column(Float)


class ModelRegistry(Base):
    """Registry for shadow/candidate models; no model controls live execution."""

    __tablename__ = "model_registry"
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(96), unique=True)
    version: Mapped[str] = mapped_column(String(32))
    model_type: Mapped[str] = mapped_column(String(32))
    features: Mapped[list] = mapped_column(JSON)
    training_range: Mapped[dict | None] = mapped_column(JSON)
    validation_range: Mapped[dict | None] = mapped_column(JSON)
    out_of_sample_metrics: Mapped[dict | None] = mapped_column(JSON)
    calibration: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="CANDIDATE")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lesson(Base):
    """Append-only institutional memory. Never rewrite history."""

    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    agent: Mapped[str] = mapped_column(String(48))
    domain: Mapped[str] = mapped_column(String(24))  # metals|crypto|macro|risk|general
    lesson: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON)  # regime/session/vol snapshot
    related_idea_id: Mapped[int | None] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))  # agent|system|human:<id>
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(48))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict | None] = mapped_column(JSON)
    model_version: Mapped[str] = mapped_column(String(16), default="0.1.0")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ChatMessage(Base):
    """Desk Room + direct agent chats."""

    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    room: Mapped[str] = mapped_column(String(48), default="desk")  # desk | agent:<name>
    author: Mapped[str] = mapped_column(String(48))  # user | <agent>
    content: Mapped[str] = mapped_column(Text)
    mentions: Mapped[list | None] = mapped_column(JSON)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class TradingViewAlert(Base):
    __tablename__ = "tradingview_alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    price: Mapped[float | None] = mapped_column(Float)
    timeframe: Mapped[str | None] = mapped_column(String(8))
    indicator: Mapped[str | None] = mapped_column(String(96))
    signal: Mapped[str | None] = mapped_column(String(32))
    volume: Mapped[float | None] = mapped_column(Float)
    raw: Mapped[dict | None] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DoctrineJournal(Base):
    """P16 — operational memory loop (statistics, NOT model training).

    Stores every CIO doctrine decision with its context so outcomes
    (MFE/MAE, correct bias?, correct entry?, lesson) can be evaluated
    later against real candles. Weights are never auto-modified.
    """

    __tablename__ = "doctrine_journal"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    session_name: Mapped[str | None] = mapped_column(String(24))
    bias: Mapped[str | None] = mapped_column(String(24))          # LONG/SHORT/NEUTRAL/WAIT
    bias_score: Mapped[int | None] = mapped_column(Integer)
    trade_quality: Mapped[int | None] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(24))             # TRADE/WAIT/REJECT/NO_TRADE
    entry_conditions: Mapped[dict | None] = mapped_column(JSON)
    liquidity_snapshot: Mapped[dict | None] = mapped_column(JSON)
    risk_verdict: Mapped[str | None] = mapped_column(String(24))
    reference_price: Mapped[float | None] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    # --- outcome block, filled by evaluate_journal_outcome()
    outcome_status: Mapped[str | None] = mapped_column(String(24))  # PENDING|EVALUATED
    mfe: Mapped[float | None] = mapped_column(Float)
    mae: Mapped[float | None] = mapped_column(Float)
    correct_bias: Mapped[bool | None] = mapped_column(Boolean)
    correct_entry: Mapped[bool | None] = mapped_column(Boolean)
    lesson_learned: Mapped[str | None] = mapped_column(Text)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WatchRequest(Base):
    """P34 — WATCH MODE. Surveillance only; NEVER executes orders."""

    __tablename__ = "watch_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    note: Mapped[str | None] = mapped_column(Text)                # user's own words
    zone_low: Mapped[float | None] = mapped_column(Float)         # reaction zone band
    zone_high: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(16), default="WATCHING")
    # WATCHING -> ARMED -> CONFIRMED | INVALIDATED; CANCELLED anytime
    state_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str | None] = mapped_column(String(48))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
