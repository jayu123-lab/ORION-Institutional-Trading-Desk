# DATA_SOURCES.md — Fuentes de datos y proveedores

Guía de integración de market data. Regla vinculante del desk: **nunca presentar
datos simulados como reales**; todo dato lleva su `DataQuality` (LIVE / DELAYED /
STALE / DISCONNECTED / SIMULATED) y el Risk Manager veta ideas basadas en datos
no frescos.

## Estado por fuente (Fase 1)

| Fuente | Tipo | Estado | Notas |
|---|---|---|---|
| `simulated` | interno | ACTIVO (SIMULATED) | Generador determinista para desarrollo/paper. Siempre etiquetado `SIMULATED`. |
| TradingView webhook | push | ACTIVO (webhook) | POST `/hooks/tradingview` con header `X-ORION-Secret`. La calidad depende del plan del usuario. |
| Polymarket Gamma/CLOB | REST read-only | ADAPTADOR LISTO | Endpoints verificados abajo. Sin credenciales necesarias para lectura. |
| Brokers (IBKR, etc.) | ejecución | NO IMPLEMENTADO (Fase 5) | Interfaces definidas en `providers/brokers/base.py`. |

## Polymarket (verificado contra docs oficiales)

- Gamma API (público): `https://gamma-api.polymarket.com`
  - `GET /markets`, `GET /markets?slug=...`
  - `GET /events`, `GET /public-search?q=...&limit_per_type=...`
- CLOB API: `https://clob.polymarket.com`
  - `GET /book?token_id=...`
  - `GET /midpoint?token_id=...`
  - `GET /last-trade-price?token_id=...`
- WebSocket: `wss://ws-subscriptions-clob.polymarket.com/ws/market`

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
