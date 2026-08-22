---
description: Análisis crypto general o de un activo (BTC, ETH, SOL...). Funding, OI, liquidations, ETF flows, on-chain, dominancia.
agent: orion-cio
subtask: true
---

Objetivo: $ARGUMENTS (vacío = BTC, ETH, SOL + BTC.D).

1. Quotes DB (spot/perp distinguidos) con quality status.
2. Invoca `crypto-analyst` (funding/OI/liquidations/basis/flujos/on-chain/dominancia).
3. Si hay evento macro o regulatorio → `news-intelligence`; si hay mercado predictivo
   relevante → `polymarket-agent`.
4. Consolida FACTS/INFERENCES/SCENARIOS(+prob)/TRADE IDEAS (vía risk-manager)/RISKS.
