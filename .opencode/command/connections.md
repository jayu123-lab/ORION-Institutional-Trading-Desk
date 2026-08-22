---
description: Conexiones y fuentes de datos — proveedores configurados, estado LIVE/STALE/DISCONNECTED/SIMULATED de cada uno, latencia.
agent: orion-cio
subtask: true
---

Inventario de conexiones:
1. Lee tabla sources y últimas quotes/alertas de DB.
2. Por cada fuente: nombre | tipo (REST/WS/WEBHOOK) | estado
   (LIVE/DELAYED/STALE/DISCONNECTED/SIMULATED) | última actualización | latencia media.
3. Marca qué credenciales faltan para activar feeds adicionales (.env.example como guía)
   SIN pedir secretos en el chat.
4. Recomendación priorizada de qué conectar siguiente y su impacto en la mesa.
