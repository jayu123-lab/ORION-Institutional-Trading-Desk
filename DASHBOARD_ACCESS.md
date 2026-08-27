# 📊 ORION Dashboard - Acceso y Guía

## 🚀 Inicio Rápido

### 1. **Backend (API)**
```bash
# Terminal 1: Activar venv
python -m venv .venv
source .venv/bin/activate  # En Windows: .\.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Iniciar API (puerto 8000)
uvicorn apps.api.main:app --reload --port 8000
```

**API disponible en:** `http://localhost:8000`

### 2. **Frontend (Dashboard)**
```bash
# Terminal 2: Navegar a web
cd apps/web

# Instalar dependencias
npm install

# Iniciar frontend (puerto 3000)
npm run dev
```

**Dashboard disponible en:** `http://localhost:3000`

### 3. **Monitor (Proceso Persistente)**
```bash
# Terminal 3: Iniciar monitor
python -m apps.monitor.main
```

El monitor ejecuta tareas programadas (volume monitoring, calendar checks, etc.)

---

## 📡 API Endpoints Disponibles

### Dashboard Widgets
```bash
# Obtener todos los widgets
curl http://localhost:8000/dashboard/widgets

# Vista general de mercado
curl http://localhost:8000/dashboard/market-overview

# Inputs de especialistas
curl http://localhost:8000/dashboard/specialist-inputs
```

### Decisiones
```bash
# Decisiones pendientes
curl http://localhost:8000/dashboard/decisions/pending

# Decisiones ejecutadas
curl http://localhost:8000/dashboard/decisions/executed
```

### Monitoreo
```bash
# Calendario económico
curl http://localhost:8000/dashboard/economic-calendar

# Monitoreo de volumen
curl http://localhost:8000/dashboard/volume-monitor

# Estadísticas del agente LLM
curl http://localhost:8000/dashboard/llm-agent/stats
```

### Estado del Sistema
```bash
# Salud del sistema
curl http://localhost:8000/dashboard/system-status

# Dashboard de riesgo
curl http://localhost:8000/dashboard/risk-dashboard
```

---

## 🎯 Qué Ver en el Dashboard

### 1. **Command Center** (http://localhost:3000/command)
- ✅ Núcleo 3D en vivo con volumen por activo
- ✅ HUD de sesión / régimen / BIAS / decisión
- ✅ Panel de volumen en tiempo real
- ✅ Lectura completa del CIO

### 2. **Market Watchlist** (http://localhost:3000/market)
- ✅ Precios LIVE (Yahoo Finance, CoinGecko)
- ✅ Índices, metales, energía, acciones, cripto
- ✅ Spreads y liquidez

### 3. **Desk Rooms**
- **Gold Desk**: XAUUSD, GC, MGC, DXY, US10Y
- **Crypto Desk**: BTC, ETH, SOL, XRP (con volatilidad real)
- **Equities Desk**: SPY, QQQ, IWM con posicionamiento

### 4. **Risk Dashboard** (http://localhost:3000/risk)
- ✅ PnL diario
- ✅ Límites de pérdida
- ✅ Apalancamiento y exposición
- ✅ Alertas en tiempo real

### 5. **Decisiones Autónomas** (http://localhost:3000/decisions)
- ✅ Trades pendientes de aprobación
- ✅ Trades ejecutados con PnL
- ✅ Historial de decisiones del LLM
- ✅ Estadísticas del agente

---

## 🔌 Estructura del Backend

```
apps/api/
├── main.py              # FastAPI app principal
├── dashboard_routes.py  # 🆕 Rutas del dashboard
└── other_routes.py      # Market, risk, chat, etc.

core/
├── scheduling/          # Scheduler + Economic Calendar
├── events/              # Eventos económicos
├── volume_monitor/      # Monitoreo de volumen
├── notifications/       # Alertas Slack/Email
├── market_data/         # Bonds, Forex, Derivatives, Macro
├── visualization/       # Dashboard widgets
├── orchestration/       # Autonomous decisions
├── agents/              # 🆕 LLM Decision Agent
└── ...                  # Otros módulos
```

---

## 🤖 LLM Decision Agent

El agente LLM está integrado en el flujo autónomo:

