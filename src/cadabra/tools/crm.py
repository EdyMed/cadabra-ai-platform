"""Herramientas del CRM (crm.crm_leads). Siempre actúan sobre el lead de ESTA conversación y ESTA empresa.

En n8n, crm_guardar_lead llamaba al webhook "CRM Upsert" y crm_actualizar_estado actualizaba por record_id sin
filtrar empresa. Aquí ambas hacen el mismo upsert directo y quedan limitadas al contacto del turno.
"""
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.tools.base import EntornoHerramienta, Herramienta

ESTADOS = ("Nuevo Lead, En Conversación, Cotización Enviada, Primer Pedido, Cliente Activo, Cliente Recurrente, "
           "Sin Respuesta, Requiere Vendedor, Inactivo")


class DatosLead(BaseModel):
    nombre: str | None = Field(default=None, description="nombre de la persona SOLO si lo dijo en la conversación")
    nombre_negocio: str | None = Field(default=None, description="nombre del local/negocio")
    producto_interes: str | None = Field(
        default=None, description="categoría de interés del negocio (ver instrucciones) u Otro"
    )
    estado_crm: str | None = Field(default=None, description="estado del embudo, valor exacto con tildes")
    comuna: str | None = Field(default=None, description="comuna del cliente")


class CambioEstado(BaseModel):
    nombre: str | None = Field(default=None, description="nombre de la persona de contacto")
    nombre_negocio: str | None = Field(default=None, description="nombre del local/negocio")
    estado_crm: str | None = Field(default=None, description="nuevo estado del embudo, valor exacto")
    vendedor_asignado: str | None = Field(default=None, description="Vendedor 1 / Vendedor 2")
    condicion_pago: str | None = Field(default=None, description="Efectivo/Cheque/Crédito 7d")
    estado_agendamiento: str | None = Field(default=None, description="Pendiente/Confirmado/Cancelado")
    bot_activo: bool | None = Field(
        default=None, description="true o false: pon false SOLO para pasar la conversación a un humano/vendedor"
    )
    record_id: int | None = Field(default=None, description="Id numérico del lead (de crm_guardar_lead)")


SQL_BUSCAR = text("select id from crm.crm_leads where empresa = :empresa and contact_id = :contacto limit 1")

# Únicas columnas que la plataforma puede escribir en un lead (los nombres van al SQL: lista fija).
COLUMNAS = ("nombre", "nombre_negocio", "producto_interes", "estado_crm", "comuna", "origen_lead",
            "vendedor_asignado", "condicion_pago", "estado_agendamiento", "bot_activo")


async def guardar_en_crm(sesion: AsyncSession, empresa: int, telefono: str, campos: dict[str, Any]) -> dict[str, Any]:
    """Actualiza el lead del contacto o lo crea si no existe. Solo escribe columnas permitidas y con valor.

    Lo usan las herramientas del agente y la detección automática de interés (conversations/post_turno.py).
    """
    contacto = int(re.sub(r"\D", "", telefono))
    campos = {k: v for k, v in campos.items() if k in COLUMNAS and v is not None and v != ""}
    existente = (await sesion.execute(SQL_BUSCAR, {"empresa": empresa, "contacto": contacto})).scalar()

    if existente is not None:
        if campos:
            asignaciones = ", ".join(f"{k} = :{k}" for k in campos)
            await sesion.execute(
                text(f"update crm.crm_leads set {asignaciones} where id = :id and empresa = :empresa"),
                {**campos, "id": existente, "empresa": empresa},
            )
        return {"record_id": existente, "accion": "actualizado"}

    nuevo = {"estado_crm": "Nuevo Lead", "origen_lead": "whatsapp", **campos,
             "empresa": empresa, "contact_id": contacto, "phone": contacto}   # phone es bigint en crm_leads
    columnas = ", ".join(nuevo)
    valores = ", ".join(f":{k}" for k in nuevo)
    creado = await sesion.execute(text(f"insert into crm.crm_leads ({columnas}) values ({valores}) returning id"), nuevo)
    return {"record_id": creado.scalar_one(), "accion": "creado"}


async def upsert_lead(entorno: EntornoHerramienta, campos: dict[str, Any]) -> dict[str, Any]:
    """El lead de ESTA conversación y ESTA empresa: el modelo no puede elegir otro."""
    return await guardar_en_crm(entorno.sesion, entorno.ctx.empresa, entorno.ctx.telefono, campos)


async def guardar_lead(entorno: EntornoHerramienta, args: DatosLead) -> dict[str, Any]:
    campos = args.model_dump()
    campos["estado_crm"] = campos["estado_crm"] or "En Conversación"
    return await upsert_lead(entorno, campos)


async def actualizar_estado(entorno: EntornoHerramienta, args: CambioEstado) -> dict[str, Any]:
    # record_id se acepta por compatibilidad con el prompt, pero no decide qué lead se toca.
    return await upsert_lead(entorno, args.model_dump(exclude={"record_id"}))


CRM_GUARDAR_LEAD = Herramienta(
    nombre="crm_guardar_lead",
    descripcion=(
        "Registra o actualiza al LEAD/cliente en el CRM sin duplicar (busca por su número). Úsala al conversar con un "
        "cliente con interés real. Clasifica producto_interes (una de las categorías válidas del negocio indicadas en "
        f"tus instrucciones, u Otro) y estado_crm con VALOR EXACTO con tildes ({ESTADOS}). El contact_id/phone se "
        "toman solos del contexto. Devuelve record_id (úsalo en crm_actualizar_estado)."
    ),
    argumentos=DatosLead,
    ejecutar=guardar_lead,
    escribe=True,
)

CRM_ACTUALIZAR_ESTADO = Herramienta(
    nombre="crm_actualizar_estado",
    descripcion=(
        "Actualiza datos del lead de esta conversación: nombre, nombre_negocio, estado_crm (valor exacto), "
        "vendedor_asignado, condicion_pago, estado_agendamiento y bot_activo (false SOLO para pasar a un vendedor)."
    ),
    argumentos=CambioEstado,
    ejecutar=actualizar_estado,
    escribe=True,
)
