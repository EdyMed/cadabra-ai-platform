"""Paso 2 del worker: procesar un turno completo de una conversación.

  1. espera el debounce y confirma que este mensaje es el último (si no, otro procesará el lote)
  2. toma el candado de la conversación (un turno a la vez, en orden)
  3. vacía el buzón: todos los mensajes seguidos forman un solo texto
  4. carga el contexto y ejecuta el agente
  5. guarda el turno en el historial, lo que detecta post_turno (lead, puntaje) y registra la ejecución
  6. ya confirmado lo anterior: responde por WhatsApp, cuenta la conversación y hace lo que post_turno pidió
     hacia afuera (alerta al vendedor, evento en Calendar, aviso de horario)
En modo ensayo se calcula todo, pero solo se escribe el registro de la ejecución.
"""
import asyncio
import json
import logging
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.agents.agente import ResultadoAgente, responder
from cadabra.agents.contexto import cargar_contexto
from cadabra.conversations import post_turno
from cadabra.conversations.buzon import Buzon
from cadabra.core.config import Settings
from cadabra.db.session import sesion_tenant
from cadabra.integrations.n8n import ClienteN8n
from cadabra.messaging.whatsapp_api import ClienteWhatsApp
from cadabra.tenancy.context import fijar_tenant
from cadabra.tools.base import EntornoHerramienta

log = logging.getLogger(__name__)

AVISO_SIN_CONFIGURAR = (
    "✅ Agente configurado correctamente. Falta configurar el negocio asociado a este número (catálogo, horarios y "
    "datos de atención). Mientras tanto, el asistente no responderá consultas."
)
ESPERA_CANDADO_SEGUNDOS = 60


async def procesar_turno(tenant_id: int, conversacion: str, message_id: str,
                         buzon: Buzon, settings: Settings, whatsapp: ClienteWhatsApp, n8n: ClienteN8n) -> None:
    fijar_tenant(tenant_id)
    await asyncio.sleep(settings.debounce_segundos)
    if not await buzon.es_el_ultimo(conversacion, message_id):
        return

    token = await _esperar_candado(buzon, conversacion)
    if token is None:
        log.warning("no se obtuvo el candado de la conversación", extra={"datos": {"conversacion": conversacion}})
        return
    try:
        mensajes = await buzon.vaciar(conversacion)
        if mensajes:
            await _atender(tenant_id, conversacion, message_id, "\n".join(mensajes).strip(), settings, whatsapp, n8n)
    finally:
        await buzon.soltar_candado(conversacion, token)


async def _esperar_candado(buzon: Buzon, conversacion: str) -> str | None:
    for _ in range(ESPERA_CANDADO_SEGUNDOS):
        token = await buzon.tomar_candado(conversacion)
        if token:
            return token
        await asyncio.sleep(1)
    return None


async def _atender(tenant_id: int, conversacion: str, message_id: str, texto: str,
                   settings: Settings, whatsapp: ClienteWhatsApp, n8n: ClienteN8n) -> None:
    _, phone_number_id, telefono = conversacion.split(":", 2)
    inicio = time.monotonic()

    async with sesion_tenant(tenant_id) as sesion:
        ctx = await cargar_contexto(sesion, phone_number_id, telefono, texto)
        if ctx is None:
            return
        resultado: ResultadoAgente | None = None
        post: post_turno.PostTurno | None = None
        if not ctx.configurado:
            respuesta = AVISO_SIN_CONFIGURAR
        else:
            entorno = EntornoHerramienta(ctx=ctx, sesion=sesion, whatsapp=whatsapp, ensayo=settings.modo_ensayo)
            resultado = await responder(ctx, entorno, settings)
            respuesta = resultado.respuesta
            if not resultado.error:
                if not settings.modo_ensayo:
                    await _guardar_turno(sesion, ctx.empresa, telefono, texto, message_id, respuesta)
                post = await post_turno.en_la_base(sesion, ctx, respuesta, settings)
            await _registrar(sesion, tenant_id, resultado, post, texto, int((time.monotonic() - inicio) * 1000))

    # Fuera de la transacción: lo escrito en la base ya quedó confirmado aunque un envío falle.
    if respuesta:
        await whatsapp.enviar_texto(phone_number_id, telefono, respuesta)
        if resultado is not None:
            await n8n.contar_conversacion(ctx.empresa, telefono)
    if post is not None:
        await post_turno.hacia_afuera(post, ctx, n8n, whatsapp)
    log.info("turno atendido", extra={"datos": {
        "conversacion": conversacion, "ensayo": settings.modo_ensayo, "respuesta": respuesta,
        "herramientas": [ll["herramienta"] for ll in (resultado.llamadas if resultado else [])],
    }})


SQL_GUARDAR_TURNO = text("""
    insert into public.conversation_history (empresa, phone_number, role, content, message_id, recibido_at)
    values (:empresa, :tel, 'user', :entrada, :mid, now()),
           (:empresa, :tel, 'assistant', :salida, null, null)
    on conflict (message_id) where message_id is not null do nothing
""")


async def _guardar_turno(sesion: AsyncSession, empresa: int, tel: str, entrada: str, mid: str, salida: str) -> None:
    await sesion.execute(SQL_GUARDAR_TURNO, {"empresa": empresa, "tel": tel, "entrada": entrada, "mid": mid,
                                             "salida": salida})


SQL_EJECUCION = text("""
    insert into platform.agent_executions
      (tenant_id, estado, modelo, tokens_entrada, tokens_salida, latencia_ms, error, terminado_en)
    values (:tenant, :estado, :modelo, :te, :ts, :lat, :error, now())
    returning id
""")
SQL_EVENTO = text("""
    insert into platform.execution_events (tenant_id, execution_id, tipo, nombre, entrada, salida)
    values (:tenant, :ejecucion, :tipo, :nombre, cast(:entrada as jsonb), cast(:salida as jsonb))
""")


async def _registrar(sesion: AsyncSession, tenant_id: int, r: ResultadoAgente, post: post_turno.PostTurno | None,
                     entrada: str, latencia_ms: int) -> None:
    ejecucion = (await sesion.execute(SQL_EJECUCION, {
        "tenant": tenant_id, "estado": "error" if r.error else "ok", "modelo": r.modelo,
        "te": r.tokens_entrada, "ts": r.tokens_salida, "lat": latencia_ms, "error": r.error,
    })).scalar_one()
    eventos = [("herramienta", ll["herramienta"], ll["argumentos"], ll["resultado"]) for ll in r.llamadas]
    eventos.append(("llm", "respuesta", {"mensaje": entrada}, {"respuesta": r.respuesta}))
    if post is not None:
        eventos.append(("herramienta", "post_turno", {}, post.resumen()))
    for tipo, nombre, e, s in eventos:
        await sesion.execute(SQL_EVENTO, {
            "tenant": tenant_id, "ejecucion": ejecucion, "tipo": tipo, "nombre": nombre,
            "entrada": json.dumps(e, ensure_ascii=False, default=str),
            "salida": json.dumps(s, ensure_ascii=False, default=str),
        })
