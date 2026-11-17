-- Cadabra AI Platform — usuarios de base de datos (ejecutar UNA vez en Supabase → SQL Editor).
-- Antes de ejecutar: reemplazar las dos contraseñas por valores largos y aleatorios (sin "#").
-- Impacto en lo existente: ninguno. Solo AGREGA permisos y políticas para los roles nuevos;
-- n8n, el panel y sus roles siguen igual.

-- 1) Roles
create role platform_migrator login password 'CAMBIAR_MIGRATOR';
create role platform_app login password 'CAMBIAR_APP' nobypassrls;

-- 2) Schema propio de la plataforma (dueño: el migrador)
create schema if not exists platform authorization platform_migrator;
grant create on database postgres to platform_migrator;
grant usage on schema platform to platform_app;
alter default privileges for role platform_migrator in schema platform
  grant select, insert, update, delete on tables to platform_app;
alter default privileges for role platform_migrator in schema platform
  grant usage, select on sequences to platform_app;
alter default privileges for role platform_migrator in schema platform
  grant execute on functions to platform_app;

-- 3) Lectura de las tablas actuales (sin modificarlas)
grant usage on schema public, crm to platform_migrator, platform_app;
grant select on public.agente_lineas_whatsapp, public.dashboard_usuarios to platform_migrator;  -- carga inicial
grant select on public.agente_lineas_whatsapp, public.agente_whatsapp_cuentas, public.agente_empresas_config,
               public.agente_contactos, public.bot_pausas, public.whatsapp_contactos,
               public.conversation_history to platform_app;
grant insert on public.conversation_history to platform_app;   -- convivencia: el panel sigue viendo todo
grant select on crm.crm_leads, crm.vendedores to platform_app;

-- 4) Políticas RLS para los roles nuevos en las tablas actuales.
--    Carga inicial: el migrador lee todas las filas de estas dos tablas.
create policy platform_migrator_carga on public.agente_lineas_whatsapp for select to platform_migrator using (true);
create policy platform_migrator_carga on public.dashboard_usuarios     for select to platform_migrator using (true);
--    La app solo ve las filas de la empresa fijada en app.tenant_id.
do $$
declare t text;
begin
  foreach t in array array[
    'public.agente_lineas_whatsapp', 'public.agente_whatsapp_cuentas', 'public.agente_empresas_config',
    'public.agente_contactos', 'public.bot_pausas', 'public.whatsapp_contactos', 'public.conversation_history',
    'crm.crm_leads', 'crm.vendedores']
  loop
    execute format(
      'create policy platform_app_tenant on %s to platform_app '
      'using (empresa = nullif(current_setting(''app.tenant_id'', true), '''')::int) '
      'with check (empresa = nullif(current_setting(''app.tenant_id'', true), '''')::int)', t);
  end loop;
end $$;
