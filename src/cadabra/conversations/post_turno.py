"""Lo que pasa después de cada respuesta del agente, sin depender del modelo (como las ramas paralelas de n8n
que salen de "Guardar turno"):

  dentro de la transacción (base de datos)        después de confirmarla (hacia afuera)
  ─────────────────────────────────────────        ──────────────────────────────────────────────
  interés detectado → guarda/actualiza el lead      corte a humano → alerta a los vendedores (n8n)
  puntaje del lead con IA → guarda el puntaje       agenda completa → evento en Calendar (n8n) + confirmación
                                                    fuera de horario → aviso al cliente

En modo ensayo se calcula todo y queda en el registro de la ejecución, pero no se escribe ni se envía nada.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.agents.contexto import ContextoTurno
from cadabra.conversations import puntaje
from cadabra.conversations.deteccion import ContextoDeteccion, detectar_agenda, detectar_interes
from cadabra.core.config import Settings
from cadabra.integrations.n8n import ClienteN8n
from cadabra.messaging.whatsapp_api import ClienteWhatsApp
from cadabra.tools.crm import guardar_en_crm

log = logging.getLogger(__name__)


@dataclass
class PostTurno:
    interes: dict[str, Any]
    agenda: dict[str, Any]
    puntaje: puntaje.Puntaje | None
    aviso_horario: str | None

    def resumen(self) -> dict[str, Any]:
        """Lo que se guarda en el registro de la ejecución (sirve para comparar con n8n)."""
        return {
            "interes": self.interes,
            "agenda": self.agenda,
            "puntaje": None if self.puntaje is None else {"score": self.puntaje.score,
                                                          "registrar": self.puntaje.registrar,
                                                          "clasificacion": self.puntaje.clasificacion},
            "aviso_horario": self.aviso_horario,
        }


async def en_la_base(sesion: AsyncSession, ctx: ContextoTurno, respuesta: str, settings: Settings) -> PostTurno:
    interes = detectar_interes(ctx.config, ctx.mensaje, ctx.historial, ctx.telefono)
    ahora = datetime.now(ZoneInfo(settings.zona_horaria)).replace(tzinfo=None)
    agenda = detectar_agenda(ContextoDeteccion(ctx.config, ctx.mensaje, ctx.historial, ctx.telefono,
                                               ctx.nombre_asistente, ctx.nombre_empresa), ahora)
    # El puntaje no se calcula para el dueño (igual que "Score: ¿aplica?").
    p = None if ctx.rol == "owner" else await puntaje.clasificar(
        ctx, settings.openai_api_key.get_secret_value(), settings.modelo_puntaje)
    # El aviso de horario solo va si el agente dijo que "coordina" la cita (si no, sonaría fuera de lugar).
    aviso = agenda.get("aviso") if agenda.get("fuera_horario") and "coordin" in (respuesta or "") else None

    if not settings.modo_ensayo:
        if interes["debeRegistrar"]:
            await guardar_en_crm(sesion, ctx.empresa, ctx.telefono, interes)
        if p is not None:
            await puntaje.guardar(sesion, ctx, p, settings.modelo_puntaje)
    return PostTurno(interes, agenda, p, aviso)


async def hacia_afuera(post: PostTurno, ctx: ContextoTurno, n8n: ClienteN8n, whatsapp: ClienteWhatsApp) -> None:
    """Las dos clases de cliente respetan el modo ensayo: en ensayo solo registran."""
    if post.interes["debeRegistrar"] and post.interes["corte"]:
        await n8n.alertar_vendedor(ctx.empresa, ctx.phone_number_id, ctx.telefono,
                                   post.interes.get("nombre") or "", post.interes.get("nombre_negocio") or "")

    if post.agenda.get("agendar"):
        evento = await n8n.crear_evento(post.agenda)
        await whatsapp.enviar_texto(ctx.phone_number_id, ctx.telefono, confirmacion_agenda(post.agenda, evento))
        await n8n.contar_conversacion(ctx.empresa, ctx.telefono)
    elif post.aviso_horario:
        await whatsapp.enviar_texto(ctx.phone_number_id, ctx.telefono, post.aviso_horario)


def confirmacion_agenda(d: dict[str, Any], evento: dict[str, Any] | None) -> str:
    """Mismo texto que "Confirmar agenda (WhatsApp)"; la ficha puede traer su propio mensaje con {tipo} {fecha}…"""
    fecha = "-".join(reversed(d["inicio"][:10].split("-")))
    hora = d["inicio"][11:16]
    if not (evento and (evento.get("id") or evento.get("htmlLink"))):
        return f"Uf, no pude agendar la {d['tipo']} ahora mismo 😕. Un vendedor te contactará para coordinar."
    if d.get("mensaje_ok"):
        return (d["mensaje_ok"].replace("{tipo}", d["tipo"]).replace("{fecha}", fecha).replace("{hora}", hora)
                .replace("{correo}", d.get("correo") or ""))
    return (f"Listo ✅ Te agendé la {d['tipo']} para el {fecha} a las {hora}"
            + (f" ({d['lugar']})" if d.get("lugar") else "") + "."
            + (f" Te llegó la invitación a {d['correo']} 😊" if d.get("correo") else " 😊"))
