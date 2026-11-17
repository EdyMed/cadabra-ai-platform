"""Gateway de webhooks de Meta: valida la firma, decide el motor, descarta duplicados, encola y responde rápido.

Con CADABRA_PUERTA_ENTRADA=true, los eventos de líneas que siguen en n8n se le reenvían tal cual
(messaging/ruteo.py). Todo el trabajo pesado (tenant, agente, envío) ocurre en los workers.
"""
import hmac
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import PlainTextResponse

from cadabra.core.config import Settings, get_settings
from cadabra.core.meta_firma import firma_valida
from cadabra.messaging.dedupe import Dedupe
from cadabra.messaging.meta_eventos import ids_de_mensajes
from cadabra.messaging.ruteo import Ruteo, reenviar_a_n8n

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp"])

Encolador = Callable[[dict[str, Any]], Awaitable[None]]
Reenviador = Callable[[bytes, str], Awaitable[bool]]


def get_dedupe(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> Dedupe:
    return Dedupe(request.app.state.redis, settings.dedupe_ttl_segundos)


def get_encolador() -> Encolador:
    from cadabra.workers.tareas import procesar_evento_whatsapp

    async def encolar(evento: dict[str, Any]) -> None:
        await procesar_evento_whatsapp.kiq(evento)

    return encolar


def get_ruteo(request: Request) -> Ruteo:
    if not hasattr(request.app.state, "ruteo"):
        request.app.state.ruteo = Ruteo()
    return request.app.state.ruteo


def get_reenviador(settings: Annotated[Settings, Depends(get_settings)]) -> Reenviador:
    async def reenviar(cuerpo: bytes, firma: str) -> bool:
        return await reenviar_a_n8n(settings.n8n_url, cuerpo, firma)

    return reenviar


@router.get("")
def verificar(
    settings: Annotated[Settings, Depends(get_settings)],
    modo: Annotated[str, Query(alias="hub.mode")] = "",
    token: Annotated[str, Query(alias="hub.verify_token")] = "",
    desafio: Annotated[str, Query(alias="hub.challenge")] = "",
) -> Response:
    esperado = settings.meta_verify_token.get_secret_value()
    if modo == "subscribe" and esperado and hmac.compare_digest(token, esperado):
        return PlainTextResponse(desafio)
    return Response(status_code=403)


@router.post("")
async def recibir(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    dedupe: Annotated[Dedupe, Depends(get_dedupe)],
    encolar: Annotated[Encolador, Depends(get_encolador)],
    ruteo: Annotated[Ruteo, Depends(get_ruteo)],
    reenviar: Annotated[Reenviador, Depends(get_reenviador)],
) -> Response:
    cuerpo = await request.body()
    firma = request.headers.get("x-hub-signature-256")
    if not firma_valida(cuerpo, firma, settings.meta_app_secret.get_secret_value()):
        log.warning("webhook con firma inválida")
        return Response(status_code=401)
    try:
        evento = json.loads(cuerpo)
    except json.JSONDecodeError:
        return Response(status_code=400)

    if settings.puerta_entrada and await ruteo.destino(evento) == "n8n":
        # n8n valida la firma y descarta duplicados por su cuenta. Si no responde, 502 → Meta reintenta.
        return Response(status_code=200 if await reenviar(cuerpo, firma or "") else 502)

    ids = ids_de_mensajes(evento)
    nuevos = [i for i in ids if await dedupe.es_nuevo(i)]
    if ids and not nuevos:
        log.info("webhook duplicado descartado", extra={"datos": {"message_ids": ids}})
        return Response(status_code=200)

    await encolar(evento)
    return Response(status_code=200)
