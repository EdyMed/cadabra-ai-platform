"""API HTTP: gateway de webhooks (data plane) y, más adelante, la API /v1 del control plane."""
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
        """Lo revisa el health check de n8n cada 15 min. worker = hay un worker vivo (latido en Redis)."""
        try:
            redis_ok = bool(await app.state.redis.ping())
            worker_ok = bool(await app.state.redis.exists("plat:worker:latido"))
        except (RedisError, OSError):
            redis_ok = worker_ok = False
        ajustes = get_settings()
        return {"estado": "ok" if redis_ok and worker_ok else "degradado", "redis": redis_ok, "worker": worker_ok,
                "modo_ensayo": ajustes.modo_ensayo, "puerta_entrada": ajustes.puerta_entrada}

    return app


app = create_app()
