"""Alta de líneas de WhatsApp en la plataforma (control plane). La llama el panel al terminar el Embedded Signup.

POST /v1/lineas  (encabezado X-Cadabra-Admin = CADABRA_ADMIN_CLAVE)
  1. registra la empresa (platform.tenants) y la línea (platform.lineas) con el motor pedido
     (por defecto CADABRA_MOTOR_LINEAS_NUEVAS); las otras líneas de la empresa vuelven a 'n8n'
     (en el panel, una empresa = una línea activa)
  2. motor 'codigo' → le pone a la línea su webhook propio en Meta apuntando a la plataforma
     (lo mismo que hace scripts/linea_webhook.ps1 -Accion activar, pero automático)
  3. si algo impide que la plataforma responda (worker caído o en modo ensayo, Meta rechaza el webhook porque el
     usuario del sistema no tiene acceso a la WABA del cliente) la línea queda en 'n8n', que sigue respondiendo,
     y se devuelve el motivo en `aviso`. Nunca deja una línea sin quien responda.

Coexistencia no necesita nada especial: los ecos del dueño, el historial y los contactos llegan a la plataforma
y conversations/entrada.py los reenvía al workflow de coexistencia de n8n (que pausa el bot cuando el dueño
contesta desde su celular).
"""
import hmac
import json
import logging
from typing import Annotated, Literal, Protocol

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text

from cadabra.core.config import Settings, get_settings
from cadabra.db.session import sesion_tenant

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/lineas", tags=["administración"])

LATIDO = "plat:worker:latido"
# Versión probada con la dirección propia por número (la misma de scripts/linea_webhook.ps1).
GRAPH_WEBHOOK = "v23.0"

SQL_TENANT = text("""
    insert into platform.tenants (id, nombre) values (:empresa, :nombre)
    on conflict (id) do update set nombre = excluded.nombre, actualizado_en = now()
""")
SQL_LINEA = text("""
    insert into platform.lineas (phone_number_id, tenant_id, motor) values (:pnid, :empresa, :motor)
    on conflict (phone_number_id) do update set tenant_id = excluded.tenant_id, motor = excluded.motor,
                                                actualizado_en = now()
""")
SQL_OTRAS_A_N8N = text("""
    update platform.lineas set motor = 'n8n', actualizado_en = now()
    where tenant_id = :empresa and phone_number_id <> :pnid and motor <> 'n8n'
""")
SQL_MOTOR = text("""
    update platform.lineas set motor = :motor, actualizado_en = now()
    where tenant_id = :empresa and phone_number_id = :pnid
""")

Motor = Literal["codigo", "n8n"]


class AltaLinea(BaseModel):
    empresa: int = Field(gt=0)
    phone_number_id: str = Field(pattern=r"^\d{5,30}$")
    nombre_empresa: str = Field(min_length=1, max_length=200)
    motor: Motor | None = None          # None = CADABRA_MOTOR_LINEAS_NUEVAS


class ResultadoAlta(BaseModel):
    empresa: int
    phone_number_id: str
    motor: Motor                        # el que quedó de verdad
    webhook: Literal["plataforma", "n8n"]
    aviso: str | None = None


# ── Piezas reemplazables en las pruebas ──────────────────────────────────────────────────────────────────────

class Registro(Protocol):
    async def guardar(self, alta: AltaLinea, motor: Motor) -> None: ...
    async def fijar_motor(self, empresa: int, pnid: str, motor: Motor) -> None: ...


class WebhookMeta(Protocol):
    async def apuntar(self, pnid: str, url: str, verify_token: str) -> None: ...
    async def quitar(self, pnid: str) -> None: ...


class RegistroSql:
    async def guardar(self, alta: AltaLinea, motor: Motor) -> None:
        async with sesion_tenant(alta.empresa) as s:
            await s.execute(SQL_TENANT, {"empresa": alta.empresa, "nombre": alta.nombre_empresa})
            await s.execute(SQL_LINEA, {"pnid": alta.phone_number_id, "empresa": alta.empresa, "motor": motor})
            await s.execute(SQL_OTRAS_A_N8N, {"empresa": alta.empresa, "pnid": alta.phone_number_id})

    async def fijar_motor(self, empresa: int, pnid: str, motor: Motor) -> None:
        async with sesion_tenant(empresa) as s:
            await s.execute(SQL_MOTOR, {"empresa": empresa, "pnid": pnid, "motor": motor})


