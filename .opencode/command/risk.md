---
description: Estado de riesgo de la cuenta — equity, drawdown, exposición total/por activo/correlacionada, límites diario/semanal, métricas históricas.
agent: risk-manager
subtask: true
---

Reporte de riesgo actual:

1. Lee risk_snapshots y positions de DB (si no hay snapshot reciente, dilo).
2. Reporta: equity, balance, open PnL, drawdown actual/máx, exposición total,
   por activo y correlacionada, riesgo diario/semanal usado vs límite,
   trades abiertos con su % de riesgo.
3. Métricas históricas si hay trades cerrados: win rate, profit factor, expectancy,
   Sharpe/Sortino, R-multiples.
4. VEREDICTO GLOBAL: GREEN LIGHT / CAUTION / RED LIGHT con motivos.
   No inventes números: faltan datos → MISSING DATA explícito.
