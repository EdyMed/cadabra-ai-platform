"""POST /v1/lineas: alta de líneas desde el panel. Nunca deja una línea sin quien responda."""
import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from cadabra.administration import lineas
from cadabra.api import main
from cadabra.core.config import Settings, get_settings

CLAVE = "clave-admin"
ALTA = {"empresa": 7, "phone_number_id": "123456789012345", "nombre_empresa": "Lanantü SPA"}


class RegistroFalso:
    def __init__(self):
        self.motores: dict[str, str] = {}

    async def guardar(self, alta, motor):
        self.motores[alta.phone_number_id] = motor

    async def fijar_motor(self, empresa, pnid, motor):
        self.motores[pnid] = motor


class MetaFalsa:
    def __init__(self, falla=False):
        self.falla, self.apuntadas, self.quitadas = falla, [], []

    async def apuntar(self, pnid, url, verify_token):
        if self.falla:
            raise RuntimeError("Meta rechazó el webhook de la línea (403): sin permiso")
        self.apuntadas.append((pnid, url, verify_token))

    async def quitar(self, pnid):
        self.quitadas.append(pnid)


@pytest.fixture
def entorno():
    def armar(*, clave=CLAVE, ensayo=False, worker=True, meta_falla=False, motor_nuevas="codigo"):
        app = main.create_app()
        servidor = fakeredis.FakeServer()
        redis = fakeredis.FakeAsyncRedis(server=servidor)
        app.state.redis = redis
        ajustes = Settings(admin_clave=clave, meta_token="tok", meta_verify_token="verif",
                           motor_lineas_nuevas=motor_nuevas, modo_ensayo=True)
        registro, meta = RegistroFalso(), MetaFalsa(meta_falla)
        app.dependency_overrides[get_settings] = lambda: ajustes
        app.dependency_overrides[lineas.get_registro] = lambda: registro
        app.dependency_overrides[lineas.get_webhook_meta] = lambda: meta
        if worker:
            fakeredis.FakeRedis(server=servidor).set(lineas.LATIDO, json.dumps({"modo_ensayo": ensayo}))
        return TestClient(app), registro, meta
    return armar


def _post(cliente, cuerpo=ALTA, clave=CLAVE):
    return cliente.post("/v1/lineas", json=cuerpo, headers={"X-Cadabra-Admin": clave})


def test_sin_clave_configurada_no_opera(entorno):
    c, _, _ = entorno(clave="")
    assert _post(c).status_code == 503


def test_clave_incorrecta(entorno):
    c, registro, _ = entorno()
    assert _post(c, clave="otra").status_code == 401
    assert registro.motores == {}


def test_linea_nueva_queda_en_la_plataforma_con_su_webhook(entorno):
    c, registro, meta = entorno()
    r = _post(c).json()
    assert (r["motor"], r["webhook"], r["aviso"]) == ("codigo", "plataforma", None)
    assert registro.motores == {ALTA["phone_number_id"]: "codigo"}
    assert meta.apuntadas == [(ALTA["phone_number_id"], "https://plataforma.appcadabra.cl/webhooks/whatsapp", "verif")]


def test_si_meta_rechaza_el_webhook_la_linea_vuelve_a_n8n(entorno):
    c, registro, _ = entorno(meta_falla=True)
    r = _post(c).json()
    assert (r["motor"], r["webhook"]) == ("n8n", "n8n")
    assert "sin permiso" in r["aviso"]
    assert registro.motores[ALTA["phone_number_id"]] == "n8n"


def test_worker_en_ensayo_deja_la_linea_en_n8n(entorno):
    c, registro, meta = entorno(ensayo=True)
    r = _post(c).json()
    assert r["motor"] == "n8n" and "ensayo" in r["aviso"]
    assert meta.apuntadas == [] and registro.motores[ALTA["phone_number_id"]] == "n8n"


def test_sin_worker_deja_la_linea_en_n8n(entorno):
    c, _, meta = entorno(worker=False)
    r = _post(c).json()
    assert r["motor"] == "n8n" and "worker" in r["aviso"] and meta.apuntadas == []


def test_motor_n8n_quita_el_webhook_propio(entorno):
    c, _, meta = entorno(motor_nuevas="n8n")
    r = _post(c).json()
    assert (r["motor"], r["aviso"]) == ("n8n", None)
    assert meta.quitadas == [ALTA["phone_number_id"]] and meta.apuntadas == []


def test_valida_el_phone_number_id(entorno):
    c, _, _ = entorno()
    assert _post(c, {**ALTA, "phone_number_id": "abc"}).status_code == 422
