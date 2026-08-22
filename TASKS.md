# TASKS — Backlog operativo

Convención: `[P#]` fase, `[agent]` responsable sugerido. Marcar `[x]` al cerrar.

## Infraestructura

- [x] [P1][infra] Estructura repo + git init + branch main
- [x] [P1][infra] pyproject + requirements + tooling (ruff, mypy, pytest)
- [x] [P1][infra] docker-compose (api, web, monitor, postgres, redis)
- [x] [P1][infra] CI GitHub Actions (tests/lint/typecheck/secrets)
- [ ] [P2][infra] Alembic revision inicial autogenerada contra Postgres
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
- [ ] [P2][events] RedisEventBus
- [ ] [P3][regime] Detector TRENDING/RANGING/VOL… sobre candles reales

## Providers

- [x] [P1][tv] TradingViewWebhookReceiver (POST JSON autenticado, guarda alerta)
- [x] [P1][pm] PolymarketAdapter (Gamma markets/events, CLOB book/price; parsing outcomePrices)
- [x] [P1][sim] SimulatedDataProvider etiquetado SIMULATED (paper/demo only)
- [ ] [P2][pm] PolymarketWsMonitor (ws-subscriptions-clob, reconexión, heartbeat)
- [ ] [P2][md] RESTAdapter genérico + adaptadores concretos según claves disponibles
- [ ] [P5][brokers] IBKR/Alpaca/OANDA/Binance adapters (doc oficial primero)

## Apps

- [x] [P1][api] FastAPI: routers market/news/macro/agents/chat/trades/risk/status/hooks
- [x] [P1][api] Chat multiagente con @routing y respuestas desde datos reales
- [x] [P1][monitor] orion-monitor loop (heartbeat, quotes, alerts, feed health)
- [x] [P1][web] Skeleton dashboard oscuro + desk room chat
- [ ] [P2][web] WebSocket client para precios live
- [ ] [P4][web] Pantallas GOLD/CRYPTO/EQUITIES/POLYMARKET/BACKTEST completas

## Calidad

- [x] [P1][qa] pytest: bus, riesgo, paper, calidad datos, consenso, sesiones
- [x] [P1][qa] check_secrets.py en CI y pre-commit local
- [ ] [P2][qa] Cobertura ≥80% en core/risk y core/execution
- [ ] [P3][qa] Property-based tests (hypothesis) para sizing/fills
