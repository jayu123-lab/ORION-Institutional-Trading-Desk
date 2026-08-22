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

- [ ] Redis como message bus opcional (`RedisEventBus`)
- [ ] TradingView webhook en producción (hardening + replay)
- [ ] Polymarket WS monitor integrado en `orion-monitor`
- [ ] Adaptadores REST públicos verificados: TwelveData/Finnhub/Polygon (según claves)
- [ ] Alembic migrations versionadas; Postgres por defecto en docker-compose
- [ ] Reconexión exponencial + health checks completos en monitor

## PHASE 3 — Inteligencia

- [ ] News intelligence: ingestion RSS/calendario, clasificación CRITICAL→NOISE,
      expected vs actual reaction
- [ ] Macro strategist conectado a fuentes oficiales (Fed/ECB/BOJ/BOE, Treasury)
- [ ] Quant: librería de indicadores no redundantes, walk-forward, Monte Carlo,
      sensibilidad de parámetros, detección de overfitting
- [ ] Regime detection avanzada (HMM/clustering sobre volatilidad y tendencias)
- [ ] Alert engine con reglas declarativas (niveles, bps, spikes, consenso)

## PHASE 4 — Mesa completa

- [ ] Agent debate orquestado (CIO convoca, registra opiniones, muestra desacuerdos)
- [ ] Memoria individual por agente append-only (`memory/<domain>/`) + lessons
- [ ] ORION FLOW INSTITUTIONAL REPORT (informe diario/semanal automatizado)
- [ ] Workflows PRE-ASIA / PRE-LONDON / PRE-NY / NY REALTIME / DAILY CLOSE / WEEKLY
- [ ] Calibration metrics (confianza declarada vs resultado observado)
- [ ] Dashboard completo: GOLD/CRYPTO/EQUITIES/POLYMARKET/STRATEGIES/BACKTEST screens

## PHASE 5 — Ejecución (con autorización humana)

- [ ] Broker adapters oficiales (IBKR/Alpaca/OANDA/Binance…) según doc oficial vigente
- [ ] Execution preview UI + confirmación humana obligatoria
- [ ] MAE tracking, reconciliación de fills, kill switch global
- [ ] LIVE MODE: doble token + checklist de seguridad + auditoría reforzada
