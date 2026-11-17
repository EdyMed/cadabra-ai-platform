"""Contrato común de las herramientas del agente.

Una herramienta es: nombre + descripción (lo que lee el modelo) + argumentos tipados (Pydantic) + una función
`ejecutar`. Además declara quién puede usarla y si escribe datos. Este archivo la convierte en una herramienta
de LangChain aplicando, en un solo lugar, el modo ensayo, el registro y el manejo de errores.
"""
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from cadabra.agents.contexto import ContextoTurno
from cadabra.messaging.whatsapp_api import ClienteWhatsApp

log = logging.getLogger(__name__)


@dataclass
class EntornoHerramienta:
    """Lo que una herramienta tiene a mano durante el turno."""
    ctx: ContextoTurno
    sesion: AsyncSession          # transacción con el tenant del turno fijado (RLS)
    whatsapp: ClienteWhatsApp
    ensayo: bool


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    argumentos: type[BaseModel]
    ejecutar: Callable[[EntornoHerramienta, Any], Awaitable[Any]]
    solo_owner: bool = False      # se entrega al modelo solo si el rol del contacto es owner
    escribe: bool = False         # en modo ensayo no se ejecuta: devuelve un resultado simulado


def _a_json(valor: Any) -> Any:
    """Decimal y fechas de Postgres a tipos que el modelo puede leer."""
    if isinstance(valor, Decimal):
        return int(valor) if valor == valor.to_integral_value() else float(valor)
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    if isinstance(valor, dict):
        return {k: _a_json(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_a_json(v) for v in valor]
    return valor


def a_langchain(h: Herramienta, entorno: EntornoHerramienta, llamadas: list[dict[str, Any]]) -> StructuredTool:
    """Herramienta de LangChain lista para el grafo. `llamadas` acumula lo ejecutado (registro del turno)."""

    async def correr(**kwargs: Any) -> str:
        args = h.argumentos(**kwargs)
        registro: dict[str, Any] = {"herramienta": h.nombre, "argumentos": args.model_dump()}
        try:
            if h.escribe and entorno.ensayo:
                resultado: Any = {"ok": True, "ensayo": True, "nota": "modo ensayo: no se escribió nada"}
            else:
                resultado = _a_json(await h.ejecutar(entorno, args))
        except Exception as e:
            log.exception("falla en herramienta %s", h.nombre)
            resultado = {"error": f"No se pudo ejecutar {h.nombre}. Responde sin inventar datos."}
            registro["excepcion"] = repr(e)
        registro["resultado"] = resultado
        llamadas.append(registro)
        return json.dumps(resultado, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=correr, name=h.nombre, description=h.descripcion, args_schema=h.argumentos
    )
