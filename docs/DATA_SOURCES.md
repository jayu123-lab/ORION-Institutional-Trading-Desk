# DATA_SOURCES.md — Fuentes de datos y proveedores

Guía de integración de market data. Regla vinculante del desk: **nunca presentar
datos simulados como reales**; todo dato lleva su `DataQuality` (LIVE / DELAYED /
STALE / DISCONNECTED / SIMULATED) y el Risk Manager veta ideas basadas en datos
no frescos.

## Estado por fuente (Fase 1)

| Fuente | Tipo | Estado | Notas |
|---|---|---|---|
| `yahoo` | REST (API pública no oficial) | **ACTIVO multi-activo** | Índices, futuros (índice/energía/agri/metales), megacaps, FX, yields. Sin API key. Ver sección Yahoo. |
| Polymarket RTDS WS | WebSocket read-only | **ACTIVO (LIVE)** | Precios crypto en tiempo real: BTCUSD/ETHUSD/SOLUSD/XRPUSD. Ver sección Polymarket. |
| `simulated` | interno | opt-in (`ORION_SIMULATED_ENABLED`) | Generador determinista para desarrollo/paper. Siempre etiquetado `SIMULATED`. |
| TradingView webhook | push | ACTIVO (webhook) | POST `/hooks/tradingview` con header `X-ORION-Secret`. La calidad depende del plan del usuario. |
| Polymarket Gamma/CLOB | REST read-only | ACTIVO | Endpoints verificados abajo. Sin credenciales necesarias para lectura. |
| Brokers (IBKR, etc.) | ejecución | NO IMPLEMENTADO (Fase 5) | Interfaces definidas en `providers/brokers/base.py`. |

## Yahoo Finance (verificado empíricamente 2026-08-23)

Endpoint: `GET https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d`
(sin API key; header User-Agent requerido). **No oficial**: sin SLA ni garantía
de continuidad — los fallos degradan a DISCONNECTED, nunca se fabrican datos.

Cobertura verificada: GC=F 4680.6 (COMEX), ^GSPC 7674.37, ^NDX, ^IXIC, ^DJI,
^GDAXI 26136.56, ^IBEX, ^FTSE, ^VIX, ES=F, NQ=F, SI=F, HG=F, CL=F 87.06 (NYM),
BZ=F, NG=F, ZW=F 699.25 USX-cents (CBOT), ZC=F, KC=F, AAPL 309.35 (NasdaqGS),
MSFT, NVDA, EURUSD=X 1.1678 (CCY), GBPUSD=X, JPY=X, DX-Y.NYB, ^TNX 4.738
(yield 10Y), ^IRX.

Notas:
- XAUUSD/XAGUSD spot no existen en Yahoo → proxy con futuro COMEX front-month
  (GC=F / SI=F); práctica estándar de mesa, documentada aquí.
- Los precios de grano llegan en centavos (moneda "USX") — mantener crudo.
- TTL cache 60 s por símbolo + pacing 0.35 s entre requests para respetar límites.
- Fuera de sesión, el precio es el cierre de la última sesión (ts_source real).

## Polymarket (verificado contra docs oficiales)

- Gamma API (público): `https://gamma-api.polymarket.com`
  - `GET /markets`, `GET /markets?slug=...`
  - `GET /events`, `GET /public-search?q=...&limit_per_type=...`
- CLOB API: `https://clob.polymarket.com`
  - `GET /book?token_id=...`
  - `GET /midpoint?token_id=...`
  - `GET /last-trade-price?token_id=...`
- WebSocket market channel: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
  - Suscripción: `{"assets_ids": ["<token_id>"], "type": "market"}`
  - Heartbeat: enviar texto `PING` cada 10 s (respuesta `PONG`)
- RTDS (`wss://ws-live-data.polymarket.com`) — **en producción** vía
  `python -m apps.monitor.polymarket_ws`:
  - Tema `crypto_prices` (feed Binance): btc/eth/sol/xrp → BTCUSD, ETHUSD,
    SOLUSD, XRPUSD con calidad LIVE.
  - Heartbeat: `PING` cada 5 s. El primer frame tras conectar llega vacío.
  - Gotcha verificado en vivo: el filtro server-side documentado
    (`"filters": "btcusdt,ethusdt"`) no devuelve eventos; se suscribe sin
    filtro y el parser descarta símbolos fuera del mapa client-side.

Gotcha conocido: los campos tipo `outcomePrices` llegan como **string JSON**
(`"[\"0.52\",\"0.48\"]"`), no como array. El adapter lo normaliza con
`_parse_jsonish()` (`providers/polymarket/adapter.py`).

## TradingView webhook

Formato esperado (JSON libre; el parser acepta campos comunes):

```json
{
  "symbol": "XAUUSD",
  "price": 2345.5,
  "action": "alert",
  "timeframe": "15m"
}
```

Header obligatorio: `X-ORION-Secret: <TRADINGVIEW_WEBHOOK_SECRET>`.
Sin secret configurado → 503; header incorrecto → 401.

## Añadir un provider nuevo

1. Crear módulo en `providers/<nombre>/adapter.py`.
2. Implementar la interfaz `MarketDataProvider` (`core/market_data/base.py`),
   devolviendo `Quote`/`Candle` con su `quality` correcto.
3. Registrarlo en `core/market_data/registry.py` (o dinámicamente desde settings).
4. Añadir tests mínimos: parseo de respuesta real guardada como fixture,
   comportamiento con timeout/respuesta inválida (debe degradar a STALE, nunca inventar).
5. Documentar aquí: endpoints, autenticación, límites conocidos.

## Credenciales

- Nunca en el repo ni en código. Solo `.env` local (ver `.env.example`).
- Cada clave vive en `core/config.py` con prefijo `ORION_` o nombre explícito.
- `scripts/check_secrets.py` escanea el repo en CI; mantener patrones al día.
