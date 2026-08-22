---
description: Análisis equities/índices (SPX, NASDAQ, NQ, ES, acciones). Earnings, breadth, rotación sectorial, gamma. Uso: "/equities NASDAQ" o "/equities".
agent: orion-cio
subtask: true
---

Objetivo: $ARGUMENTS (vacío = SPX, NASDAQ/NQ, DOW, RUSSELL).

1. Quotes índices de DB con quality status.
2. Invoca `equities-analyst` (earnings/breadth/rotación/gamma), `macro-strategist`
   (yields → growth pressure), `liquidity-agent` si hay datos de perfil.
3. Ranking interno STRONG BUY BIAS→STRONG SELL BIAS + desacuerdos + escenarios.
4. Trade ideas solo vía risk-manager.
