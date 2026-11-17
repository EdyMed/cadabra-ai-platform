-- Cadabra AI Platform — lectura del ERP mediante vistas (Supabase → SQL Editor, como postgres).
-- Se puede ejecutar más de una vez.
--
-- Por qué: las políticas RLS del ERP sobre productos, familias, movimientos_ventas y saldos_clientes consultan
-- public.usuarios, y la política de public.usuarios se consulta a sí misma ("infinite recursion detected in policy
-- for relation usuarios"). Cualquier rol sin BYPASSRLS falla al leer esas tablas.
-- Estas vistas son de postgres (que no evalúa esas políticas) y filtran por la empresa fijada en app.tenant_id,
-- así platform_app lee solo su empresa, solo las columnas necesarias, y sin tocar las políticas del ERP.
-- Impacto en lo existente: ninguno (no modifica tablas ni políticas del ERP).

create schema if not exists erp_lectura;
grant usage on schema erp_lectura to platform_app;
grant usage on schema erp_lectura to platform_migrator;   -- solo para scripts/verificar_sql.py (sin SELECT)

create or replace view erp_lectura.productos with (security_barrier) as
  select empresa, codigo, nombre, precio_venta, cod_familia, estado_vigencia
  from public.productos
  where empresa = nullif(current_setting('app.tenant_id', true), '')::int;

create or replace view erp_lectura.familias with (security_barrier) as
  select empresa, codigo, nombre
  from public.familias
  where empresa = nullif(current_setting('app.tenant_id', true), '')::int;

create or replace view erp_lectura.catalogo_productos with (security_barrier) as
  select empresa, codigo, nombre, categoria, descripcion, precio, unidad, disponible
  from public.catalogo_productos
  where empresa = nullif(current_setting('app.tenant_id', true), '')::int;

create or replace view erp_lectura.movimientos_ventas with (security_barrier) as
  select empresa, fecha_documento, numero_documento, codigo_producto, cantidad, total_incluido
  from public.movimientos_ventas
  where empresa = nullif(current_setting('app.tenant_id', true), '')::int;

-- Solo clientes con deuda en la empresa del turno (clientes no tiene columna empresa).
create or replace view erp_lectura.deudas_clientes with (security_barrier) as
  select s.empresa, s.cliente, c.nombre_empresa, c.paterno_cl, c.materno_cl, c.nombre_cl, s.saldo_deuda
  from public.saldos_clientes s
  join public.clientes c on c.rut_cl = s.cliente
  where s.empresa = nullif(current_setting('app.tenant_id', true), '')::int
    and s.saldo_deuda > 0;

grant select on all tables in schema erp_lectura to platform_app;

-- Ya no se lee el ERP directo: se retiran los permisos y políticas del paso anterior.
revoke select on public.productos, public.familias, public.catalogo_productos, public.movimientos_ventas,
                 public.saldos_clientes, public.clientes from platform_app;
drop policy if exists platform_app_tenant on public.productos;
drop policy if exists platform_app_tenant on public.familias;
drop policy if exists platform_app_tenant on public.catalogo_productos;
drop policy if exists platform_app_tenant on public.movimientos_ventas;
drop policy if exists platform_app_tenant on public.saldos_clientes;
drop policy if exists platform_app_lectura on public.clientes;
