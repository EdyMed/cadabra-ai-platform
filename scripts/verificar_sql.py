"""Prepara (sin ejecutar) todas las consultas SQL del código contra la base real.

Postgres valida tipos, columnas y políticas al preparar, así que esto detecta errores antes de desplegar.
Uso (con CADABRA_DATABASE_URL en .env):  .venv/Scripts/python scripts/verificar_sql.py
"""
import asyncio

from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine

from cadabra.agents import contexto
from cadabra.conversations import entrada, puntaje, turno
from cadabra.core.config import get_settings
from cadabra.messaging import ruteo
from cadabra.tools import catalogo, crm, gestion

CONSULTAS = {
    "stock_producto": catalogo.SQL, "ventas_periodo": gestion.SQL_VENTAS, "top_productos": gestion.SQL_TOP,
    "saldo_cliente": gestion.SQL_SALDO, "crm_buscar": crm.SQL_BUSCAR, "contexto_empresa": contexto.SQL_EMPRESA,
    "contexto_rol": contexto.SQL_ROL_Y_LEAD, "contexto_historial": contexto.SQL_HISTORIAL,
    "resolver_linea": entrada.SQL_LINEA, "ruteo_motor": ruteo.SQL_MOTOR, "control_entrada": entrada.SQL_CONTROL,
    "guardar_puntaje": puntaje.SQL_GUARDAR,
    "guardar_turno": turno.SQL_GUARDAR_TURNO, "registrar_ejecucion": turno.SQL_EJECUCION,
    "registrar_evento": turno.SQL_EVENTO,
    # guardar_en_crm arma su SQL según los campos: se verifica con todas las columnas permitidas.
    "crm_insertar": text("insert into crm.crm_leads (" + ", ".join(crm.COLUMNAS) + ", empresa, contact_id, phone) values ("
                         + ", ".join(f":{c}" for c in crm.COLUMNAS) + ", :empresa, :contact_id, :phone) returning id"),
    "crm_actualizar": text("update crm.crm_leads set " + ", ".join(f"{c} = :{c}" for c in crm.COLUMNAS)
                           + " where id = :id and empresa = :empresa"),
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
