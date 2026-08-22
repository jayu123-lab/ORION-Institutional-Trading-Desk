# Security Policy

## Modelo de seguridad

1. **Secretos**: nunca en el repositorio. Solo en `.env` (git-ignorado).
   Plantilla pública en `.env.example`. CI ejecuta `scripts/check_secrets.py`
   y bloquea merges con patrones de claves (API keys, secrets, private keys,
   seed phrases).
2. **Ejecución**:
   - `PAPER MODE` por defecto.
   - `LIVE MODE` desactivado por defecto: exige `ORION_LIVE_MODE=true`
     **y** `ORION_LIVE_CONFIRM_TOKEN` correcto.
   - Ningún agente LLM/analista puede enviar órdenes: solo el flujo
     `TRADE IDEA → CIO → RISK → EXECUTION PREVIEW → HUMAN APPROVAL → BROKER GATEWAY`.
   - Prohibida la automatización de navegador/GUI como vía de ejecución.
3. **Permisos mínimos** en OpenCode: analistas sin `edit` ni `bash`;
   execution-trader sin shell; solo interfaces definidas por `ExecutionGateway`.
4. **Webhooks**: TradingView autentica mediante cabecera secreta
   (`X-ORION-Secret`). Las credenciales jamás viajan en el payload.
5. **Logs**: no se registran secretos; los adaptadores filtran claves conocidas.

## Reportar una vulnerabilidad

Abre un issue con etiqueta `security` **sin detalles explotables**, o contacta
privadamente con los maintainers. Respuesta objetivo: 72h.

## Alcance

Incluye: fuga de secretos, bypass del flujo de aprobación, inyección vía webhook,
escalada de permisos de agentes. Excluye: calidad/señales de estrategias (no es
vulnerabilidad).
