"""mostrar_menu: envía un mensaje con 3 botones (textos y botones salen de la ficha de la empresa)."""
from typing import Literal

from pydantic import BaseModel, Field

from cadabra.tools.base import EntornoHerramienta, Herramienta


class TipoMenu(BaseModel):
    tipo_menu: Literal["owner", "cliente"] = Field(description="owner o cliente")


async def ejecutar(entorno: EntornoHerramienta, args: TipoMenu) -> dict:
    ctx = entorno.ctx
    menu = ctx.perfil.menu
    es_owner = args.tipo_menu == "owner"
    await entorno.whatsapp.enviar_botones(
        phone_number_id=ctx.phone_number_id,
        para=ctx.telefono,
        texto=menu["texto_owner"] if es_owner else menu["texto_cliente"],
        botones=menu["botones_owner"] if es_owner else menu["botones_cliente"],
    )
    return {"ok": True, "enviado": "menú"}


MOSTRAR_MENU = Herramienta(
    nombre="mostrar_menu",
    descripcion=(
        "Muestra un MENÚ con 3 BOTONES inline en WhatsApp (sin popup). Úsala cuando el usuario pida 'menú', "
        "'opciones', o al saludar. Parámetro tipo_menu: 'owner' (botones: Ventas, Buscar producto, Agendar) o "
        "'cliente' (botones: Productos, Precios, Agendar). Tras enviar el menú, NO escribas más texto; el usuario "
        "tocará un botón."
    ),
    argumentos=TipoMenu,
    ejecutar=ejecutar,
)
