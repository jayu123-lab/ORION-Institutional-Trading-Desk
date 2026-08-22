-- ORION reference DDL (PostgreSQL). The runtime schema is managed by
-- SQLAlchemy models (core/memory/models.py) + Alembic migrations.
-- This file documents the canonical table set for DBAs / reviews.

CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    name VARCHAR(64) UNIQUE NOT NULL,
    kind VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DISCONNECTED',
    base_url VARCHAR(255),
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE assets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(24) UNIQUE NOT NULL,
    asset_class VARCHAR(24) NOT NULL,
    venue_hint VARCHAR(64),
    instrument_type VARCHAR(16) NOT NULL DEFAULT 'SPOT',
    watchlist BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE quotes (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(24) NOT NULL,
    provider VARCHAR(48) NOT NULL,
    price DOUBLE PRECISION NOT NULL,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    ts_source TIMESTAMPTZ NOT NULL,
    ts_received TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_ms INTEGER,
    quality VARCHAR(8) NOT NULL DEFAULT 'UNKNOWN',   -- A|B|C|UNKNOWN
    status VARCHAR(16) NOT NULL DEFAULT 'LIVE'        -- LIVE|DELAYED|STALE|DISCONNECTED|SIMULATED
);
CREATE INDEX ix_quotes_symbol_ts ON quotes (symbol, ts_received);

CREATE TABLE candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(24) NOT NULL,
    timeframe VARCHAR(8) NOT NULL,
    provider VARCHAR(48) NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume DOUBLE PRECISION,
    ts_open TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'LIVE',
    UNIQUE (symbol, timeframe, ts_open, provider)
);

