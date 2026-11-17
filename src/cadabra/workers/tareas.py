"""Tareas de los workers. Comando: taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas

Dos tareas, una por paso (ver docs/motor-agente.md):
  whatsapp.procesar_evento  → conversations/entrada.py  (evento de Meta → buzón)
  whatsapp.procesar_turno   → conversations/turno.py    (buzón → agente → respuesta)
"""
import logging
from functools import lru_cache
from typing import Any

from redis.asyncio import Redis
from taskiq import TaskiqEvents, TaskiqState

from cadabra.conversations import entrada, turno
from cadabra.conversations.buzon import Buzon
from cadabra.core.config import get_settings
from cadabra.core.logging import configurar_logs
from cadabra.messaging.meta_eventos import ids_de_mensajes
from cadabra.messaging.whatsapp_api import ClienteWhatsApp
from cadabra.workers.broker import broker

log = logging.getLogger(__name__)


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def al_iniciar(_: TaskiqState) -> None:
    settings = get_settings()
    configurar_logs(settings.log_level)
    log.info("worker iniciado", extra={"datos": {"modo_ensayo": settings.modo_ensayo, "modelo": settings.modelo}})


@lru_cache
def _buzon() -> Buzon:
    return Buzon(Redis.from_url(get_settings().redis_url.get_secret_value()))


def _whatsapp() -> ClienteWhatsApp:
    s = get_settings()
    return ClienteWhatsApp(s.meta_token.get_secret_value(), s.meta_graph_version, ensayo=s.modo_ensayo)


async def _agendar_turno(tenant_id: int, conversacion: str, message_id: str) -> None:
    await procesar_turno.kiq(tenant_id, conversacion, message_id)


@broker.task(task_name="whatsapp.procesar_evento", retry_on_error=True)
async def procesar_evento_whatsapp(evento: dict[str, Any]) -> None:
    log.info("evento de WhatsApp recibido", extra={"datos": {"message_ids": ids_de_mensajes(evento)}})
    await entrada.procesar_evento(evento, _buzon(), get_settings(), _agendar_turno)


# Sin reintentos automáticos: reintentar un turno podría responder dos veces al cliente.
@broker.task(task_name="whatsapp.procesar_turno")
async def procesar_turno(tenant_id: int, conversacion: str, message_id: str) -> None:
    await turno.procesar_turno(tenant_id, conversacion, message_id, _buzon(), get_settings(), _whatsapp())
