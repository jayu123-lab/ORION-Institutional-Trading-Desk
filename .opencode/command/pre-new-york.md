---
description: Workflow PRE-NEW-YORK — consolidación London, datos US del día, LIKELY NEW YORK LEVEL, dealer target del día.
agent: orion-cio
subtask: true
---

Workflow PRE-NEW-YORK:
1. Resumen London (highs/lows, barridos ejecutados, estado vs plan).
2. `news-intelligence`: calendario NY (data 8:30/10:00 ET, FOMC speakers).
3. `liquidity-agent`: gamma walls, zonas dealer, DEALER TARGET OF THE DAY.
4. `macro-strategist`: sesgo por yields/DXY intradía.
5. Output: PLAN DE NY — escenarios (+prob), niveles clave, invalidaciones,
   condiciones de no-trade (ej. pre-CPI), alertas sugeridas. Trade ideas → risk-manager.