CREATE TABLE market_regimes (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(24) NOT NULL,
    regime VARCHAR(32) NOT NULL,          -- TRENDING|RANGING|...
    risk_state VARCHAR(16) NOT NULL,      -- RISK_ON|RISK_OFF
    method VARCHAR(64) NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE news (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    source VARCHAR(96) NOT NULL,
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    relevance VARCHAR(12) NOT NULL DEFAULT 'MEDIUM', -- CRITICAL|HIGH|MEDIUM|LOW|NOISE
    assets JSONB,
    expected_impact TEXT,
    actual_reaction TEXT,
    diagnosis TEXT,                                   -- BTRSTN|PRICED_IN|SQUEEZE|LIQUIDITY_EVENT
    agent VARCHAR(48)
);

CREATE TABLE macro_events (
    id BIGSERIAL PRIMARY KEY,
    event_name VARCHAR(128) NOT NULL,
    region VARCHAR(16) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    actual VARCHAR(64),
    consensus VARCHAR(64),
    previous VARCHAR(64),
    surprise VARCHAR(32),
    market_impact_expected TEXT,
    market_reaction_actual TEXT,
    importance VARCHAR(12) NOT NULL DEFAULT 'HIGH'
);
CREATE INDEX ix_macro_sched ON macro_events (scheduled_at);

CREATE TABLE analyses (
    id BIGSERIAL PRIMARY KEY,
    agent VARCHAR(48) NOT NULL,
    asset VARCHAR(24),
    kind VARCHAR(32) NOT NULL,
    input_data JSONB,
    data_sources JSONB,
    output_summary TEXT NOT NULL,
    full_output TEXT,
    stance VARCHAR(24),
    probability DOUBLE PRECISION,
    confidence VARCHAR(12),
    model VARCHAR(64),
    version VARCHAR(16) NOT NULL DEFAULT '0.1.0',
    outcome VARCHAR(24),                              -- filled post-hoc ONLY
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_analyses_agent_ts ON analyses (agent, ts);

CREATE TABLE agent_opinions (
    id BIGSERIAL PRIMARY KEY,
    analysis_id BIGINT REFERENCES analyses(id),
    debate_id VARCHAR(64),
    agent VARCHAR(48) NOT NULL,
    asset VARCHAR(24),
    stance VARCHAR(24) NOT NULL,
    strength DOUBLE PRECISION NOT NULL,               -- 0..100
    rationale TEXT,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trade_ideas (
    id BIGSERIAL PRIMARY KEY,
    proposed_by VARCHAR(48) NOT NULL,
    asset VARCHAR(24) NOT NULL,
    direction VARCHAR(8) NOT NULL,
    timeframe VARCHAR(8),
    entry DOUBLE PRECISION,
    invalidation DOUBLE PRECISION,
    stop_loss DOUBLE PRECISION,
    tp1 DOUBLE PRECISION, tp2 DOUBLE PRECISION, tp3 DOUBLE PRECISION,
    probability DOUBLE PRECISION,
    confidence VARCHAR(12),
    horizon VARCHAR(16),
    technical_thesis TEXT, fundamental_thesis TEXT, catalysts TEXT, risks TEXT,
    liquidity_notes TEXT, activation_conditions TEXT, cancel_conditions TEXT,
    data_source VARCHAR(128), price_used DOUBLE PRECISION,
    state VARCHAR(24) NOT NULL DEFAULT 'PROPOSED',
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE risk_decisions (
    id BIGSERIAL PRIMARY KEY,
    trade_idea_id BIGINT NOT NULL REFERENCES trade_ideas(id),
    decision VARCHAR(16) NOT NULL,                    -- APPROVED|REDUCE_SIZE|WAIT|REJECTED
    reasons JSONB,
    conditions JSONB,
    suggested_size DOUBLE PRECISION,
    snapshot_id BIGINT,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    id BIGSERIAL PRIMARY KEY,
    client_order_id VARCHAR(64) UNIQUE NOT NULL,
    trade_idea_id BIGINT REFERENCES trade_ideas(id),
    asset VARCHAR(24) NOT NULL,
    side VARCHAR(4) NOT NULL,
    order_type VARCHAR(12) NOT NULL,                  -- MARKET|LIMIT|STOP|STOP_LIMIT
    qty DOUBLE PRECISION NOT NULL,
    limit_price DOUBLE PRECISION, stop_price DOUBLE PRECISION,
    sl_price DOUBLE PRECISION, tp1 DOUBLE PRECISION, tp2 DOUBLE PRECISION, tp3 DOUBLE PRECISION,
    mode VARCHAR(8) NOT NULL DEFAULT 'PAPER',         -- PAPER|LIVE(locked)
    state VARCHAR(28) NOT NULL DEFAULT 'PROPOSED',    -- spec §11 lifecycle
    human_confirmed_by VARCHAR(64), human_confirmed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE executions (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    fill_qty DOUBLE PRECISION NOT NULL,
    fill_price DOUBLE PRECISION NOT NULL,
    commission DOUBLE PRECISION NOT NULL DEFAULT 0,
    slippage_bps DOUBLE PRECISION NOT NULL DEFAULT 0,
    venue VARCHAR(32) NOT NULL DEFAULT 'PAPER',
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE positions (
    id BIGSERIAL PRIMARY KEY,
    asset VARCHAR(24) NOT NULL,
    side VARCHAR(4) NOT NULL,
    qty DOUBLE PRECISION NOT NULL,
    avg_price DOUBLE PRECISION NOT NULL,
    sl_price DOUBLE PRECISION, tp_price DOUBLE PRECISION,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,
    close_price DOUBLE PRECISION,
    realized_pnl DOUBLE PRECISION,
    realized_r DOUBLE PRECISION,
    mode VARCHAR(8) NOT NULL DEFAULT 'PAPER',
    status VARCHAR(8) NOT NULL DEFAULT 'OPEN'
);

CREATE TABLE risk_snapshots (
    id BIGSERIAL PRIMARY KEY,
    equity DOUBLE PRECISION NOT NULL,
    balance DOUBLE PRECISION NOT NULL,
    open_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
    drawdown_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
    daily_risk_used DOUBLE PRECISION NOT NULL DEFAULT 0,
    weekly_risk_used DOUBLE PRECISION NOT NULL DEFAULT 0,
    exposure_total DOUBLE PRECISION NOT NULL DEFAULT 0,
    exposures_by_asset JSONB,
    win_rate DOUBLE PRECISION, profit_factor DOUBLE PRECISION, expectancy_r DOUBLE PRECISION,
    sharpe DOUBLE PRECISION, sortino DOUBLE PRECISION,
    verdict VARCHAR(16),
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(96) UNIQUE NOT NULL,
    description TEXT,
    params JSONB,
    instruments JSONB,
    regime_fit JSONB,
    active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE backtests (
    id BIGSERIAL PRIMARY KEY,
    strategy_id INT NOT NULL REFERENCES strategies(id),
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    n_trades INT NOT NULL DEFAULT 0,
    win_rate DOUBLE PRECISION, profit_factor DOUBLE PRECISION, expectancy_r DOUBLE PRECISION,
    max_dd_pct DOUBLE PRECISION, sharpe DOUBLE PRECISION,
    results JSONB,
    overfit_verdict VARCHAR(24),
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE alerts (
    id BIGSERIAL PRIMARY KEY,
    rule_name VARCHAR(96) NOT NULL,
    rule_kind VARCHAR(32) NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    message TEXT NOT NULL,
    severity VARCHAR(12) NOT NULL DEFAULT 'INFO',
    acknowledged_at TIMESTAMPTZ,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE lessons (
    id BIGSERIAL PRIMARY KEY,
    agent VARCHAR(48) NOT NULL,
    domain VARCHAR(24) NOT NULL,
    lesson TEXT NOT NULL,
    context JSONB,
    related_idea_id BIGINT,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()             -- append-only; never rewrite
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor VARCHAR(64) NOT NULL,
    action VARCHAR(64) NOT NULL,
    entity VARCHAR(48) NOT NULL,
    entity_id VARCHAR(64),
    detail JSONB,
    model_version VARCHAR(16) NOT NULL DEFAULT '0.1.0',
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_ts ON audit_log (ts);

CREATE TABLE chat_messages (
    id BIGSERIAL PRIMARY KEY,
    room VARCHAR(48) NOT NULL DEFAULT 'desk',
    author VARCHAR(48) NOT NULL,
    content TEXT NOT NULL,
    mentions JSONB,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tradingview_alerts (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(24) NOT NULL,
    price DOUBLE PRECISION,
    timeframe VARCHAR(8),
    indicator VARCHAR(96),
    signal VARCHAR(32),
    volume DOUBLE PRECISION,
    raw JSONB,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
