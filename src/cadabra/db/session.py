"""Acceso a Postgres (Supabase). Cada transacción fija app.tenant_id para que RLS filtre por empresa."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from cadabra.core.config import get_settings

_engine: AsyncEngine | None = None
_sesiones: async_sessionmaker[AsyncSession] | None = None


def engine() -> AsyncEngine:
    global _engine, _sesiones
    if _engine is None:
        url = get_settings().database_url
        if url is None:
            raise RuntimeError("Falta CADABRA_DATABASE_URL")
        _engine = create_async_engine(url.get_secret_value(), pool_pre_ping=True, pool_size=5, max_overflow=5)
        _sesiones = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def sesion_tenant(tenant_id: int) -> AsyncIterator[AsyncSession]:
    """Transacción con el tenant fijado: las políticas RLS leen current_setting('app.tenant_id')."""
    engine()
    assert _sesiones is not None
    async with _sesiones() as sesion, sesion.begin():
        await sesion.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)})
        yield sesion


@asynccontextmanager
async def sesion_sin_tenant() -> AsyncIterator[AsyncSession]:
    """Solo para lo que no depende de un tenant: hoy, platform.resolver_linea (SECURITY DEFINER)."""
    engine()
    assert _sesiones is not None
    async with _sesiones() as sesion, sesion.begin():
        yield sesion
