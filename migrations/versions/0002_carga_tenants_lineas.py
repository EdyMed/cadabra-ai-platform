"""Carga inicial: empresas (con su plan) y líneas de WhatsApp desde las tablas actuales

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-17

- tenants.plan pasa a ser la fuente única del plan (decisión del 17-11-2026). Hoy el plan está por usuario en
  public.dashboard_usuarios; se toma el más frecuente de cada empresa.
- Todas las líneas entran con motor = 'n8n': nada cambia en producción hasta moverlas a 'codigo'.
- Como las tablas tienen FORCE RLS, cada fila se inserta con app.tenant_id fijado a su empresa.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

CARGA = """
do $$
declare r record;
begin
  for r in
    with empresas as (
      select empresa, max(nombre_empresa) as nombre from public.agente_lineas_whatsapp group by empresa
      union
      select empresa, max(nombre_empresa) from public.dashboard_usuarios where empresa is not null group by empresa
    ),
    planes as (
      select empresa, mode() within group (order by plan) as plan
      from public.dashboard_usuarios where plan is not null group by empresa
    )
    select e.empresa, coalesce(max(e.nombre), 'Empresa ' || e.empresa) as nombre, max(p.plan) as plan
    from empresas e left join planes p on p.empresa = e.empresa
    group by e.empresa
  loop
    perform set_config('app.tenant_id', r.empresa::text, true);
    insert into platform.tenants (id, nombre, plan) values (r.empresa, r.nombre, r.plan)
      on conflict (id) do nothing;
    insert into platform.lineas (phone_number_id, tenant_id, motor)
      select l.phone_number_id, l.empresa, 'n8n' from public.agente_lineas_whatsapp l where l.empresa = r.empresa
      on conflict (phone_number_id) do nothing;
  end loop;
  perform set_config('app.tenant_id', '', true);
end $$
"""


def upgrade() -> None:
    op.execute(CARGA)


def downgrade() -> None:
    op.execute("""
do $$
declare r record;
begin
  -- Con FORCE RLS no se ven las filas sin tenant fijado: se recorre la misma lista de empresas de la carga.
  for r in
    select empresa from public.agente_lineas_whatsapp
    union select empresa from public.dashboard_usuarios where empresa is not null
  loop
    perform set_config('app.tenant_id', r.empresa::text, true);
    delete from platform.lineas where tenant_id = r.empresa;
    delete from platform.tenants where id = r.empresa;
  end loop;
end $$
""")
