"""Lectura del payload de webhooks de WhatsApp Cloud API."""
from typing import Any


def ids_de_mensajes(evento: dict[str, Any]) -> list[str]:
    """message_id de los mensajes entrantes del evento (los estados de entrega no traen)."""
    ids: list[str] = []
    for entrada in evento.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            for mensaje in (cambio.get("value") or {}).get("messages") or []:
                if mensaje.get("id"):
                    ids.append(str(mensaje["id"]))
    return ids
