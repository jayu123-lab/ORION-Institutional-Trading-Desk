---
description: Ejecuta backtest de una estrategia registrada o solicita uno nuevo. Muestra IS/WFS/OOS, Monte Carlo y sensibilidad de parámetros.
agent: quant-architect
subtask: true
---

Objetivo: $ARGUMENTS (nombre/ID de estrategia en DB o descripción).

1. Localiza la estrategia (tabla strategies) y datos históricos (candles) disponibles.
   Sin datos suficientes → especifica exactamente qué falta (activo, timeframe, rango).
2. Si existe motor disponible: ejecuta backtest con costes realistas (spread, slippage,
   comisión), walk-forward, OOS y Monte Carlo; reporta expectancy, PF, win rate,
   max DD, Sharpe, nº trades.
3. Sensibilidad: variación ±20-50% de parámetros → meseta vs pico.
4. VERDICT + confidence + limitaciones. Nunca prometas rentabilidad futura.
