---
description: Análisis de mercado del activo indicado (o watchlist completa). Consulta quotes frescos + especialista correspondiente + contexto macro. Uso: "/market BTCUSD" o "/market".
agent: orion-cio
subtask: true
---

Objetivo: $ARGUMENTS (vacío = watchlist: XAUUSD, BTCUSD, ETHUSD, XRPUSD, NQ, ES, DXY, US10Y).

Pasos:
1. Lee quotes/candles recientes de la DB; marca STALE/DISCONNECTED si aplica.
2. Para cada activo relevante invoca al especialista correcto (metals/crypto/equities).
3. Resume por activo: precio (fuente+timestamp+quality), bias interno, nivel clave,
   evento próximo. Formato FACTS/INFERENCES/RISKS. Sin datos → NO DATA AVAILABLE.
