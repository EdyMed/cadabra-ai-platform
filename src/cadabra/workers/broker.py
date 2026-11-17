"""Broker de Taskiq sobre Redis (ADR-0003). Lo usan la API (encolar) y los workers (procesar)."""
from taskiq import SimpleRetryMiddleware
from taskiq_redis import ListQueueBroker

from cadabra.core.config import get_settings

broker = ListQueueBroker(
    url=get_settings().redis_url.get_secret_value(),
    queue_name="plat:cola:eventos",
    # El worker espera mensajes con BRPOP sin límite de tiempo. redis-py 8 corta cualquier lectura a los
    # 5 s por defecto: sin esto el worker se cae y reinicia cada vez que la cola queda vacía 5 s.
    socket_timeout=None,
    socket_keepalive=True,
    health_check_interval=30,
).with_middlewares(SimpleRetryMiddleware(default_retry_count=3))
