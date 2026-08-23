# CHANGELOG

Formato: Keep a Changelog. Fechas UTC.

## [0.2.0] — 2026-08-23

Entrega P1–P16 del backlog institucional (ver TASKS.md). 202 tests passing,
ruff + mypy strict clean, cobertura core/risk+execution+market_brain ≥93%.

### Added — Datos y procedencia
- `core/provenance.py`: tipos de provenance + estados de verificación +
  guards de presentación (`VERIFIED / DERIVED / NOT AVAILABLE` nunca se maquillan).
- `core/market_data/reconciliation.py`: comparador multi-feed
  (CONSISTENT/DEGRADED/DIVERGENT/STALE) + eventos FEED_DIVERGENCE/DATA_STALE.
- `core/market_data/tiers.py` (P12): jerarquía PRIMARY/SECONDARY/FALLBACK con
  grades (Yahoo = unofficial→DELAYED; solo Polymarket RTDS es institutional LIVE);
  configurable vía `config/feed_tiers.json`.
- Rollup quotes→candles M15/H1/H4 (`core/memory/candles.py`) idempotente,
  etiquetado DERIVED, hook en el monitor (~5 min) + backfill de 41 símbolos.
- `providers/positioning/cftc.py` + InstitutionalPositioningAgent (P5): COT
  VERIFIED desde CFTC Socrata; gamma/options-OI/ETF-flows/CTA = NOT AVAILABLE.

### Added — Inteligencia
- Regime detector v2 (P9): ATR%, vol realizada, ADX (Wilder), persistencia,
  Kaufman ER, range expansion, volumen relativo.
- Market Brain (P6): composite momentum/liquidity/macro/risk/data-quality con
  provenance por componente.
- CrossAssetEngine (P4): correlación baseline vs reciente, DIVERGENCE /
  REGIME CHANGE / ABNORMAL_RELATIONSHIP, régimen de riesgo SPX/VIX/BTC.
- DeskDebateEngine (P7): 7 analistas deterministas + síntesis CIO +
  persistencia en analyses/agent_opinions; endpoint POST /desk/{asset}/convene.
- AuditVerifier (P1b): frescura de fuentes, coherencia numérica, opiniones sin
  fuentes marcadas UNVERIFIED.
- OrionSignal schema (P8): formato completo de señal con validación geométrica
  y de R:R (`core/signals/format.py`).

### Added — Infraestructura y API
- RedisEventBus (P10) con fallback controlado a InMemory (`build_event_bus`);
  setting ORION_REDIS_URL; test de integración gated por REDIS_URL_TEST.
- Router analytics: `/positioning/{symbol}`, `/cross_asset/scan`,
  `/market_brain/{scope}` exponiendo engines testeados.
- `/system/status` ampliado (P15): services[] con HEALTHY/DEGRADED/STALE/FAILED
  derivado de evidencia en DB (yahoo poller, RTDS, ciclo news, rollup H1,
  debates) + tipo de event bus.

### Added — Frontend
- Dashboards GOLD, CRYPTO (+panel XRP honesto), EQUITIES, POLYMARKET RTDS,
  POSITIONING, CROSS-ASSET y BACKTEST (P11). Los datos faltantes se muestran
  como NOT AVAILABLE, nunca estimados.
- Panel Services Health en /status.

### Docs
- `docs/BROKER_MATRIX.md` (P13): OANDA v20, Alpaca, IBKR TWS/Web API, MT5 y
  VT Markets desde documentación oficial; reglas de integración paper-first.
- Este changelog; actualización de ROADMAP/TASKS/ARCHITECTURE.

### Tests
- Property-based (hypothesis) para sizing/fills/risk/reconciliación (P14).
- Locks del LiveBrokerGateway (default-lock, token incorrecto, muro Phase-5).
- Agregación de candles, clasificación de salud por servicio, tiers de feeds,
  bus Redis (fallback), debate, brain, cross-asset, positioning, señal.

## [0.1.0] — entrega inicial

Fundación: modelos SQLAlchemy completos, event bus in-proceso, API FastAPI,
monitor, frontend skeleton, PaperTradingEngine con fills imperfectos,
RiskEngine con veto, chat multiagente, CI con detección de secretos.
