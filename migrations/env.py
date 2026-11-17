"""Alembic sobre Supabase: solo administra el schema "platform"; nunca toca crm ni las tablas actuales."""
import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cadabra.core.config import get_settings

ESQUEMA = "platform"


def _url() -> str:
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("Falta CADABRA_DATABASE_URL")
    return url.get_secret_value()


def _migrar(conexion) -> None:
    context.configure(connection=conexion, target_metadata=None, version_table_schema=ESQUEMA, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()


async def _online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conexion:
        await conexion.execute(text(f"create schema if not exists {ESQUEMA}"))
        await conexion.commit()
        await conexion.run_sync(_migrar)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=_url(), literal_binds=True, version_table_schema=ESQUEMA)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(_online())
