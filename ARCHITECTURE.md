# ORION — Architecture

## 1. Principios

1. **Mesa institucional, no chatbot**: especialistas independientes que pueden discrepar,
   aportan evidencias y asignan probabilidades; el CIO coordina; Risk tiene veto.
2. **Separación estricta de responsabilidades**: análisis ≠ decisión ≠ riesgo ≠ ejecución.
3. **Veracidad de datos**: cada dato declara `provider/timestamp/quality/status`.
   Lo simulado nunca se presenta como live. Sin feed fresco → `STALE/DISCONNECTED`.
4. **Auditabilidad total**: append-only; cualquier trade es reconstruible
   (input, fuente, timestamp, salida, confianza, modelo, agente, versión).
5. **Seguridad por defecto**: LIVE desactivado, secretos fuera del repo,
   mínimos permisos por agente.
6. **Extensibilidad mediante adaptadores**: añadir un proveedor = implementar
   `MarketDataProvider`; añadir un broker = implementar `ExecutionGateway`.

## 2. Vista lógica

```
┌─────────────────────────────────────────────────────────────────────┐
│                        apps/web (Next.js)                           │
│   Dashboard · Desk Room chat · Agentes · Riesgo · Trades · Status   │
└───────────────▲─────────────────────────────────────────────────────┘
                │ REST + WebSocket/SSE
┌───────────────┴───────────────────────────┐   ┌───────────────────┐
│              apps/api (FastAPI)           │   │ apps/monitor      │
│  routers: market, news, macro, agents,    │   │ (orion-monitor)   │
│  chat, trades, risk, status, hooks        │   │ WebSockets feeds  │
└───────▲───────────────────────────────────┘   │ schedulers, alert │
        │                                       └───────▲───────────┘
        │            core/event bus (async pub/sub)     │
        ├──────────────────────────────────────────────►┤
        ▼                                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ core: market_data · risk · execution · memory · sessions · regime   │
│       orchestration (consensus, confidence, debate)                 │
├─────────────────────────────────────────────────────────────────────┤
│ providers: tradingview(webhook) · polymarket(gamma/clob/ws) ·       │
│            brokers(interfaces) · crypto(interfaces)                 │
├─────────────────────────────────────────────────────────────────────┤
│ memory: SQLAlchemy → SQLite (dev) / PostgreSQL (prod) + audit log   │
└─────────────────────────────────────────────────────────────────────┘

Capa LLM (OpenCode): agentes .opencode/agents/* orquestados desde el CLI;
la app consume sus outputs a través de las tablas analyses/agent_opinions
y de los workflows definidos en .opencode/command/*.
```

## 3. Decisiones técnicas

| Decisión | Elección | Justificación |
|---|---|---|
| Backend | FastAPI + Pydantic v2 + asyncio | Async nativo para feeds/websockets, validación estricta de esquemas de señal |
| DB dev/prod | SQLite / PostgreSQL (misma URL config) | Cero fricción local; Postgres cuando se requiere concurrencia |
| ORM/Migraciones | SQLAlchemy 2.x + Alembic | Estándar, tipado, autogenerate |
| Event bus | `InMemoryEventBus` async (fase 1); Redis adapter (fase 2) | Suficiente en un solo host; interfaz idéntica para swap |
| Frontend | Next.js App Router + TS + Tailwind | Terminal oscura profesional, realtime via SSE/WS |
| Monitor | Proceso asyncio independiente | No depende del chat; corre mientras el PC esté encendido |
| Agentes LLM | OpenCode agents (`.opencode`) | Definición declarativa, permisos por agente, subagents |
| Paper fills | Modelo determinista sembrado (spread+slippage+comisión+parciales) | Reproducible y testeable |
| Live execution | `ExecutionGateway` interface, `LiveBrokerGateway` bloqueado | Requiere flag + token de confirmación; sin browser automation |

## 4. Modelo de datos (resumen)

Tablas principales (`core/memory/models.py`, DDL de referencia en `database/schema.sql`):

- **Mercado**: `assets`, `quotes`, `candles`, `market_regimes`, `sources`
- **Noticias/macro**: `news`, `macro_events`
- **Análisis**: `analyses`, `agent_opinions` (agent, confidence, stance, rationale)
- **Trading**: `trade_ideas` → `trade_proposals` (señal completa §1) → `orders` → `executions`, `positions`
- **Riesgo**: `risk_snapshots` (equity, drawdown, exposición, límites)
- **Estrategia**: `strategies`, `backtests`
- **Sistema**: `alerts`, `lessons` (append-only), `audit_log`

Todo registro relevante incluye `timestamp, source, agent, confidence, asset`.

## 5. Flujo de una operación (estado final)

