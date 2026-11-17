"""Schema platform: entidades base de la plataforma (BORRADOR, no ejecutar sin aprobación)

Revision ID: 0001
Revises:
Create Date: 2026-11-17
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TABLAS_CON_TENANT = [
    "tenants", "agents", "agent_versions", "lineas", "conversations", "messages", "webhook_events",
    "agent_executions", "execution_events", "tool_permissions", "integrations", "credentials",
    "usage_records", "audit_logs",
]

SQL = """
create table platform.tenants (
  id             int primary key,                 -- = public.*.empresa
  nombre         text not null,
  plan           text,
  estado         text not null default 'activo' check (estado in ('activo','suspendido','baja')),
  creado_en      timestamptz not null default now(),
  actualizado_en timestamptz not null default now()
);

create table platform.agents (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         int not null references platform.tenants(id),
  nombre            text not null,
  tipo              text not null default 'ventas',
  version_activa_id uuid,
  estado            text not null default 'activo' check (estado in ('activo','pausado','archivado')),
  creado_en         timestamptz not null default now(),
  unique (tenant_id, nombre)
);

create table platform.agent_versions (
  id           uuid primary key default gen_random_uuid(),
  tenant_id    int not null references platform.tenants(id),
  agent_id     uuid not null references platform.agents(id),
  numero       int not null,
  config       jsonb not null,                   -- instrucciones, tono, negocio, agenda, límites (ficha)
  modelo       text not null,
  parametros   jsonb not null default '{}'::jsonb,
  notas        text,
  creado_por   uuid,
  creado_en    timestamptz not null default now(),
  publicado_en timestamptz,
  unique (agent_id, numero)
);
alter table platform.agents
  add constraint agents_version_activa_fk foreign key (version_activa_id) references platform.agent_versions(id);

create table platform.lineas (
  phone_number_id text primary key,
  tenant_id       int not null references platform.tenants(id),
  agent_id        uuid references platform.agents(id),
  motor           text not null default 'n8n' check (motor in ('n8n','codigo')),
  actualizado_en  timestamptz not null default now()
);
create index on platform.lineas (tenant_id);

create table platform.conversations (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         int not null references platform.tenants(id),
  phone_number_id   text not null,
  contacto          text not null,               -- wa_id del cliente
  agent_id          uuid references platform.agents(id),
  estado            text not null default 'abierta' check (estado in ('abierta','humano','cerrada')),
  ultimo_mensaje_en timestamptz,
  creado_en         timestamptz not null default now(),
  unique (tenant_id, phone_number_id, contacto)
);

create table platform.messages (
  id              bigint generated always as identity primary key,
  tenant_id       int not null references platform.tenants(id),
  conversation_id uuid not null references platform.conversations(id),
  direccion       text not null check (direccion in ('entrante','saliente')),
  rol             text not null check (rol in ('user','assistant','vendedor','sistema')),
  tipo            text not null default 'text',
  contenido       text,
  message_id      text,
  estado_entrega  text,
  payload         jsonb,
  creado_en       timestamptz not null default now()
);
create unique index messages_message_id_uq on platform.messages (message_id) where message_id is not null;
create index on platform.messages (conversation_id, creado_en);

create table platform.webhook_events (
  id              bigint generated always as identity primary key,
  tenant_id       int references platform.tenants(id),   -- null hasta resolver el número
  phone_number_id text,
  campo           text,                                  -- messages, history, smb_message_echoes…
  message_ids     text[] not null default '{}',
  payload         jsonb not null,
  estado          text not null default 'recibido' check (estado in ('recibido','procesado','descartado','error')),
  intentos        int not null default 0,
  error           text,
  recibido_en     timestamptz not null default now(),
  procesado_en    timestamptz
);
create index on platform.webhook_events (estado, recibido_en);

create table platform.agent_executions (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        int not null references platform.tenants(id),
  conversation_id  uuid references platform.conversations(id),
  agent_version_id uuid references platform.agent_versions(id),
  estado           text not null check (estado in ('en_curso','ok','error','interrumpida')),
  modelo           text,
  tokens_entrada   int not null default 0,
  tokens_salida    int not null default 0,
  costo_usd        numeric(12,6) not null default 0,
  latencia_ms      int,
  trace_id         text,
  error            text,
  iniciado_en      timestamptz not null default now(),
  terminado_en     timestamptz
);
create index on platform.agent_executions (tenant_id, iniciado_en);

