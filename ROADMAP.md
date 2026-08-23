# ROADMAP

Estado: **PHASE 1 implementada** (salvo donde se indique). Actualizar al cerrar fases.

## PHASE 1 — Fundación ✅ (esta entrega)

- [x] Repositorio, arquitectura documentada, licencia, seguridad base
- [x] `opencode.json` + agentes reales en `.opencode/agents/` + comandos de mesa
- [x] Esquema de base de datos completo (SQLite dev / PostgreSQL prod) + Alembic
- [x] Event bus asíncrono in-proceso con topics del dominio
- [x] API FastAPI base (market, news, macro, agents, chat, trades, risk, status, hook TV)
- [x] Frontend Next.js skeleton oscuro (overview, desk room, agentes, riesgo, trades, status)
- [x] Paper trading engine con spread/slippage/comisión/fills parciales
- [x] Risk engine con veto y sizing
- [x] Chat básico multiagente (@mentions + desk room) sobre datos reales de la DB
- [x] Tests pytest (event bus, riesgo, paper fills, calidad de datos, consenso)
- [x] CI: lint + typecheck + tests + detección de secretos

## PHASE 2 — Datos en vivo

- [x] Redis como message bus opcional (`RedisEventBus` + fallback InMemory
      controlado, setting `ORION_REDIS_URL`)
- [ ] TradingView webhook en producción (hardening + replay)
- [x] Polymarket WS monitor integrado en `orion-monitor`
      (proceso `apps.monitor.polymarket_ws`, PRIMARY_FEED/LIVE)
- [ ] Adaptadores REST públicos verificados: TwelveData/Finnhub/Polygon (según claves)
- [ ] Alembic migrations versionadas; Postgres por defecto en docker-compose
- [~] Reconexión exponencial + health checks completos en monitor
      (health checks por servicio hechos en P15; reconexión exponencial pendiente)

## PHASE 3 — Inteligencia

- [~] News intelligence: ingestion RSS/calendario y clasificación CRITICAL→NOISE
      hechas; expected vs actual reaction pendiente
- [ ] Macro strategist conectado a fuentes oficiales (Fed/ECB/BOJ/BOE, Treasury)
- [ ] Quant: librería de indicadores no redundantes, walk-forward, Monte Carlo,
      sensibilidad de parámetros, detección de overfitting
- [~] Regime detection: baseline determinista multi-factor v2 (ATR%, vol
      realizada, ADX Wilder, Kaufman ER, persistencia); HMM/clustering pendiente
- [~] Alert engine: detección de anomalías cross-asset activa; reglas
      declarativas configurables y persistencia de alertas pendientes

## PHASE 4 — Mesa completa

- [x] Agent debate orquestado (DeskDebateEngine determinista + síntesis CIO,
      persistido en analyses/agent_opinions; POST /desk/{asset}/convene)
- [ ] Memoria individual por agente append-only (`memory/<domain>/`) + lessons
- [ ] ORION FLOW INSTITUTIONAL REPORT (informe diario/semanal automatizado)
- [ ] Workflows PRE-ASIA / PRE-LONDON / PRE-NY / NY REALTIME / DAILY CLOSE / WEEKLY
- [ ] Calibration metrics (confianza declarada vs resultado observado)
- [~] Dashboard completo: GOLD/CRYPTO/EQUITIES/POLYMARKET/POSITIONING/
      CROSS-ASSET hechos (P11); BACKTEST es placeholder honesto NOT AVAILABLE;
      STRATEGIES pendiente

## PHASE 5 — Ejecución (con autorización humana)

- [~] Broker adapters oficiales: investigación y matriz de decisión por broker
      completadas (`docs/BROKER_MATRIX.md`); implementación de adapters pendiente
- [~] Execution preview: endpoint/flujo IDEA→CIO→RISK→PREVIEW existe; UI de
      confirmación humana obligatoria pendiente
- [x] Kill switch / muro de seguridad: `LiveBrokerGateway` bloqueado por
      defecto, token requerido, wall de Phase-5 incluso con token correcto
      (tests en `tests/test_execution_gateway.py`)
- [ ] MAE tracking, reconciliación de fills
- [ ] LIVE MODE checklist operativo (el gate técnico ya existe)
