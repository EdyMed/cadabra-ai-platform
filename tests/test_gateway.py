import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cadabra.messaging import gateway

SECRETO = "secreto-de-prueba"


class DedupeEnMemoria:
    def __init__(self) -> None:
        self.vistos: set[str] = set()

    async def es_nuevo(self, message_id: str) -> bool:
        if message_id in self.vistos:
            return False
        self.vistos.add(message_id)
        return True


@pytest.fixture
def entorno():
    encolados: list[dict] = []

    async def encolar(evento: dict) -> None:
        encolados.append(evento)

    dedupe = DedupeEnMemoria()
    app = FastAPI()
    app.include_router(gateway.router)
    app.dependency_overrides[gateway.get_dedupe] = lambda: dedupe
    app.dependency_overrides[gateway.get_encolador] = lambda: encolar
    return TestClient(app), encolados


def evento_mensaje(message_id: str) -> bytes:
    return json.dumps({"entry": [{"changes": [{"value": {"messages": [{"id": message_id, "type": "text"}]}}]}]}).encode()


def post(cliente: TestClient, cuerpo: bytes, firma: str | None = None):
    firma = firma if firma is not None else "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()
    return cliente.post("/webhooks/whatsapp", content=cuerpo, headers={"x-hub-signature-256": firma})


def test_firma_invalida_responde_401_y_no_encola(entorno):
    cliente, encolados = entorno
    assert post(cliente, evento_mensaje("wamid.1"), "sha256=" + "0" * 64).status_code == 401
    assert encolados == []


def test_mensaje_valido_se_encola_una_sola_vez(entorno):
    cliente, encolados = entorno
    cuerpo = evento_mensaje("wamid.2")
    assert post(cliente, cuerpo).status_code == 200
    assert post(cliente, cuerpo).status_code == 200  # reintento de Meta
    assert len(encolados) == 1


def test_estado_de_entrega_sin_mensajes_se_encola(entorno):
    cliente, encolados = entorno
    cuerpo = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}).encode()
    assert post(cliente, cuerpo).status_code == 200
    assert len(encolados) == 1


def test_verificacion_get(entorno):
    cliente, _ = entorno
    ok = cliente.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "token-de-prueba", "hub.challenge": "123"})
    assert ok.status_code == 200 and ok.text == "123"
    malo = cliente.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "otro", "hub.challenge": "123"})
    assert malo.status_code == 403
