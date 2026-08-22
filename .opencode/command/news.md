---
description: Últimas noticias relevantes clasificadas (CRITICAL→NOISE) con análisis expected vs actual reaction.
agent: news-intelligence
subtask: true
---

Objetivo: $ARGUMENTS (activo/filtro opcional).

1. Lee news de DB ordenadas por relevancia/timestamp; si está vacía y tienes web
   disponible, busca titulares macro/mercados de las últimas 24h en fuentes oficiales
   citando URL+fecha.
2. Clasifica cada pieza: CRITICAL/HIGH/MEDIUM/LOW/NOISE + activos afectados.
3. Para datos macro: ACTUAL vs CONSENSUS vs PREVIOUS vs REACCIÓN REAL; diagnostica
   BTRSTN / STRBN / PRICED IN / SQUEEZE / LIQUIDITY EVENT cuando aplique.
4. Implicaciones para la sesión actual y próxima.
