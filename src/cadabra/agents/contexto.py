"""Contexto de un turno: quién escribe, a qué empresa, qué sabe el CRM y qué se habló antes.

Mismas consultas que los nodos "Resolver empresa", "Resolver rol" y "Recuperar historial" de n8n. Se ejecutan
dentro de `sesion_tenant`, así que RLS limita todo a la empresa del turno.
"""
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.agents.perfil import Perfil, construir_perfil, negocio_configurado

HISTORIAL_TURNOS = 10


@dataclass
class ContextoTurno:
    empresa: int
    nombre_empresa: str
    nombre_asistente: str
    config: dict[str, Any]
    perfil: Perfil
    telefono: str                  # wa_id del contacto
    phone_number_id: str           # número del negocio
    mensaje: str                   # texto del turno (mensajes agrupados)
    rol: str = "anon"              # owner | customer | anon
    rut_cliente: str | None = None
    lead: dict[str, Any] | None = None
    historial: list[dict[str, str]] = field(default_factory=list)

    @property
    def configurado(self) -> bool:
        return negocio_configurado(self.config)

    def historial_texto(self) -> str:
        if not self.historial:
            return "(sin historial previo)"
        return "\n".join(f"{h['role']}: {h['content']}" for h in self.historial)


SQL_EMPRESA = text("""
    select l.empresa, l.nombre_empresa, l.nombre_asistente, coalesce(c.config, '{}'::jsonb) as config
    from public.agente_lineas_whatsapp l
    left join public.agente_empresas_config c on c.empresa = l.empresa
    where l.phone_number_id = cast(:pnid as text) and l.activo = true
    limit 1
""")

SQL_ROL_Y_LEAD = text("""
    select c.rol, c.rut_cliente,
           l.id as lead_id, l.nombre, l.nombre_negocio as negocio, l.producto_interes as producto,
           l.estado_crm as estado, l.comuna, l.vendedor_asignado as vendedor,
           l.estado_agendamiento as agenda, to_char(l.fecha_agendamiento, 'YYYY-MM-DD') as fecha_cita,
           to_char(l.hora_cita, 'HH24:MI') as hora_cita,
           to_char(l.created_at at time zone 'America/Santiago', 'YYYY-MM-DD') as desde
    from (select 1) d
    left join public.agente_contactos c on c.empresa = cast(:empresa as int) and c.phone_number = cast(:tel as text) and c.activo = true
    left join crm.crm_leads l
           on l.empresa = cast(:empresa as int) and l.contact_id = nullif(regexp_replace(cast(:tel as text), '[^0-9]', '', 'g'), '')::bigint
    limit 1
""")

SQL_HISTORIAL = text("""
    select role, content from public.conversation_history
    where empresa = cast(:empresa as int) and phone_number = cast(:tel as text)
    order by created_at desc
    limit cast(:n as int)
""")


async def cargar_contexto(
    sesion: AsyncSession, phone_number_id: str, telefono: str, mensaje: str
) -> ContextoTurno | None:
    """None si el número no pertenece a ninguna empresa activa."""
    fila = (await sesion.execute(SQL_EMPRESA, {"pnid": phone_number_id})).mappings().first()
    if fila is None:
        return None

    empresa = fila["empresa"]
    nombre_empresa = fila["nombre_empresa"] or "la empresa"
    nombre_asistente = fila["nombre_asistente"] or "Asistente"
    config = fila["config"] or {}

    rol = (await sesion.execute(SQL_ROL_Y_LEAD, {"empresa": empresa, "tel": telefono})).mappings().first() or {}
    lead = dict(rol) if rol.get("lead_id") else None

    filas = (await sesion.execute(SQL_HISTORIAL, {"empresa": empresa, "tel": telefono, "n": HISTORIAL_TURNOS})).all()
    historial = [{"role": r.role, "content": r.content} for r in reversed(filas) if r.role and r.content]

    return ContextoTurno(
        empresa=empresa,
        nombre_empresa=nombre_empresa,
        nombre_asistente=nombre_asistente,
        config=config,
        perfil=construir_perfil(config, nombre_asistente, nombre_empresa),
        telefono=telefono,
        phone_number_id=phone_number_id,
        mensaje=mensaje,
        rol=rol.get("rol") or "anon",
        rut_cliente=rol.get("rut_cliente"),
        lead=lead,
        historial=historial,
    )
