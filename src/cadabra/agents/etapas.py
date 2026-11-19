"""Etapas del embudo (estado_crm) de cada empresa.

Hay 9 etapas FIJAS: de sus nombres dependen las métricas del panel y la derivación ("Requiere Vendedor" corta el
bot y alerta al vendedor). Además, cada cliente puede crear hasta 4 etapas PROPIAS desde el panel (tablero de
Oportunidades → «Etapas»). Se guardan en la ficha: agente_empresas_config.config -> 'etapas', una lista como
    [{"nombre": "Esperando pago", "fija": false, "criterio": "cuando confirma el pedido y dice que transfiere"}, ...]
(panel: app/CRM Whatsap/src/lib/etapas.ts).

El agente puede mover un lead a una etapa propia SOLO si la etapa está visible y tiene criterio: el criterio es la
instrucción del cliente sobre cuándo hacerlo. Sin criterio, la etapa es de uso manual en el panel.
"""
import re
from dataclasses import dataclass
from typing import Any

FIJAS = ("Nuevo Lead", "En Conversación", "Cotización Enviada", "Primer Pedido", "Cliente Activo",
         "Cliente Recurrente", "Sin Respuesta", "Requiere Vendedor", "Inactivo")
MAX_PROPIAS = 4
LARGO_CRITERIO = 300

# Etapas desde las que la detección automática de interés sí puede pasar el lead a "En Conversación".
# Desde cualquier otra (Cotización Enviada, Primer Pedido, una etapa propia…) el lead ya avanzó: no se retrocede.
REACTIVABLES = ("", "Nuevo Lead", "Sin Respuesta", "Inactivo")


@dataclass(frozen=True)
class EtapaPropia:
    nombre: str
    criterio: str


def _una_linea(texto: str, largo: int) -> str:
    """El criterio lo escribe el cliente: una sola línea, sin saltos que puedan simular secciones del prompt."""
    return re.sub(r"\s+", " ", texto).strip()[:largo]


def etapas_propias(config: dict[str, Any]) -> list[EtapaPropia]:
    """Etapas propias que el agente puede usar: visibles, con nombre válido y con criterio (máximo 4)."""
    salida: list[EtapaPropia] = []
    vistas = {f.lower() for f in FIJAS}
    for e in config.get("etapas") or []:
        if not isinstance(e, dict) or e.get("fija") is not False or e.get("oculta"):
            continue
        nombre = _una_linea(str(e.get("nombre") or ""), 40)
        criterio = _una_linea(str(e.get("criterio") or ""), LARGO_CRITERIO)
        if not nombre or not criterio or nombre.lower() in vistas:
            continue
        vistas.add(nombre.lower())
        salida.append(EtapaPropia(nombre, criterio))
        if len(salida) == MAX_PROPIAS:
            break
    return salida


def estado_valido(config: dict[str, Any], estado: str) -> bool:
    """El agente solo puede escribir una etapa fija o una propia habilitada de ESTA empresa."""
    return estado in FIJAS or any(e.nombre == estado for e in etapas_propias(config))


def texto_prompt(config: dict[str, Any]) -> str:
    """Bloque que se agrega al prompt cuando la empresa tiene etapas propias habilitadas ("" si no tiene)."""
    propias = etapas_propias(config)
    if not propias:
        return ""
    lineas = "\n".join(f'- "{e.nombre}" → criterio del negocio: {e.criterio}' for e in propias)
    return (
        "\n\nETAPAS PROPIAS DEL NEGOCIO (además de las estándar): cuando la conversación cumpla el criterio de una de "
        "estas etapas, actualiza el lead con `crm_actualizar_estado` usando estado_crm con el nombre EXACTO. "
        "Nunca uses estas etapas para pasar a un vendedor (para eso sigue siendo 'Requiere Vendedor'), no cambies "
        "bot_activo por ellas y no le menciones al cliente la etapa en que quedó.\n" + lineas
    )
