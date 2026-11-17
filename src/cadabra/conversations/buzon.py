"""Buzón por conversación en Redis: agrupa mensajes seguidos y garantiza que un turno se procese de a uno.

Reemplaza al "Buffer" de n8n (lista en Redis + nodo Wait de 8 s), pero sin dejar ejecuciones bloqueadas:

1. Cada mensaje se deposita en la lista de su conversación y queda marcado como "el último".
2. Su tarea espera unos segundos. Si al despertar ya no es el último, termina: otro mensaje más nuevo
   procesará el lote completo.
3. El último toma el candado de la conversación, vacía la lista y procesa todo como un solo turno.
"""
import secrets

from redis.asyncio import Redis

PREFIJO = "plat:buzon:"
TTL_SEGUNDOS = 3600


def clave_conversacion(tenant_id: int, phone_number_id: str, telefono: str) -> str:
    return f"{tenant_id}:{phone_number_id}:{telefono}"


class Buzon:
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def depositar(self, conversacion: str, message_id: str, texto: str) -> None:
        base = PREFIJO + conversacion
        async with self._r.pipeline(transaction=True) as p:
            p.rpush(base + ":mensajes", texto)
            p.expire(base + ":mensajes", TTL_SEGUNDOS)
            p.set(base + ":ultimo", message_id, ex=TTL_SEGUNDOS)
            await p.execute()

    async def es_el_ultimo(self, conversacion: str, message_id: str) -> bool:
        ultimo = await self._r.get(PREFIJO + conversacion + ":ultimo")
        return ultimo is not None and _texto(ultimo) == message_id

    async def vaciar(self, conversacion: str) -> list[str]:
        """Devuelve los mensajes acumulados (en orden de llegada) y deja la lista vacía."""
        clave = PREFIJO + conversacion + ":mensajes"
        async with self._r.pipeline(transaction=True) as p:
            p.lrange(clave, 0, -1)
            p.delete(clave)
            mensajes, _ = await p.execute()
        return [_texto(m) for m in mensajes]

    async def tomar_candado(self, conversacion: str, segundos: int = 120) -> str | None:
        """Token del candado si se obtuvo; None si otro turno de esta conversación está en curso."""
        token = secrets.token_hex(8)
        ok = await self._r.set(PREFIJO + conversacion + ":candado", token, nx=True, ex=segundos)
        return token if ok else None

    async def soltar_candado(self, conversacion: str, token: str) -> None:
        clave = PREFIJO + conversacion + ":candado"
        if _texto(await self._r.get(clave) or b"") == token:
            await self._r.delete(clave)


def _texto(valor: bytes | str) -> str:
    return valor.decode() if isinstance(valor, bytes) else valor
