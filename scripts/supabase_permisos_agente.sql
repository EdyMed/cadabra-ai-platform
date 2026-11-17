-- Cadabra AI Platform — permisos del motor del agente (Supabase → SQL Editor). Se puede ejecutar más de una vez.
-- Impacto en lo existente: ninguno. Solo agrega permisos y políticas para platform_app; n8n y el panel siguen igual.

-- 1) Lectura del ERP que consultan las herramientas (stock_producto, ventas_periodo, top_productos, saldo_cliente)
grant select on public.productos, public.familias, public.catalogo_productos, public.movimientos_ventas,
               public.saldos_clientes, public.clientes to platform_app;

-- 2) Escritura del CRM (crm_guardar_lead / crm_actualizar_estado), solo sobre la empresa del turno (política ya creada)
grant insert, update on crm.crm_leads to platform_app;
do $$
declare s text := pg_get_serial_sequence('crm.crm_leads', 'id');
begin
  if s is not null then execute format('grant usage, select on sequence %s to platform_app', s); end if;
end $$;

-- 3) Políticas RLS: platform_app solo ve las filas de la empresa fijada en app.tenant_id
do $$
declare t text;
begin
  foreach t in array array['public.productos', 'public.familias', 'public.catalogo_productos',
                           'public.movimientos_ventas', 'public.saldos_clientes']
  loop
    execute format('drop policy if exists platform_app_tenant on %s', t);
    execute format(
      'create policy platform_app_tenant on %s for select to platform_app '
      'using (empresa = nullif(current_setting(''app.tenant_id'', true), '''')::int)', t);
  end loop;
end $$;

-- public.clientes no tiene columna empresa: la consulta de deudas la filtra por empresa a través de
-- saldos_clientes (que sí está limitada por la política de arriba).
drop policy if exists platform_app_lectura on public.clientes;
create policy platform_app_lectura on public.clientes for select to platform_app using (true);
