"""stock_producto: busca productos y precios en el ERP o en el catálogo de Google Sheets. Disponible para todos."""
from pydantic import BaseModel, Field
from sqlalchemy import text

from cadabra.tools.base import EntornoHerramienta, Herramienta

# Misma consulta que la herramienta de n8n. Toma la fuente según la ficha: 'erp_supabase' u otra (catálogo propio).
SQL = text(r"""
with q as (
  select array_remove(string_to_array(lower(trim(cast(:busqueda as text))), ' '), '') as palabras
)
select distinct p.nombre, p.precio_venta, null::text as unidad
from public.productos p
left join public.familias f on f.codigo = p.cod_familia and f.empresa = p.empresa,
  q
where cast(:fuente as text) = 'erp_supabase'
  and p.empresa = cast(:empresa as int)
  and p.estado_vigencia = 1
  and lower(p.nombre) !~ '(guia|flete|emitidas|segun guias)'
  and (
    p.codigo = cast(:busqueda as text)
    or ( array_length(q.palabras,1) is not null
         and not exists (
           select 1 from unnest(q.palabras) w
           where w not in ('empanada','empanadas','de','al','la','el','los','las','horno','frita','fritas','hoja','y',
                           'con','insumo','insumos','producto','productos')
             and lower(p.nombre) !~ ('\y'||w||'\y')
             and coalesce(lower(f.nombre),'') !~ ('\y'||w||'\y')
         )
       )
  )
union all
select c.nombre || case when c.disponible then '' else ' (agotado)' end, c.precio, c.unidad
from public.catalogo_productos c, q
where cast(:fuente as text) <> 'erp_supabase'
  and c.empresa = cast(:empresa as int)
  and (
    lower(c.codigo) = lower(cast(:busqueda as text))
    or ( array_length(q.palabras,1) is not null
         and not exists (
           select 1 from unnest(q.palabras) w
           where w not in ('de','al','la','el','los','las','y','con','producto','productos')
             and lower(c.nombre || ' ' || coalesce(c.categoria,'') || ' ' || coalesce(c.descripcion,''))
                 !~ ('\y'||w||'\y')
         )
       )
  )
order by 1
limit 12
""")


class Busqueda(BaseModel):
    busqueda: str = Field(description="palabras clave del producto, ej: mariscos o pino queso")


async def ejecutar(entorno: EntornoHerramienta, args: Busqueda) -> list[dict]:
    filas = await entorno.sesion.execute(
        SQL,
        {"empresa": entorno.ctx.empresa, "busqueda": args.busqueda, "fuente": entorno.ctx.perfil.fuente_catalogo},
    )
    return [dict(f) for f in filas.mappings()]


STOCK_PRODUCTO = Herramienta(
    nombre="stock_producto",
    descripcion=(
        "Busca productos vigentes por palabra(s) clave y devuelve nombre y precio de venta. Pasa solo las palabras "
        "clave del producto (ej. 'mariscos', 'pino queso'), SIN palabras de relleno como 'empanada', 'de', 'al horno' "
        "ni 'frita'. Úsala para consultas de precio o disponibilidad de productos."
    ),
    argumentos=Busqueda,
    ejecutar=ejecutar,
)