class WebhookMetaGraph:
    """Dirección propia (override) del número en Meta. Prioridad: número > WABA > app (n8n)."""

    def __init__(self, token: str) -> None:
        self._token = token

    async def _post(self, pnid: str, configuracion: dict[str, str]) -> None:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post(f"https://graph.facebook.com/{GRAPH_WEBHOOK}/{pnid}",
                                json={"webhook_configuration": configuracion},
                                headers={"Authorization": f"Bearer {self._token}"})
        if not r.is_success:
            try:
                detalle = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                detalle = r.text[:200]
            raise RuntimeError(f"Meta rechazó el webhook de la línea ({r.status_code}): {detalle}")

    async def apuntar(self, pnid: str, url: str, verify_token: str) -> None:
        await self._post(pnid, {"override_callback_uri": url, "verify_token": verify_token})

    async def quitar(self, pnid: str) -> None:
        await self._post(pnid, {"override_callback_uri": ""})


def get_registro() -> Registro:
    return RegistroSql()


def get_webhook_meta(settings: Annotated[Settings, Depends(get_settings)]) -> WebhookMeta:
    return WebhookMetaGraph(settings.meta_token.get_secret_value())


def autorizar(settings: Annotated[Settings, Depends(get_settings)],
              clave: Annotated[str, Header(alias="X-Cadabra-Admin")] = "") -> None:
    esperada = settings.admin_clave.get_secret_value()
    if not esperada:
        raise HTTPException(503, "Alta de líneas deshabilitada: falta CADABRA_ADMIN_CLAVE")
    if not hmac.compare_digest(clave, esperada):
        raise HTTPException(401)


async def motivo_para_no_responder(redis: Redis, settings: Settings) -> str | None:
    """None si la plataforma puede atender una línea ya; si no, el motivo (se queda en n8n)."""
    if not settings.meta_token.get_secret_value() or not settings.meta_verify_token.get_secret_value():
        return "falta CADABRA_META_TOKEN o CADABRA_META_VERIFY_TOKEN en plataforma-api"
    try:
        latido = await redis.get(LATIDO)
    except (RedisError, OSError):
        return "no se pudo leer el estado del worker (Redis)"
    if latido is None:
        return "no hay un worker vivo"
    try:
        ensayo = json.loads(latido)["modo_ensayo"]
    except (ValueError, KeyError, TypeError):
        ensayo = settings.modo_ensayo
    return "el worker está en modo ensayo (no respondería)" if ensayo else None


# ── Endpoint ─────────────────────────────────────────────────────────────────────────────────────────────────

@router.post("", dependencies=[Depends(autorizar)])
async def alta_linea(
    alta: AltaLinea,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    registro: Annotated[Registro, Depends(get_registro)],
    meta: Annotated[WebhookMeta, Depends(get_webhook_meta)],
) -> ResultadoAlta:
    """Registra la línea de una empresa y, si va al motor de código, le pone su webhook propio en Meta."""
    pedido: Motor = alta.motor or settings.motor_lineas_nuevas
    aviso = None
    if pedido == "codigo":
        aviso = await motivo_para_no_responder(request.app.state.redis, settings)
    motor: Motor = "codigo" if pedido == "codigo" and aviso is None else "n8n"

    # Primero la base: cuando Meta empiece a mandar a la plataforma, la línea ya debe estar registrada.
    await registro.guardar(alta, motor)

    if motor == "codigo":
        url = f"{settings.url_publica.rstrip('/')}/webhooks/whatsapp"
        try:
            await meta.apuntar(alta.phone_number_id, url, settings.meta_verify_token.get_secret_value())
        except Exception as e:  # noqa: BLE001 — cualquier falla deja la línea en n8n, que sí responde
            aviso = str(e)
            motor = "n8n"
            await registro.fijar_motor(alta.empresa, alta.phone_number_id, "n8n")
    else:
        try:   # una reconexión de una línea que estaba en la plataforma: sin dirección propia vuelve a n8n
            await meta.quitar(alta.phone_number_id)
        except Exception as e:  # noqa: BLE001 — no impide el alta
            log.warning("no se pudo quitar el webhook propio de la línea", extra={"datos": {"error": str(e)}})

    log.info("alta de línea", extra={"datos": {"empresa": alta.empresa, "pnid": alta.phone_number_id,
                                               "pedido": pedido, "motor": motor, "aviso": aviso}})
    return ResultadoAlta(empresa=alta.empresa, phone_number_id=alta.phone_number_id, motor=motor,
                         webhook="plataforma" if motor == "codigo" else "n8n", aviso=aviso)
