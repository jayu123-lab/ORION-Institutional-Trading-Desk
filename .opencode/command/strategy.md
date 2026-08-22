---
description: Evalúa o diseña una estrategia — confluencia no redundante, validación cuantitativa completa, veredicto sobre overfitting. Uso: "/strategy <descripción>".
agent: quant-architect
subtask: true
---

Objetivo: $ARGUMENTS (vacío = revisar estrategias registradas en DB).

Si hay descripción de estrategia:
1. Formalízala: universo, timeframe, señales por CONFLUENCIA NO REDUNDANTE (elimina
   indicadores redundantes y dilo), gestión, costes asumidos.
2. Plan de validación: backtest IS → walk-forward → OOS → Monte Carlo → sensibilidad.
   Si tienes acceso a datos históricos en DB/backtests engine, ejecuta; si no,
   especifica exactamente qué datos necesitas.
3. Veredicto: VIABLE / VIABLE CON CAMBIOS / REJECTED (+motivo, ej. OVERFIT)
   con expectancy esperada y limitaciones.
