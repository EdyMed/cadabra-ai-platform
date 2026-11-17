"""Tope diario de mensajes por contacto (protege del abuso y del gasto en IA). Igual que "Tope:" de n8n:

- cuenta cada mensaje entrante del día (zona Chile) en Redis;
- el dueño no tiene tope;
- al pasar el límite el bot deja de responder ese día, y solo al primer exceso se avisa al contacto.
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

PREFIJO = "plat:tope:"   # n8n usa "tope:": cada motor cuenta lo que atiende
TTL_SEGUNDOS = 93_600    # 26 h
LIMITE_POR_DEFECTO = 100
AVISO = ("Recibimos muchos mensajes seguidos hoy 🙏 Para atenderte mejor, una persona del equipo seguirá esta "
         "conversación.")


@dataclass(frozen=True)
class EstadoTope:
    n: int
    limite: int
    excedido: bool
    avisar: bool


async def contar(redis: Redis, empresa: int, telefono: str, rol: str, limite: int | None, zona: str) -> EstadoTope:
    dia = datetime.now(ZoneInfo(zona)).strftime("%Y-%m-%d")
    clave = f"{PREFIJO}{empresa}:{telefono}:{dia}"
    async with redis.pipeline(transaction=True) as p:
        p.incr(clave)
        p.expire(clave, TTL_SEGUNDOS)
        n, _ = await p.execute()
    limite = limite or LIMITE_POR_DEFECTO
    excedido = rol != "owner" and n > limite
    return EstadoTope(n=n, limite=limite, excedido=excedido, avisar=excedido and n == limite + 1)
