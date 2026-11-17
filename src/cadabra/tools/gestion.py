"""Herramientas de gestión del negocio. SOLO se entregan al modelo cuando el contacto es owner.

Leen las vistas erp_lectura.* (ya filtradas por la empresa del turno; ver scripts/supabase_vistas_erp.sql).
"""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import text

from cadabra.tools.base import EntornoHerramienta, Herramienta


class Periodo(BaseModel):
    desde: date = Field(description="fecha inicio del período, formato AAAA-MM-DD")
    hasta: date = Field(description="fecha fin EXCLUSIVA del período, formato AAAA-MM-DD")


class PeriodoRanking(Periodo):
    limite: int = Field(default=5, ge=1, le=50, description="cuántos productos (default 5)")
    orden: Literal["monto", "unidades"] = Field(default="monto", description="monto o unidades")


class NombreCliente(BaseModel):
    nombre: str = Field(description="nombre, apellido o razón social del cliente a buscar")


# ---- ventas_periodo -------------------------------------------------------------------------------------------

SQL_VENTAS = text("""
    select coalesce(round(sum(total_incluido)), 0) as ventas_clp, count(distinct numero_documento) as documentos
    from erp_lectura.movimientos_ventas
    where empresa = cast(:empresa as int) and fecha_documento >= cast(:desde as date) and fecha_documento < cast(:hasta as date)
""")


async def ventas_periodo(entorno: EntornoHerramienta, args: Periodo) -> dict:
    fila = await entorno.sesion.execute(SQL_VENTAS, {"empresa": entorno.ctx.empresa, **args.model_dump()})
    return dict(fila.mappings().one())


VENTAS_PERIODO = Herramienta(
    nombre="ventas_periodo",
    descripcion=(
        "Devuelve el TOTAL de ventas (en pesos CLP) y la cantidad de documentos de un período. Úsala cuando el dueño "
        "pregunte cuánto se vendió (hoy, ayer, esta semana, este mes, un mes específico, etc.). Pasa 'desde' y 'hasta' "
        "como fechas AAAA-MM-DD (hasta es exclusivo: para 'enero' usa desde=2026-01-01 hasta=2026-02-01)."
    ),
    argumentos=Periodo,
    ejecutar=ventas_periodo,
    solo_owner=True,
)

# ---- top_productos --------------------------------------------------------------------------------------------

SQL_TOP = text("""
    select p.nombre, round(sum(mv.total_incluido)) as monto_clp, round(sum(mv.cantidad)) as unidades
    from erp_lectura.movimientos_ventas mv
    left join erp_lectura.productos p on p.codigo = mv.codigo_producto and p.empresa = mv.empresa
    where mv.empresa = cast(:empresa as int) and mv.fecha_documento >= cast(:desde as date) and mv.fecha_documento < cast(:hasta as date)
    group by p.nombre
    order by (case when cast(:orden as text) = 'unidades' then sum(mv.cantidad) else sum(mv.total_incluido) end) desc nulls last
    limit cast(:limite as int)
""")


async def top_productos(entorno: EntornoHerramienta, args: PeriodoRanking) -> list[dict]:
    filas = await entorno.sesion.execute(SQL_TOP, {"empresa": entorno.ctx.empresa, **args.model_dump()})
    return [dict(f) for f in filas.mappings()]


TOP_PRODUCTOS = Herramienta(
    nombre="top_productos",
    descripcion=(
        "Devuelve el RANKING de productos más vendidos en un período (nombre, monto en CLP y unidades). Úsala cuando "
        "el dueño pregunte por 'productos más vendidos', 'top productos', 'qué se vende más'. Parámetros: desde y "
        "hasta (AAAA-MM-DD, hasta exclusivo), limite (cuántos, default 5), y orden ('monto' o 'unidades', default "
        "monto)."
    ),
    argumentos=PeriodoRanking,
    ejecutar=top_productos,
    solo_owner=True,
)

# ---- saldo_cliente --------------------------------------------------------------------------------------------

SQL_SALDO = text("""
    select coalesce(d.nombre_empresa, trim(d.paterno_cl||' '||coalesce(d.materno_cl,'')||' '||d.nombre_cl)) as cliente,
           round(d.saldo_deuda) as deuda_clp
    from erp_lectura.deudas_clientes d
    where d.empresa = cast(:empresa as int)
      and (
        lower(coalesce(d.nombre_empresa,'')) like '%'||lower(cast(:nombre as text))||'%'
        or lower(coalesce(d.paterno_cl,'')) like '%'||lower(cast(:nombre as text))||'%'
        or lower(coalesce(d.materno_cl,'')) like '%'||lower(cast(:nombre as text))||'%'
        or lower(coalesce(d.nombre_cl,'')) like '%'||lower(cast(:nombre as text))||'%'
      )
    order by d.saldo_deuda desc
    limit 8
""")


async def saldo_cliente(entorno: EntornoHerramienta, args: NombreCliente) -> list[dict]:
    filas = await entorno.sesion.execute(SQL_SALDO, {"empresa": entorno.ctx.empresa, "nombre": args.nombre})
    return [dict(f) for f in filas.mappings()]


SALDO_CLIENTE = Herramienta(
    nombre="saldo_cliente",
    descripcion=(
        "Consulta la DEUDA (saldo pendiente) de un cliente buscándolo por nombre o apellido. Úsala cuando el dueño "
        "pregunte cuánto le debe un cliente (ej. 'cuánto me debe Guerrero', 'deuda de Delicity'). Parámetro: nombre = "
        "nombre, apellido o razón social del cliente a buscar. Devuelve el nombre completo y la deuda en CLP. Solo "
        "para el owner."
    ),
    argumentos=NombreCliente,
    ejecutar=saldo_cliente,
    solo_owner=True,
)
