# TASKS — Backlog operativo

Convención: `[P#]` fase, `[agent]` responsable sugerido. Marcar `[x]` al cerrar.

## Infraestructura

- [x] [P1][infra] Estructura repo + git init + branch main
- [x] [P1][infra] pyproject + requirements + tooling (ruff, mypy, pytest)
- [x] [P1][infra] docker-compose (api, web, monitor, postgres, redis)
- [x] [P1][infra] CI GitHub Actions (tests/lint/typecheck/secrets)
- [x] [P2][infra] Alembic revision inicial autogenerada (98aada0dedf4; dev DB stamped)
- [ ] [P2][infra] Makefile/justfile equivalentes PowerShell

## OpenCode / agentes

- [x] [P1][opencode] opencode.json (default_agent=orion-cio, subagent_depth=2)
- [x] [P1][opencode] 13 agentes en .opencode/agents/ con permisos mínimos
- [x] [P1][opencode] 17 comandos de mesa en .opencode/command/
- [ ] [P2][opencode] Skill "orion-signal-format" para validar señales §1
- [ ] [P3][cio] Plantilla de AGENT DEBATE estructurado (JSON de opiniones)

## Core

- [x] [P1][core] Modelos SQLAlchemy completos (18 tablas del spec)
- [x] [P1][core] InMemoryEventBus + tipos de evento
- [x] [P1][core] SessionEngine (UTC interno, Europe/Madrid display)
- [x] [P1][core] DataQuality + staleness policy
- [x] [P1][core] WeightedConsensus + ConfidenceEngine
- [x] [P1][risk] RiskEngine.evaluate (APPROVED/REDUCE_SIZE/WAIT/REJECTED)
- [x] [P1][risk] sizing por % riesgo y stop distance; límites diarios/semanales
- [x] [P1][execution] OrderState machine + PaperGateway (spread/slippage/comisión/parciales)
- [x] [P1][execution] ExecutionGateway interface + LiveBrokerGateway bloqueado
- [x] [P2][events] RedisEventBus con fallback controlado a InMemory
      (build_event_bus; integración live gated por REDIS_URL_TEST)
- [x] [P3][regime] Detector TRENDING/RANGING/VOL multi-factor sobre candles reales
      (ATR% + vol realizada + ADX Wilder + persistencia + Kaufman ER)
- [x] [P2][core] Provenance + MarketDataReconciliationEngine (P2/P3 spec usuario;
      estados CONSISTENT/DEGRADED/DIVERGENT/STALE, eventos FEED_DIVERGENCE/DATA_STALE)
- [x] [P12][core] Jerarquía de tiers de feeds PRIMARY/SECONDARY/FALLBACK + grades
      (Yahoo explícitamente NO institucional-live; configurable config/feed_tiers.json)
- [x] [P5][core] InstitutionalPositioningAgent — CFTC Socrata VERIFIED DATA;
      gamma/options-OI/ETF-flows/CTA declarados NOT AVAILABLE, nunca fabricados
- [x] [P4][core] CrossAssetEngine — correlaciones baseline/reciente, DIVERGENCE/
      REGIME CHANGE/ABNORMAL, régimen de riesgo SPX/VIX/BTC
- [x] [P6][core] Market Brain composite (momentum/liquidity/macro/risco/data-quality)
- [x] [P7][core] DeskDebateEngine 7 analistas deterministas + CIO synthesis + audit
- [x] [P1b][core] AuditVerifier — verificación de fuentes/coherencia numérica en análisis
- [x] [P8][core] OrionSignal schema + validación geométrica/R:R (formato señal §1)
- [x] [core] Rollup quotes→candles M15/H1/H4 (DERIVED) idempotente + hook en monitor

## Providers

- [x] [P1][tv] TradingViewWebhookReceiver (POST JSON autenticado, guarda alerta)
- [x] [P1][pm] PolymarketAdapter (Gamma markets/events, CLOB book/price; parsing outcomePrices)
- [x] [P1][sim] SimulatedDataProvider etiquetado SIMULATED (paper/demo only)
- [x] [P2][pm] PolymarketWsMonitor RTDS crypto_prices LIVE (BTCUSD/ETHUSD/SOLUSD/XRPUSD;
      reconexión exponencial, heartbeat PING 5s, filtro client-side — ver docs/DATA_SOURCES.md)
- [x] [P2][md] YahooFinanceProvider multi-activo (índices, futuros, commodities, megacaps,
      FX, yields; API pública no oficial verificada 2026-08-23; TTL cache + pacing)
- [ ] [P5][brokers] IBKR/Alpaca/OANDA/Binance adapters (doc oficial primero)

## Apps

- [x] [P1][api] FastAPI: routers market/news/macro/agents/chat/trades/risk/status/hooks
- [x] [P1][api] Chat multiagente con @routing y respuestas desde datos reales
- [x] [P1][monitor] orion-monitor loop (heartbeat, quotes, alerts, feed health)
- [x] [P1][web] Skeleton dashboard oscuro + desk room chat
- [x] [P2][web] WebSocket client para precios live (/ws/events + fallback polling,
      indicador de transporte LIVE WS/POLLING/OFFLINE)
- [x] [P4][web] Pantallas GOLD/CRYPTO/EQUITIES/POLYMARKET/POSITIONING/CROSS-ASSET/
      BACKTEST (datos faltantes mostrados como NOT AVAILABLE, nunca estimados)
- [x] [P11][api] Router analytics: /positioning/{sym} · /cross_asset/scan ·
      /market_brain/{scope} exponiendo engines ya testeadaos

## Calidad

- [x] [P1][qa] pytest: bus, riesgo, paper, calidad datos, consenso, sesiones
- [x] [P1][qa] check_secrets.py en CI y pre-commit local
- [x] [P2][qa] Cobertura ≥80% en core/risk + core/execution + core/market_brain
      (TOTAL 93% con pytest-cov)
- [x] [P3][qa] Property-based tests (hypothesis): sizing/fills/risk/reconciliación
