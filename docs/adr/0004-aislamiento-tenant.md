# ADR 0004: Aislamiento por tenant con RLS en el schema platform

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

Cada tabla nueva lleva `tenant_id`. Las políticas RLS comparan con `current_setting('app.tenant_id')`, que `db.session.sesion_tenant` fija por transacción. El rol de la plataforma no tiene `BYPASSRLS`. El tenant se resuelve en el servidor (p. ej. desde el `phone_number_id`), nunca desde datos del cliente.

## Alternativas descartadas

Filtrar solo en el código: es la situación actual del agente en n8n y la auditoría la marcó como riesgo alto.

## Consecuencias

Pruebas automáticas de acceso cruzado obligatorias para cada tabla nueva.
