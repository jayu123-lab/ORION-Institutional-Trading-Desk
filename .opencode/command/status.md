---
description: Estado del sistema — feeds, DB, monitor, agentes, alertas activas, última actividad por componente.
agent: orion-cio
subtask: true
---

Diagnóstico de sistema:
1. Lee de DB: últimas quotes por fuente (¿stale? ¿disconnected?), últimas alerts,
   heartbeat del monitor, registros de agentes.
2. Reporta tabla: componente | estado (CONNECTED/DEGRADED/STALE/DISCONNECTED) |
   última actualización | detalle.
3. Lista alertas activas y eventos pendientes del calendario si existen.
4. Conclusión: ¿sistema operativo para análisis? ¿qué reparar primero?
