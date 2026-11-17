# ADR 0002: Mantener Supabase y crear solo el schema platform

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

La plataforma usa el mismo proyecto Supabase. Todo lo nuevo vive en el schema `platform`, administrado por Alembic. Las tablas actuales (`public.agente_*`, `conversation_history`, `crm.*`, ERP) se leen sin modificarlas mientras convivan n8n y la plataforma. Se recomienda el plan Pro para evitar pausas.

## Alternativas descartadas

Postgres nuevo en el VPS: obliga a mover o replicar el ERP que consultan las herramientas.

## Consecuencias

Sin migración de datos al inicio. Alembic nunca toca otros schemas.
