---
description: ¿Qué está descontando Polymarket? Probabilidades actuales de mercados relevantes (Fed, elecciones, geopolítica) y comparativa cross-asset.
agent: polymarket-agent
subtask: true
---

Objetivo: $ARGUMENTS (tema/mercado opcional; vacío = mercados de mayor volumen abiertos
relevantes para la mesa: Fed rates, elecciones, geopolítica, economía).

1. Usa Gamma API oficial (gamma-api.polymarket.com) vía webfetch o el adapter:
   discovery + probabilidad YES + spread + volumen. Recuerda parsear outcomePrices
   (viene como string JSON).
2. Para cada mercado relevante: probabilidad actual (+timestamp), delta reciente,
   interpretación.
3. Compara contra precios reales de SPX/GOLD/BTC/DXY/YIELDS si están en DB.
4. Diagnóstico: PRICED IN / DIVERGENCIA POTENCIAL / EVENT RISK / NOISE.
