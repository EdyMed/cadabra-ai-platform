import hashlib
import hmac
import json

from cadabra.core.meta_firma import firma_valida

SECRETO = "secreto-de-prueba"


def firmar(cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(SECRETO.encode(), cuerpo, hashlib.sha256).hexdigest()


def test_firma_correcta_sobre_unicode_escapado():
    # Meta envía el JSON con unicode escapado (\u00f1) y firma esos bytes exactos.
    cuerpo = json.dumps({"texto": "ñandú"}).encode()
    assert firma_valida(cuerpo, firmar(cuerpo), SECRETO)


def test_firma_de_otro_cuerpo_es_rechazada():
    cuerpo = b'{"a":1}'
    assert not firma_valida(b'{"a":2}', firmar(cuerpo), SECRETO)


def test_sin_cabecera_o_sin_secreto_es_rechazada():
    cuerpo = b"{}"
    assert not firma_valida(cuerpo, None, SECRETO)
    assert not firma_valida(cuerpo, "abc", SECRETO)
    assert not firma_valida(cuerpo, firmar(cuerpo), "")


def test_gateway_sin_secreto_configurado_rechaza_todo():
    from cadabra.core.config import Settings

    s = Settings(_env_file=None, meta_app_secret="", meta_verify_token="")
    assert not firma_valida(b"{}", firmar(b"{}"), s.meta_app_secret.get_secret_value())
