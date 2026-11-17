-- Cadabra AI Platform — permisos del motor del agente (Supabase → SQL Editor). Se puede ejecutar más de una vez.
-- Impacto en lo existente: ninguno. Solo agrega permisos para platform_app; n8n y el panel siguen igual.
-- La lectura del ERP va por vistas: ver supabase_vistas_erp.sql (las políticas del ERP no permiten leerlo directo).

-- Escritura del CRM (crm_guardar_lead / crm_actualizar_estado), solo sobre la empresa del turno
-- (la política platform_app_tenant de crm.crm_leads se creó en supabase_roles.sql).
grant insert, update on crm.crm_leads to platform_app;
do $$
declare s text := pg_get_serial_sequence('crm.crm_leads', 'id');
begin
  if s is not null then execute format('grant usage, select on sequence %s to platform_app', s); end if;
end $$;
