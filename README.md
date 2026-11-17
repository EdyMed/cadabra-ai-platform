# Cadabra AI Platform

Plataforma propia de agentes de IA multiempresa sobre WhatsApp Business Platform. Reemplaza de forma
progresiva al agente construido en n8n, que **sigue en producción** hasta que cada empresa se migre.

- Auditoría de partida (16-11-2026): https://claude.ai/artifact/R1sCmdmA8ReJCM1Fka667B
- Decisiones de arquitectura: [`docs/adr/`](docs/adr/)
- Despliegue en el VPS (EasyPanel): [`docs/despliegue.md`](docs/despliegue.md)

## Arquitectura esencial

| Pieza | Qué hace |
| --- | --- |
| `api` (FastAPI) | Gateway de webhooks de Meta: valida la firma, descarta duplicados, encola y responde 200. Luego, API `/v1` del control plane |
| `worker` (Taskiq) | Procesa la cola: tenant, agente (LangGraph, Etapa 4), envío y registro |
| Redis | Cola y descarte de duplicados. En el VPS, el Redis existente (claves `plat:`) |
| Supabase Postgres | La base actual. La plataforma solo crea tablas en el schema `platform` y lee el resto sin cambiarlo |

## Estructura

```
src/cadabra/
  core/          configuración, logs JSON, firma de Meta
  tenancy/       contexto de tenant y ejecución
  db/            sesiones con app.tenant_id para RLS
  api/           app FastAPI
  messaging/     gateway de WhatsApp, duplicados, lectura de eventos
  workers/       broker y tareas Taskiq
  agents/ tools/ integrations/ billing/ administration/   (se llenan en las Etapas 2 a 4)
migrations/      Alembic (schema platform)
docker/          Dockerfile único
tests/
docs/adr/
```

## Desarrollo local

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # Windows
cp .env.example .env                                 # completar valores
.venv/Scripts/python -m pytest
.venv/Scripts/uvicorn cadabra.api.main:app --reload
.venv/Scripts/taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas
```

## Reglas

- No se modifica producción (n8n, tablas actuales, integraciones) sin aprobación.
- Ningún secreto en el código ni en los logs: todo por variables `CADABRA_*`.
- Cada decisión de arquitectura queda en un ADR.
