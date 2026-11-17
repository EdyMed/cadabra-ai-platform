"""Descarte de reintentos de Meta: un message_id se procesa una sola vez."""
from redis.asyncio import Redis

# Prefijo propio: n8n usa "wamid:" en el mismo Redis y, mientras convivan, un mensaje
# reenviado por n8n a la plataforma no debe verse como duplicado.
PREFIJO = "plat:wamid:"


class Dedupe:
    def __init__(self, redis: Redis, ttl_segundos: int) -> None:
        self._redis = redis
        self._ttl = ttl_segundos

    async def es_nuevo(self, message_id: str) -> bool:
        return bool(await self._redis.set(PREFIJO + message_id, 1, nx=True, ex=self._ttl))
