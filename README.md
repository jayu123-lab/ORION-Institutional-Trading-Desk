# ORION INSTITUTIONAL TRADING DESK

Plataforma local, modular y multiagente que simula una **mesa institucional de trading**:
especialistas que analizan en paralelo, discrepan con evidencias, asignan probabilidades,
y un Chief Risk Manager con poder de veto — todo auditable, en modo paper por defecto.

> ⚠️ **No es asesoramiento financiero.** Las clasificaciones internas (STRONG BUY BIAS,
> etc.) son salidas de modelo para uso investigador. La ejecución real está desactivada
> por defecto y requiere autorización humana explícita.

## Flujo institucional

```
MARKET DATA → SPECIALIST AGENTS → STRATEGY/QUANT → CIO/DESK HEAD
→ CHIEF RISK MANAGER (veto) → TRADE PROPOSAL → EXECUTION GATEWAY
→ PAPER / HUMAN-APPROVED LIVE
```

Ningún analista ejecuta operaciones. Toda señal declara: activo, timestamp, fuente,
precio, timeframe, dirección, entrada, invalidación, SL, objetivos, R:R, probabilidad,
confianza, horizonte, razonamiento técnico/fundamental, catalizadores, riesgos,
liquidez, condiciones de activación y de cancelación.

## Componentes

| Módulo | Descripción |
|---|---|
| `apps/api` | FastAPI: market data, chat multiagente, propuestas, riesgo, estado |
| `apps/web` | Dashboard Next.js oscuro estilo terminal + Desk Room |
| `apps/monitor` | `orion-monitor`: proceso persistente (feeds, schedulers, alertas) |
| `core/` | Event bus, market data adapters, risk engine, execution gateway, memoria |
| `providers/` | TradingView webhook, Polymarket (Gamma/CLOB), interfaces brokers |
| `.opencode/` | 13 agentes LLM reales (CIO, Risk, Macro, News, Equities, Crypto, Metals, Liquidity, Quant, Execution, Polymarket, Research, Market Data Engineer) + comandos de mesa |

## Inicio rápido (sin Docker — Windows)

Requisitos: Python 3.12+ (probado 3.13), Node 20+.

```powershell
# Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # editar valores si procede
python -m core.memory.init_db   # crea SQLite dev

# API  → http://127.0.0.1:8000/docs
uvicorn apps.api.main:app --reload --port 8000

# Monitor persistente (otra terminal)
python -m apps.monitor.main

# Frontend → http://localhost:3000 (otra terminal)
cd apps/web; npm install; npm run dev
```

## Inicio rápido (Docker)

```bash
docker compose up --build
```

## Agentes OpenCode

Abrir `opencode` en la raíz del repo. El agente primario es **ORION-CIO**, que invoca
especialistas como subagents (`subagent_depth: 2`). Comandos disponibles:

```
/desk /market /gold /crypto /xrp /equities /macro /news /liquidity
/risk /strategy /backtest /trade /status /connections /daily /weekly
```

Ejemplos de uso en el Desk Room web o en OpenCode:

- `@metals ¿qué estás viendo ahora mismo en oro?`
- `@crypto analiza XRP`
- `@risk ¿qué riesgo tenemos abierto?`
- `Convoca la mesa para analizar XAUUSD`

## Seguridad

- Secretos **solo** en `.env` (nunca en el repo). Ver `.env.example`.
- CI bloquea commits con patrones de claves (`scripts/check_secrets.py`).
- LIVE MODE: doble bloqueo (`ORION_LIVE_MODE=true` + token de confirmación).
  Sin implementación de broker activa hasta Fase 5. Sin automatización de navegador.
- Ver [SECURITY.md](SECURITY.md).

## Documentación

- [ARCHITECTURE.md](ARCHITECTURE.md) — decisiones y diseño
- [ROADMAP.md](ROADMAP.md) — fases y estado
- [TASKS.md](TASKS.md) — backlog operativo
- [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) — proveedores y cómo añadir nuevos
- [CONTRIBUTING.md](CONTRIBUTING.md)

## Licencia

MIT — ver [LICENSE](LICENSE).
