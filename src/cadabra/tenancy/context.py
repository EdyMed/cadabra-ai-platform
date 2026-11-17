"""Contexto de ejecución: tenant y ejecución en curso.

El tenant SIEMPRE lo resuelve el servidor (p. ej. desde el phone_number_id de Meta),
nunca se toma de un dato enviado por el cliente.
"""
from contextvars import ContextVar

_tenant_id: ContextVar[int | None] = ContextVar("tenant_id", default=None)
_execution_id: ContextVar[str | None] = ContextVar("execution_id", default=None)


def tenant_id_actual() -> int | None:
    return _tenant_id.get()


def execution_id_actual() -> str | None:
    return _execution_id.get()


def fijar_tenant(tenant_id: int) -> None:
    _tenant_id.set(tenant_id)


def fijar_ejecucion(execution_id: str) -> None:
    _execution_id.set(execution_id)
