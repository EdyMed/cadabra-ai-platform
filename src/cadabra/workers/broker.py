"""Broker de Taskiq sobre Redis (ADR-0003). Lo usan la API (encolar) y los workers (procesar)."""
from taskiq import SimpleRetryMiddleware
from taskiq_redis import ListQueueBroker

from cadabra.core.config import get_settings

broker = ListQueueBroker(
    url=get_settings().redis_url.get_secret_value(),
    queue_name="plat:cola:eventos",
).with_middlewares(SimpleRetryMiddleware(default_retry_count=3))
