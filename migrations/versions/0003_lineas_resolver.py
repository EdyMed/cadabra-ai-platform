"""platform.lineas: el dueño (función resolver_linea) la lee sin tenant; platform_app sigue limitado por RLS

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-17

resolver_linea es SECURITY DEFINER (corre como platform_migrator, dueño de la tabla). Con FORCE RLS el dueño
también queda sujeto a la política y, sin app.tenant_id fijado, la función no encontraba ninguna línea.
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("alter table platform.lineas no force row level security")


def downgrade() -> None:
    op.execute("alter table platform.lineas force row level security")
