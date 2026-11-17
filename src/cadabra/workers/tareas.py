"""Tareas de los workers. Comando: taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas

Dos tareas, una por paso (ver docs/motor-agente.md):
  whatsapp.procesar_evento  → conversations/entrada.py  (evento de Meta → buzón; audio/foto/PDF → texto)
  whatsapp.procesar_turno   → conversations/turno.py    (buzón → agente → respuesta → post_turno)
"""
import asyncio
import contextlib
import logging
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI
from redis.asyncio import Redis
from taskiq import TaskiqEvents, TaskiqState

from cadabra.conversations import entrada, multimedia, turno
from cadabra.conversations.buzon import Buzon
from cadabra.core.config import get_settings
from cadabra.core.logging import configurar_logs
from cadabra.integrations.n8n import ClienteN8n
from cadabra.messaging import media
from cadabra.messaging.meta_eventos import ids_de_mensajes
from cadabra.messaging.whatsapp_api import ClienteWhatsApp
from cadabra.workers.broker import broker

log = logging.getLogger(__name__)


# Latido: el worker renueva esta clave cada 30 s; /healthz la lee para saber si hay un worker vivo.
LATIDO = "plat:worker:latido"


async def _latir() -> None:
    while True:
        try:
            await _redis().set(LATIDO, "1", ex=120)
        except Exception:  # el latido nunca debe botar al worker
            log.exception("no se pudo registrar el latido del worker")
        await asyncio.sleep(30)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def al_iniciar(state: TaskiqState) -> None:
    settings = get_settings()
    configurar_logs(settings.log_level)
    state.latido = asyncio.create_task(_latir())
    log.info("worker iniciado", extra={"datos": {"modo_ensayo": settings.modo_ensayo, "modelo": settings.modelo}})


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def al_detener(state: TaskiqState) -> None:
    tarea = getattr(state, "latido", None)
    if tarea:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url.get_secret_value())


def _whatsapp() -> ClienteWhatsApp:
    s = get_settings()
    return ClienteWhatsApp(s.meta_token.get_secret_value(), s.meta_graph_version, ensayo=s.modo_ensayo)


def _n8n() -> ClienteN8n:
    s = get_settings()
    return ClienteN8n(s.n8n_url, s.n8n_clave.get_secret_value(), ensayo=s.modo_ensayo)


async def _leer_medio(media_id: str, medio: multimedia.Medio) -> str:
    """Descarga el archivo desde Meta y lo convierte en texto (solo lectura: también corre en modo ensayo)."""
    s = get_settings()
    try:
        archivo = await media.descargar(media_id, s.meta_token.get_secret_value(), s.meta_graph_version)
    except Exception:  # sin archivo, el agente recibe el texto de respaldo
        log.exception("no se pudo descargar el archivo desde Meta", extra={"datos": {"tipo": medio.tipo}})
        archivo = None
    cliente = AsyncOpenAI(api_key=s.openai_api_key.get_secret_value())
    return await multimedia.a_texto(medio, archivo, cliente, s.modelo_audio, s.modelo_vision)


async def _agendar_turno(tenant_id: int, conversacion: str, message_id: str) -> None:
    await procesar_turno.kiq(tenant_id, conversacion, message_id)


@broker.task(task_name="whatsapp.procesar_evento", retry_on_error=True)
async def procesar_evento_whatsapp(evento: dict[str, Any]) -> None:
    log.info("evento de WhatsApp recibido", extra={"datos": {"message_ids": ids_de_mensajes(evento)}})
    await entrada.procesar_evento(evento, entrada.Dependencias(
        buzon=Buzon(_redis()), redis=_redis(), settings=get_settings(), whatsapp=_whatsapp(), n8n=_n8n(),
        agendar_turno=_agendar_turno, leer_medio=_leer_medio,
    ))


# Sin reintentos automáticos: reintentar un turno podría responder dos veces al cliente.
@broker.task(task_name="whatsapp.procesar_turno")
async def procesar_turno(tenant_id: int, conversacion: str, message_id: str) -> None:
    await turno.procesar_turno(tenant_id, conversacion, message_id, Buzon(_redis()), get_settings(), _whatsapp(),
                               _n8n())
