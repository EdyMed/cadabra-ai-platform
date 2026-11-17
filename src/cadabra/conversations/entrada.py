"""Paso 1 del worker: de un evento de Meta a mensajes depositados en el buzón de su conversación.

Eventos de coexistencia (ecos del dueño, historial, contactos de la app WhatsApp Business) se reenvían a n8n.
Por cada mensaje entrante decide si la plataforma lo atiende:
  - ¿el número pertenece a una empresa? (platform.resolver_linea)
  - ¿la línea está en el motor nuevo? (o estamos en modo ensayo)
  - ¿el bot está encendido para este contacto? (bot_activo del CRM y pausa de coexistencia)
  - ¿el contacto no pasó el tope diario de mensajes? (conversations/tope.py)
Si todo da sí, lo deja en el buzón y agenda el turno. Audios, fotos y documentos se convierten antes en texto
(conversations/multimedia.py); cualquier otro tipo (sticker, ubicación, video…) recibe un aviso fijo, como en n8n.
"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import text

from cadabra.conversations import multimedia, tope
from cadabra.conversations.buzon import Buzon, clave_conversacion
from cadabra.core.config import Settings
from cadabra.db.session import sesion_sin_tenant, sesion_tenant
from cadabra.integrations.n8n import ClienteN8n
from cadabra.messaging.whatsapp_api import ClienteWhatsApp

log = logging.getLogger(__name__)

CAMPOS_COEXISTENCIA = {"smb_message_echoes", "history", "smb_app_state_sync", "account_update"}


@dataclass
class Dependencias:
    buzon: Buzon
    redis: Redis
    settings: Settings
    whatsapp: ClienteWhatsApp
    n8n: ClienteN8n
    agendar_turno: Callable[[int, str, str], Awaitable[None]]   # (tenant_id, conversación, message_id)
    leer_medio: Callable[[str, multimedia.Medio], Awaitable[str]]   # (media_id, medio) → texto para el agente


@dataclass(frozen=True)
class MensajeEntrante:
    message_id: str
    phone_number_id: str
    telefono: str
    tipo: str
    texto: str
    media_id: str = ""        # audio / image / document
    caption: str = ""
    filename: str = ""


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
                medio = m.get(m.get("type") or "") if m.get("type") in multimedia.TIPOS else None
                medio = medio if isinstance(medio, dict) else {}
                if m.get("id") and m.get("from") and pnid:
                    mensajes.append(MensajeEntrante(m["id"], pnid, m["from"], m.get("type") or "", texto,
                                                    medio.get("id") or "", medio.get("caption") or "",
                                                    medio.get("filename") or ""))
    return mensajes


def es_de_coexistencia(evento: dict[str, Any]) -> bool:
    return any(c.get("field") in CAMPOS_COEXISTENCIA
               for e in evento.get("entry") or [] for c in e.get("changes") or [])


SQL_LINEA = text("select tenant_id, motor from platform.resolver_linea(cast(:pnid as text))")

# Guarda (bot encendido), rol del contacto y tope diario de la ficha, en una sola ida a la base.
SQL_CONTROL = text("""
    select
      case when exists (select 1 from public.bot_pausas p
                        where p.empresa = cast(:empresa as int) and p.contact_id = cast(:tel as text)
                          and p.hasta > now()) then false
           else coalesce((select l.bot_activo from crm.crm_leads l
                          where l.empresa = cast(:empresa as int)
                            and l.contact_id = nullif(regexp_replace(cast(:tel as text), '[^0-9]', '', 'g'), '')::bigint
                          limit 1), true)
      end as bot_activo,
      coalesce((select c.rol from public.agente_contactos c
                where c.empresa = cast(:empresa as int) and c.phone_number = cast(:tel as text) and c.activo = true
                limit 1), 'anon') as rol,
      (select case when c.config->'limites'->>'mensajes_dia_contacto' ~ '^[0-9]+$'
                   then (c.config->'limites'->>'mensajes_dia_contacto')::int end
       from public.agente_empresas_config c where c.empresa = cast(:empresa as int)) as limite
""")


async def procesar_evento(evento: dict[str, Any], dep: Dependencias) -> None:
    if es_de_coexistencia(evento):
        await dep.n8n.reenviar_coexistencia(evento)   # en ensayo, ClienteN8n solo lo registra
        return

    for m in leer_mensajes(evento):
        async with sesion_sin_tenant() as sesion:
            linea = (await sesion.execute(SQL_LINEA, {"pnid": m.phone_number_id})).first()
        if linea is None:
            log.info("número sin empresa en la plataforma", extra={"datos": {"pnid": m.phone_number_id}})
            continue
        if linea.motor != "codigo" and not dep.settings.modo_ensayo:
            continue  # esta línea la atiende n8n

        if m.tipo not in ("text", "interactive") and m.tipo not in multimedia.TIPOS:
            # n8n: "¿Otros: es mensaje?" → "Enviar aviso (otros)", sin pasar por la guarda ni el tope.
            await dep.whatsapp.enviar_texto(m.phone_number_id, m.telefono, multimedia.AVISO_OTROS)
            log.info("tipo de mensaje no soportado: aviso al cliente", extra={"datos": {"tipo": m.tipo}})
            continue

        async with sesion_tenant(linea.tenant_id) as sesion:
            control = (await sesion.execute(SQL_CONTROL, {"empresa": linea.tenant_id, "tel": m.telefono})).one()
        if control.bot_activo is False:
            log.info("bot apagado para este contacto", extra={"datos": {"telefono": m.telefono}})
            continue

        t = await tope.contar(dep.redis, linea.tenant_id, m.telefono, control.rol, control.limite,
                              dep.settings.zona_horaria)
        if t.excedido:
            if t.avisar:
                await dep.whatsapp.enviar_texto(m.phone_number_id, m.telefono, tope.AVISO)
            log.info("tope diario excedido", extra={"datos": {"telefono": m.telefono, "n": t.n, "limite": t.limite}})
            continue

        texto = m.texto
        if m.tipo in multimedia.TIPOS:   # después de la guarda y el tope: no se paga Whisper/visión de más
            texto = await dep.leer_medio(m.media_id, multimedia.Medio(m.tipo, m.caption, m.filename))

        conversacion = clave_conversacion(linea.tenant_id, m.phone_number_id, m.telefono)
        await dep.buzon.depositar(conversacion, m.message_id, texto)
        await dep.agendar_turno(linea.tenant_id, conversacion, m.message_id)
