"""API HTTP: gateway de webhooks (data plane) y, más adelante, la API /v1 del control plane."""
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis
from redis.exceptions import RedisError

from cadabra.core.config import get_settings
from cadabra.core.logging import configurar_logs
from cadabra.messaging import gateway


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    from cadabra.workers.broker import broker

    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url.get_secret_value())
    await broker.startup()
    try:
        yield
    finally:
        await broker.shutdown()
        await app.state.redis.aclose()


def create_app() -> FastAPI:
    configurar_logs(get_settings().log_level)
    app = FastAPI(title="Cadabra AI Platform", version="0.1.0", lifespan=lifespan)
    app.include_router(gateway.router)

    @app.get("/healthz", tags=["operación"])
    async def healthz() -> dict[str, object]:
        """Lo revisa el health check de n8n cada 15 min.

        worker = hay un worker vivo (latido en Redis). modo_ensayo = el del WORKER (es quien responde); si no hay
        worker vivo, se informa el de la API.
        """
        ajustes = get_settings()
        latido = None
        try:
            redis_ok = bool(await app.state.redis.ping())
            latido = await app.state.redis.get("plat:worker:latido")
        except (RedisError, OSError):
            redis_ok = False
        try:
            modo_worker = json.loads(latido)["modo_ensayo"] if latido else None
        except (ValueError, KeyError, TypeError):
            modo_worker = None   # latido de una versión anterior ("1")
        worker_ok = latido is not None
        return {"estado": "ok" if redis_ok and worker_ok else "degradado", "redis": redis_ok, "worker": worker_ok,
                "modo_ensayo": ajustes.modo_ensayo if modo_worker is None else modo_worker,
                "puerta_entrada": ajustes.puerta_entrada}

    return app


app = create_app()
