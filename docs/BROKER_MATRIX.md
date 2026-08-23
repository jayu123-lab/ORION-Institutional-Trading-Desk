# Broker / Execution Matrix (PRIORITY 13)

> **Estado**: investigación documental ONLY. **No se ha establecido ninguna conexión
> real** con ningún broker. Todas las afirmaciones provienen de documentación oficial
> o se marcan como fuente secundaria.
>
> Última revisión: 2026-08-23 · Fuentes verificadas manualmente (ver enlaces por fila).

## Resumen

| Plataforma | Tipo | Protocolo | Paper/Demo | Activos relevantes para ORION | Veredicto de integración |
|---|---|---|---|---|---|
| **OANDA v20** | Broker FX/CFD | REST + streaming HTTP | `practice` env nativo | FX, XAU/XAG, índices CFD | **Mejor candidato FX/metales** |
| **Alpaca** | Broker API-first | REST + WebSocket | Sandbox gratuito ($100k default) | US equities, options, crypto (**NO FX**) | **Mejor candidato equities** |
| **IBKR TWS API** | Broker multi-activo | TCP socket (TWS/Gateway local) | Paper account vía Gateway | Todo (FX, futuros, equities) | Potente, mayor complejidad operativa |
| **IBKR Web API** | Broker multi-activo | REST + WebSocket | Sí, requiere gateway local u OAuth | Todo | En transición a "IBKR Web API" unificada (OAuth 2.0) |
| **MetaTrader 5** | Terminal multi-broker | Python package → terminal local | Depende del broker (login demo) | FX, metales, CFDs según broker | Viable en Windows con terminal corriendo |
| **VT Markets** | Broker MT4/MT5 | Solo vía terminal MT4/MT5 (sin API REST propia pública) | Demo MT4 90d / MT5 30d | FX, metales, CFDs | Accesible solo a través de la capa MT5 |

---

## Detalle por plataforma

### OANDA — REST-v20
- **Fuente oficial**: https://developer.oanda.com/rest-live-v20/introduction/
- Endpoints: Account / Order / Trade / Position / Transaction; datos históricos desde 2005;
  bars desde 5 segundos hasta mensuales.
- Streaming dedicado separado del order placement (`/v3/accounts/{id}/pricing/stream`,
  hasta ~4 precios/segundo/instrumento, chunked transfer).
- Entornos explícitos `practice` y `live` — mapea 1:1 con el modo PAPER/LIVE de ORION.
- Autenticación: Bearer token por cuenta.
- **Para ORION**: adaptador `providers/execution/oanda.py` (futuro) cubriría XAUUSD,
  XAGUSD y pares FX con etiqueta de provenance PRIMARY_FEED cuando esté conectado.

### Alpaca
- **Fuente oficial**: https://docs.alpaca.markets/us/docs/paper-trading y
  https://alpaca.markets/sdks/python/trading.html
- REST (`paper-api.alpaca.markets` / `api.alpaca.markets`) + WebSocket
  (`trade_updates`: eventos `new`, `fill` con partial fills documentados).
- Paper trading gratuito e ilimitado, balance inicial configurable (default $100k),
  misma especificación de API que live.
- Activos: US equities, options, crypto. **No ofrece FX** — descartado para XAUUSD spot FX-style.
- Dato de mercado en cuentas paper-only: IEX (limitado).
- SDK oficial: `alpaca-py`.
- **Para ORION**: candidato equities (SPX-proxy ETFs, acciones) y panel crypto.

### Interactive Brokers — TWS API
- **Fuente oficial**: https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc
- Arquitectura: protocolo socket TCP contra Trader Workstation o IB Gateway locales
  (requieren JVM); clientes oficiales Python/Java/C++/C#/VB (C# y Excel solo Windows).
- Hasta 32 clients simultáneos por instancia TWS/Gateway.
- Market data depende de suscripciones contratadas: "market data you can receive in
  Trader Workstation may not be available in the API".
- Librerías de terceros (`ib_insync`, `ib_async`) explícitamente NO soportadas por IBKR.
- **Para ORION**: máxima cobertura de activos, pero exige proceso TWS/Gateway vivo —
  registrar como dependencia operativa en el health dashboard si se integra.

### Interactive Brokers — Web API (ex Client Portal)
- **Fuente oficial**: https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/
- Migración en curso: Client Portal Web API + Digital Account Management + Flex Web
  Service se unifican bajo OAuth 2.0 ("existing endpoints are not deprecated").
- Individuales: requiere cuenta live IBKR Pro abierta y fondeada para usar el Web API
  (incluido acceso al paper asociado). Gateway headless local u OAuth (institucional).
- Terceros (vendors): actualmente solo OAuth 1.0a con aprobación de Compliance.
- **Para ORION**: vigilar evolución; hoy el camino retail es TWS API.

### MetaTrader 5 (capa aplicable a VT Markets y cualquier broker MT5)
- **Fuente oficial**: https://www.mql5.com/en/docs/python_metatrader5 y PyPI `metatrader5`.
- Package oficial `MetaTrader5` (pip) — **solo wheels Windows x86-64**; requiere terminal
  MT5 instalado, corriendo y logueado en la misma máquina.
- Funciones clave: `initialize`, `account_info`, `symbol_info_tick`, `copy_rates_from_pos`,
  `order_check`, `order_send`, `positions_get`.
- Seguridad: el terminal puede bloquear trading externo vía opción "Disable automatic
  trading via external Python API" → error 10027 `TRADE_RETCODE_CLIENT_DISABLES_AT`.
- **Para ORION**: adaptador factible en este host (Windows), pero acoplado a un terminal
  gráfico vivo; marcar feeds derivados del terminal como SECONDARY_FEED.

### VT Markets
- **Fuentes**: Help Centre oficial https://get.vtmarkets.help/hc/en-us/sections/37061868448921-MetaTrader-4-MetaTrader-5
  y FAQ oficial https://www.vtmarkets.com/en-eu/faq/a-complete-faq-on-vt-markets-metatrader-4-and-metatrader-5/
- No publica una API REST propia: el acceso programático es vía terminales MT4/MT5.
- Demo: MT4 válida 90 días, MT5 30 días desde último login (renovable en Client Portal).
- Servidor alterna GMT+2/GMT+3 (ancla NY close 17:00 EST).
- Existen límites documentados de high-frequency trading (Help Centre) — consultar antes
  de cualquier integración de ejecución frecuente.
- FIX/API connectivity mencionada SOLO en reseña de terceros (bestbrokers.com, 2026-06):
  **fuente secundaria, no confirmada en documentación oficial — tratar como NOT AVAILABLE**
  hasta verificar con el broker directamente.

---

## Reglas ORION para cualquier integración futura

1. **Ningún adaptador se marca LIVE sin conexión verificada** contra entorno paper/practice.
2. Orden de preferencia propuesta: OANDA practice (FX/metales) → Alpaca paper (equities)
   → MT5/VT Markets (solo si el workflow lo justifica).
3. Cada fill real debe publicar `POSITION_UPDATE` / `ORDER_UPDATE` en el event bus y
   quedar auditado con provenance del feed que lo originó.
4. El gate `ORION_LIVE_MODE` + `ORION_LIVE_CONFIRM_TOKEN` permanece obligatorio;
   ningún broker adapter puede saltarse el flujo IDEA → CIO → RISK → HUMAN APPROVAL.
5. Este documento no constituye recomendación de broker ni asesoría financiera.
