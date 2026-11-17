"""Tareas de los workers. Comando: taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas"""
import logging
from typing import Any

from cadabra.messaging.meta_eventos import ids_de_mensajes
from cadabra.workers.broker import broker

log = logging.getLogger(__name__)


@broker.task(task_name="whatsapp.procesar_evento", retry_on_error=True)
async def procesar_evento_whatsapp(evento: dict[str, Any]) -> None:
    # Etapa 4: resolver tenant por phone_number_id, buzón por conversación (orden + debounce),
    # grafo LangGraph, envío y registro de la ejecución. Hoy solo se registra la recepción.
    log.info("evento de WhatsApp recibido", extra={"datos": {"message_ids": ids_de_mensajes(evento)}})
