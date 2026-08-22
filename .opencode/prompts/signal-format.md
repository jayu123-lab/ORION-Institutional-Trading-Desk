# Formato obligatorio de señal de trade (ORION)

Toda idea de trade propuesta por cualquier analista DEBE incluir TODOS estos campos.
Sin campos vacíos: si un campo no aplica, escribe `N/A — <motivo>`.

```yaml
asset:                # ticker normalizado, ej. XAUUSD, BTCUSD, NQ
timestamp_utc:        # ISO-8601 UTC del análisis
data_source:          # provider + quality status (LIVE/DELAYED/SIMULATED...)
price_used:           # precio exacto utilizado y su timestamp
timeframe:            # ej. H1, D1, M15
direction:            # LONG | SHORT | FLAT
entry:                # precio de entrada o zona (con condición)
invalidation:         # nivel/condición que invalida la tesis ANTES del SL
stop_loss:            # nivel absoluto
targets:              # TP1 / TP2 / TP3 con niveles
risk_reward:          # R:R calculado sobre entrada-SL vs TP1..TPn
probability:          # 0-100% estimado de alcanzar TP1 antes que SL
confidence:           # LOW | MODERATE | HIGH | VERY HIGH
horizon:              # intraday | days | weeks
technical_thesis:     # estructura, niveles, liquidez, confluencias
fundamental_thesis:   # macro/fundamental relevante o N/A
catalysts:            # eventos con fecha (CPI, FOMC, earnings...)
risks:                # riesgos específicos de esta idea
liquidity_notes:      # sesiones relevantes, volumen, spreads
activation_conditions:# qué debe cumplirse para ACTIVAR la orden
cancel_conditions:    # qué cancela la idea sin activarla
```

Reglas:
- R:R mínimo orientativo 1.5 en setups no institucionales; si es menor, justifícalo.
- probability y confidence deben ser coherentes entre sí.
- Si falta dato de mercado para fijar un nivel: `NO DATA AVAILABLE`, no inventar.