### Flujo de Decisiones
```
1. MARKET DATA
   └─→ RealTimeFeeds (bonds, forex, VIX, commodities)

2. SPECIALISTS ANALYZE
   └─→ 9 especialistas generan inputs

3. LLM AGENT DECIDES
   └─→ claude-opus analiza y genera decision
       ├─ Evalúa macro bias
       ├─ Calcula entry/stop/target
       ├─ Verifica R:R >= 1:2
       └─ Genera JSON con decisión

4. RISK MANAGER APPROVES/REJECTS
   └─→ Chequea límites y veta si es necesario

5. EXECUTION QUEUE
   └─→ Trades aprovados listos para ejecutar
```

### Prompt del LLM

```python
# Ver en: core/agents/decision_agent.py

DecisionAgentPrompt.get_system_prompt()
# Explica el framework de decisiones al LLM
```

### Respuesta del LLM

```json
{
  "decision": "LONG|SHORT|WAIT",
  "confidence": 0.0-1.0,
  "rationale": "Clear reasoning based on data",
  "entry": 450.25,
  "stop_loss": 441.25,
  "target": 468.50,
  "risk_reward": 2.1,
  "catalyst": "Specialist consensus: STRONG_BULLISH",
  "risk_level": "LOW|MEDIUM|HIGH",
  "max_position_size": 1234
}
```

---

## 📊 Datos en Tiempo Real

### Fuentes Activas
- **Yahoo Finance**: Stocks, índices, volumen
- **CoinGecko**: Crypto prices, 24h volume
- **FRED**: US Treasury yields
- **ER-API**: Forex rates
- **Trading Calendar**: Economic events (Fed, BCE, etc.)

### Monitoreo Automático
| Tarea | Intervalo | Módulo |
|-------|-----------|--------|
| Volume monitoring | Cada 5 min | VolumeMonitor |
| Economic calendar check | Cada hora | EconomicCalendar |
| Calendar refresh | Diariamente 00:00 UTC | SchedulerEngine |
| Data quality check | Cada 30 min | SessionEngine |

---

## 🔐 Seguridad y Límites

### Risk Manager Veto
```python
# El Risk Manager SIEMPRE revisa:
✅ R:R ratio >= 1:2 (mínimo)
✅ Risk amount <= 2% daily loss limit
✅ Confidence >= 70%
✅ Data quality > threshold
```

### No automático:
```python
# El Risk Manager RECHAZA si:
❌ R:R < 1:2
❌ Risk > account size * 2%
❌ Data quality < 50%
❌ VIX > 40 (volatilidad extrema)
```

---

## 💡 Pruebas Manuales

### 1. Verificar APIs
```bash
# Health check
curl http://localhost:8000/dashboard/health

# System status
curl http://localhost:8000/dashboard/system-status
```

### 2. Ver Datos en Tiempo Real
```bash
# Market overview
curl http://localhost:8000/dashboard/market-overview

# Economic calendar
curl http://localhost:8000/dashboard/economic-calendar
```

### 3. Ver Decisiones del Agente
```bash
# Decisiones pendientes
curl http://localhost:8000/dashboard/decisions/pending

# Estadísticas del LLM
curl http://localhost:8000/dashboard/llm-agent/stats
```

---

## 🐛 Debugging

### Logs
```bash
# Ver logs del API
tail -f logs/api.log

# Ver logs del monitor
tail -f logs/monitor.log

# Ver logs de decisiones
grep "LLM Decision" logs/*.log
```

### Database
```bash
# Ver trades ejecutados
sqlite3 database/orion_dev.db "SELECT * FROM trade_decisions;"

# Ver eventos monitoreados
sqlite3 database/orion_dev.db "SELECT * FROM economic_events;"
```

---

## 📈 Próximos Pasos

1. ✅ **Agente LLM integrado** (completado)
2. ⏳ **Conectar a bróker real** (paper trading)
3. ⏳ **WebSocket para updates en vivo**
4. ⏳ **Mobile app para monitoreo**
5. ⏳ **Machine learning para mejoras**

---

## 💬 Soporte

- **Documentación**: Ver `/docs` en el repo
- **API Docs**: `http://localhost:8000/docs` (Swagger)
- **Issues**: Reportar en GitHub

---

**¡Tu mesa de trading institucional ya está lista!** 🚀
