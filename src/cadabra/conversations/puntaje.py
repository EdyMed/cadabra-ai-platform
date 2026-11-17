"""Puntaje del lead (0-100): un clasificador de IA lee lo que dijo el cliente y unos pesos fijos lo convierten
en puntaje. Traducción de los nodos "Score: preparar / clasificar / calcular / guardar" de n8n.
"""
import json
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.agents.contexto import ContextoTurno

PESO_INTENCION = {"compra": 40, "cotizacion": 35, "agendar": 30, "consulta_producto": 20, "soporte_postventa": 5}
INTENCIONES = ["compra", "cotizacion", "agendar", "consulta_producto", "soporte_postventa", "reclamo",
               "saludo_o_charla", "otro"]


@dataclass
class Puntaje:
    score: int
    registrar: bool
    puntos: dict[str, int]
    clasificacion: dict[str, Any]


def pedido_clasificador(ctx: ContextoTurno, modelo: str) -> dict[str, Any]:
    """Mismo prompt y mismo esquema JSON que "Score: preparar"."""
    cfg = ctx.config
    categorias = [c["nombre"] for c in ((cfg.get("interes") or {}).get("categorias") or [])
                  if isinstance(c, dict) and c.get("nombre")]
    previos = [f"- {str(h['content'])[:400]}" for h in ctx.historial if h.get("role") == "user"][-5:]
    actual = str(ctx.mensaje or "")[:1500]
    negocio = str((cfg.get("negocio") or {}).get("descripcion") or ctx.nombre_empresa or "")[:400]

    categoria = ({"anyOf": [{"type": "string", "enum": categorias}, {"type": "null"}]} if categorias
                 else {"type": ["string", "null"]})
    esquema = {
        "type": "object", "additionalProperties": False,
        "required": ["intencion", "categoria", "cantidad", "es_negocio", "urgencia", "pide_humano", "resumen"],
        "properties": {
            "intencion": {"type": "string", "enum": INTENCIONES},
            "categoria": categoria,
            "cantidad": {"type": ["string", "null"],
                         "description": 'Cantidad o volumen mencionado (ej. "200 unidades", "3 docenas"), o null'},
            "es_negocio": {"type": "boolean", "description": "true si el cliente compra para un negocio (local, "
                                                             "restaurant, empresa, almacén, etc.)"},
            "urgencia": {"type": "string", "enum": ["alta", "media", "baja", "sin_dato"]},
            "pide_humano": {"type": "boolean"},
            "resumen": {"type": "string", "description": "Qué busca el cliente, en máximo 15 palabras, en español"},
        },
    }
    sistema = (
        "Clasificas a clientes que escriben por WhatsApp a un negocio, para priorizar el seguimiento comercial. "
        f"Negocio: {negocio}. "
        + (f"Categorías de producto válidas: {', '.join(categorias)}. " if categorias else "")
        + "Considera TODO lo que el cliente ha dicho (mensajes previos + actual), no solo el último. "
        "intencion: compra = quiere comprar/hacer un pedido; cotizacion = pide precios para comprar o una cotización; "
        "agendar = quiere reunión/visita/cita; consulta_producto = pregunta por productos sin intención clara de "
        "compra; saludo_o_charla = saludo, gracias o charla sin consulta. urgencia: alta si dice hoy/mañana/urgente/"
        "esta semana; media si da un plazo cercano; baja si dice más adelante; si no dice nada, sin_dato. No inventes "
        "datos: si algo no se menciona, usa null/false/sin_dato."
    )
    usuario = ("Mensajes anteriores del cliente:\n" + "\n".join(previos) + "\n\n" if previos else "") \
        + "Mensaje actual:\n" + actual
    return {
        "model": modelo, "temperature": 0, "max_tokens": 250,
        "response_format": {"type": "json_schema", "json_schema": {"name": "lead", "strict": True, "schema": esquema}},
        "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
    }


def calcular(clasificacion: dict[str, Any]) -> Puntaje:
    """Pesos fijos de "Score: calcular"."""
    d = clasificacion
    puntos = {
        "intencion": PESO_INTENCION.get(d.get("intencion"), 0),
        "categoria": 10 if d.get("categoria") else 0,
        "cantidad": 15 if d.get("cantidad") else 0,
        "negocio": 15 if d.get("es_negocio") else 0,
        "urgencia": {"alta": 15, "media": 8}.get(d.get("urgencia"), 0),
        "pide_humano": 5 if d.get("pide_humano") else 0,
    }
    registrar = d.get("intencion") in ("compra", "cotizacion", "consulta_producto", "agendar") \
        and bool(d.get("categoria") or d.get("cantidad"))
    return Puntaje(min(100, sum(puntos.values())), registrar, puntos, d)


async def clasificar(ctx: ContextoTurno, api_key: str, modelo: str) -> Puntaje | None:
    """None si el clasificador falla o devuelve algo ilegible (igual que n8n: el puntaje es opcional)."""
    try:
        respuesta = await AsyncOpenAI(api_key=api_key).chat.completions.create(**pedido_clasificador(ctx, modelo))
        return calcular(json.loads(respuesta.choices[0].message.content or ""))
    except Exception:  # noqa: BLE001 — el puntaje nunca debe romper el turno
        return None


# El puntaje "envejece": si el último tiene más de 14 días se reemplaza; si no, se queda el mayor.
SQL_GUARDAR = text("""
    insert into crm.crm_leads (empresa, contact_id, phone, producto_interes, estado_crm, origen_lead, bot_activo,
                               score, score_detalle, score_at)
    select cast(:empresa as int), cast(:contacto as bigint), cast(:contacto as bigint), cast(:producto as text),
           'Nuevo Lead', 'WhatsApp (IA)', true, cast(:score as int), cast(:detalle as jsonb), now()
    where cast(:registrar as boolean)
       or exists (select 1 from crm.crm_leads where empresa = cast(:empresa as int) and contact_id = cast(:contacto as bigint))
    on conflict (empresa, contact_id) do update set
      score = case when crm.crm_leads.score is null or crm.crm_leads.score_at < now() - interval '14 days'
                   then excluded.score else greatest(crm.crm_leads.score, excluded.score) end,
      score_detalle = case when crm.crm_leads.score is null or crm.crm_leads.score_at < now() - interval '14 days'
                             or excluded.score >= crm.crm_leads.score
                           then excluded.score_detalle else crm.crm_leads.score_detalle end,
      score_at = now(),
      producto_interes = coalesce(crm.crm_leads.producto_interes, excluded.producto_interes)
""")


async def guardar(sesion: AsyncSession, ctx: ContextoTurno, p: Puntaje, modelo: str) -> None:
    contacto = re.sub(r"\D", "", ctx.telefono)
    categoria = p.clasificacion.get("categoria")
    await sesion.execute(SQL_GUARDAR, {
        "empresa": ctx.empresa, "contacto": int(contacto),
        "producto": str(categoria)[:60] if categoria else None, "score": p.score, "registrar": p.registrar,
        "detalle": json.dumps({**p.clasificacion, "puntos": p.puntos, "modelo": modelo}, ensure_ascii=False),
    })
