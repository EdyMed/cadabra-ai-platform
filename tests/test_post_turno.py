import fakeredis.aioredis

from cadabra.conversations import tope
from cadabra.conversations.entrada import es_de_coexistencia
from cadabra.conversations.post_turno import confirmacion_agenda
from cadabra.conversations.puntaje import calcular


async def test_tope_diario():
    r = fakeredis.aioredis.FakeRedis()
    estados = [await tope.contar(r, 1, "569", "anon", 2, "America/Santiago") for _ in range(4)]
    assert [(e.excedido, e.avisar) for e in estados] == [(False, False), (False, False), (True, True), (True, False)]
    dueno = [await tope.contar(r, 1, "569owner", "owner", 1, "America/Santiago") for _ in range(3)]
    assert not any(e.excedido for e in dueno)


def test_puntaje_con_los_pesos_de_n8n():
    p = calcular({"intencion": "compra", "categoria": "Empanadas", "cantidad": "200", "es_negocio": True,
                  "urgencia": "alta", "pide_humano": True})
    assert p.score == 100 and p.registrar                       # 40+10+15+15+15+5 = 100
    p = calcular({"intencion": "saludo_o_charla", "categoria": None, "cantidad": None, "es_negocio": False,
                  "urgencia": "sin_dato", "pide_humano": False})
    assert p.score == 0 and not p.registrar
    assert calcular({"intencion": "cotizacion", "categoria": None, "cantidad": "3 docenas", "urgencia": "media"}).score == 58


def test_confirmacion_de_agenda():
    d = {"inicio": "2026-11-20T11:30:00", "tipo": "visita", "lugar": "Oficina", "correo": "a@b.cl", "mensaje_ok": ""}
    assert confirmacion_agenda(d, {"id": "x"}) == ("Listo ✅ Te agendé la visita para el 20-11-2026 a las 11:30 "
                                                   "(Oficina). Te llegó la invitación a a@b.cl 😊")
    assert confirmacion_agenda(d, None).startswith("Uf, no pude agendar la visita")
    propio = {**d, "mensaje_ok": "{tipo} el {fecha} {hora} → {correo}"}
    assert confirmacion_agenda(propio, {"htmlLink": "u"}) == "visita el 20-11-2026 11:30 → a@b.cl"


def test_eventos_de_coexistencia_se_reconocen():
    assert es_de_coexistencia({"entry": [{"changes": [{"field": "smb_message_echoes", "value": {}}]}]})
    assert not es_de_coexistencia({"entry": [{"changes": [{"field": "messages", "value": {}}]}]})
