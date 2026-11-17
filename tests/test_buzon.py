import fakeredis.aioredis
import pytest

from cadabra.conversations.buzon import Buzon, clave_conversacion


@pytest.fixture
def buzon():
    return Buzon(fakeredis.aioredis.FakeRedis())


async def test_agrupa_mensajes_y_solo_el_ultimo_procesa(buzon):
    conv = clave_conversacion(1, "pn", "569")
    await buzon.depositar(conv, "m1", "hola")
    await buzon.depositar(conv, "m2", "quiero empanadas")
    assert not await buzon.es_el_ultimo(conv, "m1")
    assert await buzon.es_el_ultimo(conv, "m2")
    assert await buzon.vaciar(conv) == ["hola", "quiero empanadas"]
    assert await buzon.vaciar(conv) == []


async def test_candado_un_turno_a_la_vez(buzon):
    conv = clave_conversacion(1, "pn", "569")
    token = await buzon.tomar_candado(conv)
    assert token is not None
    assert await buzon.tomar_candado(conv) is None
    await buzon.soltar_candado(conv, "otro-token")       # un token ajeno no lo libera
    assert await buzon.tomar_candado(conv) is None
    await buzon.soltar_candado(conv, token)
    assert await buzon.tomar_candado(conv) is not None


async def test_conversaciones_de_empresas_distintas_no_se_mezclan(buzon):
    await buzon.depositar(clave_conversacion(1, "pn", "569"), "a", "empresa 1")
    await buzon.depositar(clave_conversacion(3, "pn", "569"), "b", "empresa 3")
    assert await buzon.vaciar(clave_conversacion(1, "pn", "569")) == ["empresa 1"]
