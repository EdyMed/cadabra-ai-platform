from cadabra.conversations.entrada import leer_mensajes
from cadabra.tools import herramientas_para


def evento(mensaje: dict) -> dict:
    return {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PN"}, "messages": [mensaje]}}]}]}


def test_lee_texto():
    [m] = leer_mensajes(evento({"id": "w1", "from": "569", "type": "text", "text": {"body": "hola"}}))
    assert (m.message_id, m.phone_number_id, m.telefono, m.texto) == ("w1", "PN", "569", "hola")


def test_boton_tocado_llega_como_su_id():
    [m] = leer_mensajes(evento({"id": "w2", "from": "569", "type": "interactive",
                                "interactive": {"button_reply": {"id": "ventas_periodo", "title": "Ventas"}}}))
    assert m.texto == "ventas_periodo"


def test_estados_de_entrega_no_son_mensajes():
    assert leer_mensajes({"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}) == []


def test_herramientas_de_gestion_solo_para_owner():
    gestion = {"ventas_periodo", "top_productos", "saldo_cliente"}
    assert gestion <= {h.nombre for h in herramientas_para("owner")}
    for rol in ("customer", "anon"):
        assert not gestion & {h.nombre for h in herramientas_para(rol)}