```
TradeIdea (analista)              estado: PROPOSED
  → CIO consolida + debate        TradeProposal: RISK_REVIEW
  → RiskManager.evaluate()        APPROVED | REDUCE_SIZE | WAIT | REJECTED
  → ExecutionTrader prepara       AWAITING_HUMAN_CONFIRMATION
  → Humano confirma               SUBMITTED
  → PaperGateway.fill()           PARTIAL_FILL → FILLED | STOPPED | CLOSED
                                  CANCELLED | REJECTED
```

Estados definidos en `core/execution/models.py::OrderState` (exclusivamente los del spec).

## 6. Consenso y confianza

- `WeightedConsensus`: pesos por rol configurables **por activo y régimen**
  (`config/consensus_weights.json`). No es mayoría simple: suma ponderada de
  stances ± confidences, con detección de disenso (dispersión).
- `ConfidenceEngine`: etiquetas LOW/MODERATE/HIGH/VERY_HIGH + probabilidad opcional;
  tabla de calibración posterior (predicción vs resultado real).

## 7. Calidad de datos y sesiones

- `DataQuality(provider, timestamp, latency_ms, quality, status)` adjunta a cada quote.
- Staleness configurable por clase de activo; monitor marca `DATA STALE` /
  `FEED DISCONNECTED`; prohibido usar último precio como actual tras expiración.
- `SessionEngine`: ASIA/LONDON/NEW_YORK/LONDON_FIX/COMEX/NYSE_OPEN/NYSE_CLOSE;
  UTC interno, presentación Europe/Madrid.

## 8. Seguridad (resumen)

- Secretos solo en `.env`; `.gitignore` + scanner en CI (`scripts/check_secrets.py`).
- Permisos OpenCode mínimos por agente (analistas: read/web sí, edit/bash no).
- Ejecución live: `ORION_LIVE_MODE=true` **y** `ORION_LIVE_CONFIRM_TOKEN` coincidente;
  gateway sin implementación de broker activa hasta Fase 5.
- Webhook TradingView autenticado por cabecera secreta; sin credenciales en payload.

## 9. Extender el sistema

- **Nuevo proveedor**: heredar `MarketDataProvider` (`core/market_data/base.py`),
  registrar en `registry.py`. Ver `docs/DATA_SOURCES.md`.
- **Nuevo broker**: implementar `ExecutionGateway`; nunca exponer shell al agente
  execution-trader; pasar siempre por `submit_order()` con humano en el circuito.
- **Nueva estrategia**: objeto en `strategies/` con `generate(candles, regime)` +
  registro en tabla `strategies`; backtest vía `backtests/engine.py`.

## 10. Capa de inteligencia institucional (entrega 0.2.0)

Módulos añadidos sobre la base existente (todos con tests):

- **Procedencia y calidad**: `core/provenance.py` (estados VERIFIED/DERIVED/
  NOT AVAILABLE), `core/market_data/reconciliation.py` (comparación multi-feed,
  eventos FEED_DIVERGENCE/DATA_STALE), `core/market_data/tiers.py`
  (PRIMARY/SECONDARY/FALLBACK + grades LIVE/DELAYED/UNOFFICIAL/SIMULATED;
  configurable en `config/feed_tiers.json`).
- **Candles derivadas**: `core/memory/candles.py` agrega quotes→OHLC M15/H1/H4
  (provider=`derived-quotes`, status=DERIVED, upsert idempotente); el monitor
  ejecuta el rollup cada ~5 min.
- **Régimen**: `core/regime.py` v2 multi-factor determinista (ATR%, vol
  realizada, ADX Wilder, Kaufman ER, persistencia, expansión de rango).
- **Market Brain**: `core/market_brain/` composite momentum/liquidity/macro/
  risk/data-quality con provenance por componente.
- **Cross-asset**: `core/cross_asset/engine.py` correlaciones baseline vs
  reciente (DIVERGENCE / REGIME CHANGE / ABNORMAL_RELATIONSHIP) y régimen de
  riesgo SPX/VIX/BTC.
- **Positioning**: `providers/positioning/cftc.py` (COT oficial vía Socrata)
  + `core/positioning/agent.py`; fuentes sin API pública se reportan
  NOT AVAILABLE.
- **Debate**: `core/debate/engine.py` convoca analistas deterministas,
  registra opiniones y síntesis CIO en analyses/agent_opinions.
- **Señales**: `core/signals/format.py` valida el formato completo de señal
  (entrada/invalidación/SL/TP/R:R/probabilidad/condiciones) antes de publicar.
- **Auditoría**: `core/audit/verifier.py` comprueba frescura de fuentes y
  coherencia numérica de análisis/opiniones.
- **Infra**: `RedisEventBus` opcional (`build_event_bus`, fallback InMemory),
  router analytics (`/positioning`, `/cross_asset/scan`, `/market_brain`) y
  health por servicio en `/system/status`.
- **Brokers**: matriz de decisión e investigación oficial en
  `docs/BROKER_MATRIX.md`; adapters pendientes (Phase 5).
