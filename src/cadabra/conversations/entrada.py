"""Paso 1 del worker: de un evento de Meta a mensajes depositados en el buzón de su conversación.

Por cada mensaje entrante decide si la plataforma lo atiende:
  - ¿el número pertenece a una empresa? (platform.resolver_linea)
  - ¿la línea está en el motor nuevo? (o estamos en modo ensayo)
  - ¿el bot está encendido para este contacto? (bot_activo del CRM y pausa de coexistencia)
Si todo da sí, lo deja en el buzón y agenda el turno.
"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from cadabra.conversations.buzon import Buzon, clave_conversacion
from cadabra.core.config import Settings
from cadabra.db.session import sesion_sin_tenant, sesion_tenant

log = logging.getLogger(__name__)

AgendarTurno = Callable[[int, str, str], Awaitable[None]]   # (tenant_id, conversación, message_id)


@dataclass(frozen=True)
class MensajeEntrante:
    message_id: str
    phone_number_id: str
    telefono: str
    tipo: str
    texto: str


def leer_mensajes(evento: dict[str, Any]) -> list[MensajeEntrante]:
    """Texto, o el id/título del botón tocado (igual que "Extraer campos" de n8n)."""
    mensajes = []
    for entrada in evento.get("entry") or []:
        for cambio in entrada.get("changes") or []:
            valor = cambio.get("value") or {}
            pnid = (valor.get("metadata") or {}).get("phone_number_id")
            for m in valor.get("messages") or []:
                texto = (m.get("text") or {}).get("body") or ""
                if m.get("type") == "interactive":
                    i = m.get("interactive") or {}
                    texto = ((i.get("button_reply") or {}).get("id") or (i.get("list_reply") or {}).get("id")
                             or (i.get("button_reply") or {}).get("title") or (i.get("list_reply") or {}).get("title")
                             or "")
                if m.get("id") and m.get("from") and pnid:
                    mensajes.append(MensajeEntrante(m["id"], pnid, m["from"], m.get("type") or "", texto))
    return mensajes


SQL_LINEA = text("select tenant_id, motor from platform.resolver_linea(cast(:pnid as text))")

SQL_BOT_ACTIVO = text("""
    select case
             when exists (select 1 from public.bot_pausas p
                          where p.empresa = cast(:empresa as int) and p.contact_id = cast(:tel as text)
                            and p.hasta > now()) then false
             else coalesce((select l.bot_activo from crm.crm_leads l
                            where l.empresa = cast(:empresa as int)
                              and l.contact_id = nullif(regexp_replace(cast(:tel as text), '[^0-9]', '', 'g'), '')::bigint
                            limit 1), true)
           end
""")


async def procesar_evento(evento: dict[str, Any], buzon: Buzon, settings: Settings, agendar: AgendarTurno) -> None:
    for m in leer_mensajes(evento):
        if m.tipo not in ("text", "interactive"):
            log.info("tipo de mensaje aún no soportado por la plataforma", extra={"datos": {"tipo": m.tipo}})
            continue

        async with sesion_sin_tenant() as sesion:
            linea = (await sesion.execute(SQL_LINEA, {"pnid": m.phone_number_id})).first()
        if linea is None:
            log.info("número sin empresa en la plataforma", extra={"datos": {"pnid": m.phone_number_id}})
            continue
        if linea.motor != "codigo" and not settings.modo_ensayo:
            continue  # esta línea la atiende n8n

        async with sesion_tenant(linea.tenant_id) as sesion:
            activo = (await sesion.execute(SQL_BOT_ACTIVO, {"empresa": linea.tenant_id, "tel": m.telefono})).scalar()
        if activo is False:
            log.info("bot apagado para este contacto", extra={"datos": {"telefono": m.telefono}})
            continue

        conversacion = clave_conversacion(linea.tenant_id, m.phone_number_id, m.telefono)
        await buzon.depositar(conversacion, m.message_id, m.texto)
        await agendar(linea.tenant_id, conversacion, m.message_id)
