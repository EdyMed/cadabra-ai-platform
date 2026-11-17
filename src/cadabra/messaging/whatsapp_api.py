"""Salida hacia WhatsApp Cloud API (Graph API de Meta).

En modo ensayo no se llama a Meta: los envíos quedan en `self.enviados` y en el log, para revisarlos o
compararlos con n8n.
"""
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ClienteWhatsApp:
    def __init__(self, token: str, version: str = "v21.0", ensayo: bool = True,
                 http: httpx.AsyncClient | None = None) -> None:
        self._token = token
        self._base = f"https://graph.facebook.com/{version}"
        self.ensayo = ensayo
        self._http = http
        self.enviados: list[dict[str, Any]] = []

    async def enviar_texto(self, phone_number_id: str, para: str, texto: str) -> None:
        await self._enviar(phone_number_id, {
            "messaging_product": "whatsapp", "to": para, "type": "text", "text": {"body": texto},
        })

    async def enviar_botones(self, phone_number_id: str, para: str, texto: str, botones: list[dict[str, str]]) -> None:
        await self._enviar(phone_number_id, {
            "messaging_product": "whatsapp", "to": para, "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": texto},
                "action": {"buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": str(b["title"])[:20]}} for b in botones[:3]
                ]},
            },
        })

    async def _enviar(self, phone_number_id: str, cuerpo: dict[str, Any]) -> None:
        self.enviados.append(cuerpo)
        if self.ensayo:
            log.info("ensayo: mensaje NO enviado a WhatsApp", extra={"datos": {"para": cuerpo["to"], "mensaje": cuerpo}})
            return
        http = self._http or httpx.AsyncClient(timeout=15)
        try:
            r = await http.post(
                f"{self._base}/{phone_number_id}/messages",
                json=cuerpo,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            r.raise_for_status()
        finally:
            if self._http is None:
                await http.aclose()
