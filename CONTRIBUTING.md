# Contributing

## Reglas del dominio (no negociables)

1. Datos simulados siempre etiquetados `SIMULATED`; jamás presentarlos como live.
2. Sin datos frescos → estados `STALE`/`DISCONNECTED`; prohibido usar el último
   precio como actual.
3. Ninguna ruta de código permite a un analista ejecutar órdenes.
4. Auditabilidad: toda decisión relevante escribe registro append-only con
   timestamp/source/agent/confidence.
5. Antes de integrar una API externa: verificar documentación oficial vigente.
   No inventar endpoints.

## Flujo de trabajo

- Branches por feature desde `main`: `feature/<tema>`, `fix/<tema>`.
- Commits pequeños y descriptivos (convención tipo `feat(risk): ...`).
- PR requerido para `main`. CI verde obligatorio:
  `ruff check`, `ruff format --check`, `mypy core providers agents apps/api`,
  `pytest`, `python scripts/check_secrets.py`.

## Estilo

- Python 3.12+, tipado completo, async cuando haya I/O.
- Sin comentarios innecesarios; docstrings breves solo donde aportan.
- Frontend TypeScript estricto; componentes pequeños; tema oscuro institucional.

## Añadir un proveedor de datos

Ver `docs/DATA_SOURCES.md`: implementar `MarketDataProvider`, declarar calidad de
datos, registrar en el registry, añadir tests con fixtures (sin red en tests).
