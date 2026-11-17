import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cadabra.core.config import Settings, get_settings
from cadabra.messaging import gateway
from cadabra.messaging.ruteo import numeros_del_evento

SECRETO = "secreto-de-prueba"


class DedupeEnMemoria:
    def __init__(self) -> None:
        self.vistos: set[str] = set()

    async def es_nuevo(self, message_id: str) -> bool:
        if message_id in self.vistos:
            return False
        self.vistos.add(message_id)
        return True


class RuteoFijo:
    """Línea '1' en código; cualquier otra en n8n."""
    async def destino(self, evento: dict) -> str:
        return "plataforma" if "1" in numeros_del_evento(evento) else "n8n"


def _app(puerta: bool, n8n_ok: bool = True):
    encolados: list[dict] = []
    reenviados: list[tuple[bytes, str]] = []

    async def encolar(evento: dict) -> None:
        encolados.append(evento)

    async def reenviar(cuerpo: bytes, firma: str) -> bool:
        reenviados.append((cuerpo, firma))
        return n8n_ok

    dedupe = DedupeEnMemoria()
    app = FastAPI()
    app.include_router(gateway.router)
    app.dependency_overrides[gateway.get_dedupe] = lambda: dedupe
    app.dependency_overrides[gateway.get_encolador] = lambda: encolar
    app.dependency_overrides[gateway.get_ruteo] = RuteoFijo
    app.dependency_overrides[gateway.get_reenviador] = lambda: reenviar
    app.dependency_overrides[get_settings] = lambda: Settings(meta_app_secret=SECRETO,
                                                              meta_verify_token="token-de-prueba",
                                                              puerta_entrada=puerta)
    return TestClient(app), encolados, reenviados


@pytest.fixture
def entorno():
    cliente, encolados, _ = _app(puerta=False)
    return cliente, encolados


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


def evento_de_linea(pnid: str, message_id: str) -> bytes:
    return json.dumps({"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": pnid},
                                                         "messages": [{"id": message_id, "type": "text"}]}}]}]}).encode()


def test_puerta_reenvia_a_n8n_el_cuerpo_y_la_firma_originales():
    cliente, encolados, reenviados = _app(puerta=True)
    cuerpo = evento_de_linea("2", "wamid.n8n")
    r = post(cliente, cuerpo)
    assert r.status_code == 200 and encolados == []
    assert reenviados == [(cuerpo, "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest())]


def test_puerta_linea_en_codigo_la_atiende_la_plataforma():
    cliente, encolados, reenviados = _app(puerta=True)
    assert post(cliente, evento_de_linea("1", "wamid.cod")).status_code == 200
    assert len(encolados) == 1 and reenviados == []


def test_puerta_si_n8n_falla_meta_debe_reintentar():
    cliente, _, _ = _app(puerta=True, n8n_ok=False)
    assert post(cliente, evento_de_linea("2", "wamid.caido")).status_code == 502


def test_puerta_firma_invalida_no_se_reenvia():
    cliente, _, reenviados = _app(puerta=True)
    assert post(cliente, evento_de_linea("2", "wamid.x"), "sha256=" + "0" * 64).status_code == 401
    assert reenviados == []


def test_sin_puerta_todo_va_a_la_plataforma():
    cliente, encolados, reenviados = _app(puerta=False)
    assert post(cliente, evento_de_linea("2", "wamid.sp")).status_code == 200
    assert len(encolados) == 1 and reenviados == []
