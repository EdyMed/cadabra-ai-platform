"""Puerta de entrada: decide qué motor atiende cada evento de Meta, según la línea (platform.lineas.motor).

  motor = 'codigo'          → lo atiende la plataforma (cola → workers)
  motor = 'n8n' o sin línea → se reenvía a n8n TAL CUAL (mismo cuerpo, misma firma), y n8n sigue igual que hoy

Cambiar una línea de motor = un UPDATE en platform.lineas; aplica en menos de CACHE_SEGUNDOS.
Solo se usa con CADABRA_PUERTA_ENTRADA=true, es decir, cuando el webhook de Meta apunta a la plataforma.
"""
import logging
import time
from typing import Any

import httpx
from sqlalchemy import text

from cadabra.db.session import sesion_sin_tenant

log = logging.getLogger(__name__)

CACHE_SEGUNDOS = 30
SQL_MOTOR = text("select motor from platform.resolver_linea(cast(:pnid as text))")


def numeros_del_evento(evento: dict[str, Any]) -> set[str]:
    return {pnid for e in evento.get("entry") or [] for c in e.get("changes") or []
            if (pnid := ((c.get("value") or {}).get("metadata") or {}).get("phone_number_id"))}


class Ruteo:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, str | None]] = {}

    async def _motor(self, pnid: str) -> str | None:
        ahora = time.monotonic()
        guardado = self._cache.get(pnid)
        if guardado and ahora - guardado[0] < CACHE_SEGUNDOS:
            return guardado[1]
        async with sesion_sin_tenant() as sesion:
            motor = (await sesion.execute(SQL_MOTOR, {"pnid": pnid})).scalar()
        self._cache[pnid] = (ahora, motor)
        return motor

    async def destino(self, evento: dict[str, Any]) -> str:
        """'plataforma' si alguna línea del evento está en código; si no, 'n8n' (incluye eventos sin número)."""
        for pnid in numeros_del_evento(evento):
            if await self._motor(pnid) == "codigo":
                return "plataforma"
        return "n8n"


async def reenviar_a_n8n(url_n8n: str, cuerpo: bytes, firma: str) -> bool:
    """Reenvía el webhook original a n8n. False si n8n no respondió 2xx (la plataforma le dirá a Meta que reintente)."""
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(f"{url_n8n.rstrip('/')}/webhook/whatsapp-agent", content=cuerpo,
                                headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma})
        if r.is_success:
            return True
        log.error("n8n rechazó el reenvío", extra={"datos": {"status": r.status_code}})
    except httpx.HTTPError:
        log.exception("no se pudo reenviar a n8n")
    return False
