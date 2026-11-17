"""Prepara (sin ejecutar) todas las consultas SQL del código contra la base real.

Postgres valida tipos, columnas y políticas al preparar, así que esto detecta errores antes de desplegar.
Uso (con CADABRA_DATABASE_URL en .env):  .venv/Scripts/python scripts/verificar_sql.py
"""
import asyncio

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine

from cadabra.agents import contexto
from cadabra.conversations import entrada, turno
from cadabra.core.config import get_settings
from cadabra.tools import catalogo, crm, gestion

CONSULTAS = {
    "stock_producto": catalogo.SQL, "ventas_periodo": gestion.SQL_VENTAS, "top_productos": gestion.SQL_TOP,
    "saldo_cliente": gestion.SQL_SALDO, "crm_buscar": crm.SQL_BUSCAR, "contexto_empresa": contexto.SQL_EMPRESA,
    "contexto_rol": contexto.SQL_ROL_Y_LEAD, "contexto_historial": contexto.SQL_HISTORIAL,
    "resolver_linea": entrada.SQL_LINEA, "bot_activo": entrada.SQL_BOT_ACTIVO,
    "guardar_turno": turno.SQL_GUARDAR_TURNO, "registrar_ejecucion": turno.SQL_EJECUCION,
    "registrar_evento": turno.SQL_EVENTO,
}


async def main() -> int:
    url = get_settings().database_url
    if url is None:
        raise SystemExit("Falta CADABRA_DATABASE_URL")
    engine = create_async_engine(url.get_secret_value())
    fallas = 0
    async with engine.connect() as conexion:
        crudo = (await conexion.get_raw_connection()).driver_connection
        for nombre, consulta in CONSULTAS.items():
            sql = str(consulta.compile(dialect=postgresql.asyncpg.dialect()))
            try:
                await crudo.prepare(sql)
                print(f"OK     {nombre}")
            except Exception as e:  # noqa: BLE001 — se informa y se sigue con la siguiente
                fallas += 1
                print(f"FALLA  {nombre}: {type(e).__name__}: {str(e)[:160]}")
    await engine.dispose()
    return fallas


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
