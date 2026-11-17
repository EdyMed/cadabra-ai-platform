"""/healthz: el modo ensayo que informa es el del worker (el que responde), no el de la API."""
import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from cadabra.api import main
from cadabra.core.config import Settings


@pytest.fixture
def cliente(monkeypatch):
    app = main.create_app()
    redis = fakeredis.FakeAsyncRedis()
    app.state.redis = redis
    monkeypatch.setattr(main, "get_settings", lambda: Settings(modo_ensayo=True))
    return TestClient(app), redis


def _get(cliente):
    # Sin "with": no corre el lifespan (no hay broker real en las pruebas).
    return cliente.get("/healthz").json()


async def test_sin_worker_esta_degradado(cliente):
    c, _ = cliente
    r = _get(c)
    assert (r["estado"], r["worker"], r["modo_ensayo"]) == ("degradado", False, True)


async def test_modo_ensayo_viene_del_worker(cliente):
    c, redis = cliente
    await redis.set("plat:worker:latido", json.dumps({"modo_ensayo": False}))
    r = _get(c)
    assert (r["estado"], r["worker"], r["modo_ensayo"]) == ("ok", True, False)


async def test_latido_antiguo_usa_el_modo_de_la_api(cliente):
    c, redis = cliente
    await redis.set("plat:worker:latido", "1")
    assert _get(c)["modo_ensayo"] is True


