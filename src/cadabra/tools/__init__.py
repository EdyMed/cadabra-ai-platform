"""Registro de herramientas del agente: agregar una herramienta nueva = crearla en su archivo y sumarla aquí."""
from cadabra.tools.base import Herramienta
from cadabra.tools.catalogo import STOCK_PRODUCTO
from cadabra.tools.crm import CRM_ACTUALIZAR_ESTADO, CRM_GUARDAR_LEAD
from cadabra.tools.gestion import SALDO_CLIENTE, TOP_PRODUCTOS, VENTAS_PERIODO
from cadabra.tools.menu import MOSTRAR_MENU

HERRAMIENTAS: list[Herramienta] = [
    STOCK_PRODUCTO,
    VENTAS_PERIODO,
    TOP_PRODUCTOS,
    SALDO_CLIENTE,
    MOSTRAR_MENU,
    CRM_GUARDAR_LEAD,
    CRM_ACTUALIZAR_ESTADO,
]


def herramientas_para(rol: str) -> list[Herramienta]:
    """Las de gestión (ventas, ranking, deudas) solo llegan al modelo si el contacto es owner."""
    return [h for h in HERRAMIENTAS if rol == "owner" or not h.solo_owner]
