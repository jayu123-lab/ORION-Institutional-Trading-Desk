---
description: Prepara una orden a partir de una idea aprobada — genera ticket de ejecución en PAPER MODE pendiente de confirmación humana explícita. Uso: "/trade <descripción o ID de propuesta>".
agent: execution-trader
subtask: true
---

Objetivo: $ARGUMENTS (ID de trade_proposal aprobada o descripción).

1. Verifica estado: solo propuestas APPROVED/REDUCE SIZE del risk manager avanzan;
   si no lo está → REJECTED: "requiere paso previo por Risk".
2. Construye ORDER TICKET: asset, side, type (LIMIT/MARKET/STOP/STOP_LIMIT justificado),
   qty según sizing de Risk, entry, SL, TP1-3, R:R neto con spread/comisión estimados,
   mode=PAPER, state=AWAITING_HUMAN_CONFIRMATION.
3. Registra el ticket y muestra la confirmación humana requerida:
   "Confirmación HUMANA explícita necesaria para SUBMITTED". Nunca auto-envíes.
4. Si falta precio LIVE fresco: CANNOT PRICE ORDER - DATA STALE.
