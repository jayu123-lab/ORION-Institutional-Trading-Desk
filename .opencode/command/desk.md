---
description: Convoca la mesa completa para analizar un activo o tema. Invoca en paralelo a Macro, Metals/Liquidity/Quant/News según el activo, consolida desacuerdos y produce el análisis institucional con CIO al frente. Uso: "/desk XAUUSD" o sin argumento para estado general de la mesa.
agent: orion-cio
subtask: true
---

Ejecuta el protocolo completo de convocatoria de mesa.

Objetivo: $ARGUMENTS (si está vacío: estado general de la mesa y del mercado según DB).

Pasos:
1. Consulta datos actuales del activo en la base (quotes recientes; verifica quality/status).
2. Invoca EN PARALELO como subagents: `macro-strategist`, el especialista del activo
   (`metals-analyst` si metal, `crypto-analyst` si crypto, `equities-analyst` si índice),
   `liquidity-agent`, `news-intelligence`, `polymarket-agent` si aplica evento predictivo.
3. Consolida con formato FACTS / INFERENCES / SCENARIOS / TRADE IDEAS / RISKS /
   MISSING DATA. Muestra desacuerdos entre agentes SIN suavizarlos.
4. Si surge trade idea viable → pásala por `risk-manager` e incluye el veredicto.
5. Cierra con INSTITUTIONAL BIAS + confidence + próximos catalizadores.
