from cadabra.workers.broker import broker


def test_broker_espera_sin_timeout_de_lectura():
    # BRPOP bloquea hasta que llega un mensaje: un timeout de lectura tumbaría al worker con la cola vacía.
    kwargs = broker.connection_pool.connection_kwargs
    assert kwargs["socket_timeout"] is None
    assert kwargs["socket_keepalive"] is True
