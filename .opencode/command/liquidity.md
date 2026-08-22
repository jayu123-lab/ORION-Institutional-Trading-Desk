---
description: Mapa de liquidez y microestructura — POC/VAH/VAL, VWAP anclado, zonas dealer, gamma walls, liquidity pools. Uso: "/liquidity XAUUSD".
agent: liquidity-agent
subtask: true
---

Objetivo: $ARGUMENTS (activo; vacío = watchlist principal).

1. Lee candles/volume data disponibles en DB para construir perfil si hay volumen;
   sin volumen por tick → decláralo y usa aproximación por velas.
2. Genera (solo con datos reales): POC/VAH/VAL, HVN/LVN, VWAP y anchored VWAP a eventos,
   Liquidity Pools (stops obvios), Dealer Buy/Sell Zones, Gamma Walls (si feed de opciones).
3. Rutas probables: escenarios de barrido de liquidez por sesión (Asia/London/NY).
4. MISSING DATA explícito para lo que el feed actual no cubre.