create table platform.execution_events (
  id           bigint generated always as identity primary key,
  tenant_id    int not null references platform.tenants(id),
  execution_id uuid not null references platform.agent_executions(id),
  tipo         text not null check (tipo in ('llm','herramienta','interrupcion','error')),
  nombre       text,
  entrada      jsonb,
  salida       jsonb,
  duracion_ms  int,
  creado_en    timestamptz not null default now()
);
create index on platform.execution_events (execution_id);

create table platform.tool_definitions (
  clave             text primary key,
  descripcion       text not null,
  riesgo            text not null check (riesgo in ('bajo','medio','alto')),
  permiso_requerido text not null,
  esquema_entrada   jsonb not null,
  version           int not null default 1
);

create table platform.tool_permissions (
  tenant_id        int not null references platform.tenants(id),
  agent_id         uuid not null references platform.agents(id),
  tool_clave       text not null references platform.tool_definitions(clave),
  habilitada       boolean not null default true,
  roles_permitidos text[] not null default '{owner}',
  config           jsonb not null default '{}'::jsonb,
  primary key (agent_id, tool_clave)
);

create table platform.integrations (
  id        uuid primary key default gen_random_uuid(),
  tenant_id int not null references platform.tenants(id),
  tipo      text not null,                       -- google_calendar, erp_supabase, google_sheets…
  nombre    text not null,
  estado    text not null default 'activa' check (estado in ('activa','error','desconectada')),
  config    jsonb not null default '{}'::jsonb,
  creado_en timestamptz not null default now(),
  unique (tenant_id, tipo, nombre)
);

create table platform.credentials (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       int not null references platform.tenants(id),
  integration_id  uuid not null references platform.integrations(id),
  secreto_cifrado text not null,                 -- base64(iv|tag|cifrado), AES-256-GCM
  metadatos       jsonb not null default '{}'::jsonb,
  rotado_en       timestamptz not null default now()
);

create table platform.usage_records (
  id           bigint generated always as identity primary key,
  tenant_id    int not null references platform.tenants(id),
  periodo      date not null,                    -- primer día del mes
  metrica      text not null,                    -- mensajes_servicio, tokens, plantilla_marketing…
  cantidad     numeric(14,2) not null,
  costo_usd    numeric(12,6),
  execution_id uuid references platform.agent_executions(id),
  creado_en    timestamptz not null default now()
);
create index on platform.usage_records (tenant_id, periodo, metrica);

create table platform.audit_logs (
  id         bigint generated always as identity primary key,
  tenant_id  int references platform.tenants(id),
  actor      text not null,                      -- auth_user_id, 'worker', 'sistema'
  accion     text not null,
  entidad    text not null,
  entidad_id text,
  antes      jsonb,
  despues    jsonb,
  creado_en  timestamptz not null default now()
);
create index on platform.audit_logs (tenant_id, creado_en);

-- Única lectura sin tenant: resolver el número entrante. Devuelve solo lo necesario.
create function platform.resolver_linea(p_phone_number_id text)
returns table (tenant_id int, agent_id uuid, motor text)
language sql stable security definer set search_path = platform as $$
  select l.tenant_id, l.agent_id, l.motor from platform.lineas l where l.phone_number_id = p_phone_number_id
$$;
"""


def upgrade() -> None:
    # asyncpg no admite varias sentencias en una llamada: se ejecutan una por una
    # (el cuerpo de la función no contiene ";").
    for sentencia in SQL.split(";"):
        if sentencia.strip():
            op.execute(sentencia)
    for tabla in TABLAS_CON_TENANT:
        columna = "id" if tabla == "tenants" else "tenant_id"
        op.execute(f"alter table platform.{tabla} enable row level security")
        op.execute(f"alter table platform.{tabla} force row level security")
        op.execute(
            f"create policy aislamiento_tenant on platform.{tabla} "
            f"using ({columna} = nullif(current_setting('app.tenant_id', true), '')::int) "
            f"with check ({columna} = nullif(current_setting('app.tenant_id', true), '')::int)"
        )


def downgrade() -> None:
    op.execute("drop function if exists platform.resolver_linea(text)")
    for tabla in reversed(TABLAS_CON_TENANT + ["tool_definitions"]):
        op.execute(f"drop table if exists platform.{tabla} cascade")
