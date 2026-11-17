# Modelo de datos — schema `platform` (propuesta para aprobar)

Estado: **aprobado el 17-11-2026, aún no ejecutado en Supabase**. Migraciones: `0001_schema_platform.py`
(estructura) y `0002_carga_tenants_lineas.py` (carga inicial). Roles: `scripts/supabase_roles.sql`.

## Principios

1. **No se duplica lo que ya existe.** La plataforma lee y reutiliza estas tablas actuales sin cambiarlas:
   `public.agente_lineas_whatsapp` (número → empresa), `public.agente_whatsapp_cuentas` (WABA, token cifrado,
   modo coexistencia), `public.agente_empresas_config` (ficha JSONB), `public.dashboard_usuarios` (usuarios del
   panel, Supabase Auth), `crm.*` (leads, vendedores), `public.bot_pausas`, `public.whatsapp_contactos` y el ERP.
2. **`tenant_id` = el entero `empresa` actual.** No hay tabla de correspondencia: la empresa 1 es el tenant 1.
3. **RLS en todas las tablas con `tenant_id`**: `tenant_id = current_setting('app.tenant_id')::int`, con el rol
   `platform_app` sin `BYPASSRLS`. La única lectura sin tenant es `platform.resolver_linea(phone_number_id)`,
   una función `SECURITY DEFINER` que devuelve tenant, agente y motor de un número.
4. **Durante la convivencia** los workers escriben también en `public.conversation_history`, para que el panel
   siga viendo todas las conversaciones.

## Entidades nuevas

| Tabla | Para qué | Claves e índices | Retención |
| --- | --- | --- | --- |
| `tenants` | Empresa en la plataforma: nombre, plan, estado | PK `id` (= `empresa`) | Permanente |
| `agents` | Agente de una empresa (ventas, agenda…) y su versión activa | PK uuid; único `(tenant_id, nombre)` | Permanente |
| `agent_versions` | Configuración versionada: instrucciones, modelo, parámetros, límites (JSONB). La v1 copia la ficha actual | PK uuid; único `(agent_id, numero)` | Permanente |
| `lineas` | Número de WhatsApp → agente y **motor** (`n8n` o `codigo`). Aquí vive el interruptor de migración, sin tocar `agente_lineas_whatsapp` | PK `phone_number_id`; índice `tenant_id` | Permanente |
| `conversations` | Una conversación por (número del negocio, contacto) | PK uuid; único `(tenant_id, phone_number_id, contacto)` | Permanente |
| `messages` | Mensajes entrantes y salientes, con estado de entrega | PK bigint; único parcial `message_id`; índice `(conversation_id, creado_en)` | Permanente (se borra a pedido del titular) |
| `webhook_events` | Registro de cada evento de Meta recibido y su procesamiento | PK bigint; índice `(estado, recibido_en)` | 30 días |
| `agent_executions` | Cada ejecución del agente: estado, latencia, tokens, costo, modelo, traza | PK uuid; índice `(tenant_id, iniciado_en)` | 12 meses |
| `execution_events` | Pasos de una ejecución: llamadas al modelo, herramientas, interrupciones, errores | PK bigint; índice `execution_id` | 90 días |
| `tool_definitions` | Catálogo global de herramientas: contrato, riesgo, permiso requerido | PK `clave` | Permanente |
| `tool_permissions` | Herramientas habilitadas por agente y para qué roles (owner, cliente) | PK `(agent_id, tool_clave)` | Permanente |
| `integrations` | Integraciones de una empresa (Calendar, ERP, Sheets…) y su estado | PK uuid; único `(tenant_id, tipo, nombre)` | Permanente |
| `credentials` | Secretos de cada integración, cifrados con AES-256-GCM (mismo formato que el panel) | PK uuid; FK a `integrations` | Hasta revocar |
| `usage_records` | Consumo medible: mensajes, tokens, plantillas, costo | PK bigint; índice `(tenant_id, periodo, metrica)` | 24 meses |
| `audit_logs` | Quién cambió qué y cuándo; solo inserción | PK bigint; índice `(tenant_id, creado_en)` | 24 meses |

**No se crean** `users` ni `roles`: los usuarios siguen en Supabase Auth + `public.dashboard_usuarios`. Se
revisará cuando el control plane reemplace la administración del panel.

**Checkpoints de LangGraph:** el `PostgresSaver` crea sus propias tablas; se ubicarán en `platform` y el
`thread_id` será `"{tenant_id}:{conversation_id}"`. Se agregan en la Etapa 4.

## Roles de base de datos

| Rol | Uso | Permisos |
| --- | --- | --- |
| `platform_migrator` | Alembic | Dueño del schema `platform` |
| `platform_app` | API y workers | DML en `platform` sujeto a RLS; `SELECT` en las tablas actuales que lee; `INSERT` en `public.conversation_history`. Sin `BYPASSRLS` |

Los roles se crean una vez con `scripts/supabase_roles.sql` en el SQL Editor de Supabase; las migraciones no
crean roles. Ese script solo agrega permisos y políticas para los roles nuevos: en las tablas actuales,
`platform_app` ve únicamente las filas de la empresa fijada en `app.tenant_id`.

## Decisiones

- **Plan comercial (17-11-2026):** `tenants.plan` es la fuente única. La carga inicial toma el plan más frecuente
  de cada empresa en `dashboard_usuarios.plan`. El panel seguirá leyendo `dashboard_usuarios` hasta que consuma la
  API `/v1`; ese cambio del panel se hará con aprobación aparte.

## Pendiente de decidir

- Si `messages` reemplaza a `conversation_history` al terminar la migración o ambas conviven.
