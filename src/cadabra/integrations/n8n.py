"""Integraciones que siguen viviendo en n8n, llamadas por webhook (ADR-0001: n8n queda para integraciones).

  alerta-vendedor       avisa por WhatsApp a los vendedores activos de la empresa       (workflow existente)
  contar-conversacion   suma la conversación al contador del plan y avisa al 80 %       (workflow existente)
  plataforma-agenda     crea el evento en Google Calendar con la credencial de n8n      (workflow para la plataforma)
  coexistencia-eventos  ecos del dueño, historial y contactos de la app WhatsApp Business (workflow existente)

En modo ensayo no se llama a n8n: las llamadas quedan registradas en `self.llamadas` y en el log.
"""
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class ClienteN8n:
    def __init__(self, url: str, clave: str, ensayo: bool = True) -> None:
        self._url = url.rstrip("/")
        self._clave = clave
        self.ensayo = ensayo
        self.llamadas: list[dict[str, Any]] = []

    async def alertar_vendedor(self, empresa: int, phone_number_id: str, telefono: str, nombre: str,
                               negocio: str) -> None:
        await self._post("alerta-vendedor", {"wa_id": telefono, "nombre": nombre or "", "negocio": negocio or "",
                                             "empresa": empresa, "phone_number_id": phone_number_id})

    async def contar_conversacion(self, empresa: int, telefono: str) -> None:
        await self._post("contar-conversacion", {"empresa": empresa, "wa_id": telefono})

    async def crear_evento(self, agenda: dict[str, Any]) -> dict[str, Any] | None:
        """Datos del evento creado ({id, htmlLink}) o None si no se pudo."""
        return await self._post("plataforma-agenda", {k: agenda[k] for k in (
            "calendar_id", "inicio", "fin", "titulo", "descripcion", "attendees", "lugar")}, con_clave=True)

    async def reenviar_coexistencia(self, evento: dict[str, Any]) -> None:
        await self._post("coexistencia-eventos", evento, con_clave=True)

    async def _post(self, ruta: str, cuerpo: dict[str, Any], con_clave: bool = False) -> dict[str, Any] | None:
        self.llamadas.append({"webhook": ruta, "cuerpo": cuerpo})
        if self.ensayo:
            log.info("ensayo: webhook de n8n NO llamado", extra={"datos": {"webhook": ruta}})
            return None
        try:
            async with httpx.AsyncClient(timeout=20) as http:
                r = await http.post(f"{self._url}/webhook/{ruta}", json=cuerpo,
                                    headers={"X-Cadabra-Clave": self._clave} if con_clave else {})
                r.raise_for_status()
                return r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else {}
        except (httpx.HTTPError, ValueError):
            log.exception("falla llamando a n8n", extra={"datos": {"webhook": ruta}})
            return None
