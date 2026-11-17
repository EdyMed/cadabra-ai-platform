"""Compara, mensaje a mensaje, la respuesta de la plataforma (modo ensayo) con la de n8n.

Por cada mensaje: lo envía firmado a la plataforma, espera su ejecución, luego lo envía a n8n y lee la salida del
nodo "AI Agent". La plataforma va primero porque en ensayo no escribe historial: así ambos ven el mismo historial.
Ojo: n8n SÍ escribe historial y puede crear un lead para el número usado (usar un número ficticio).

Uso: .venv/Scripts/python scripts/comparar_con_n8n.py <app_secret> <n8n_api_key> <telefono> "mensaje 1" "mensaje 2" ...
"""
import asyncio
import datetime as dt
import hashlib
import hmac
import json
import sys
import time
import urllib.request

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from cadabra.core.config import get_settings

PLATAFORMA = "https://plataforma.appcadabra.cl/webhooks/whatsapp"
N8N = "https://appcadabra-cadabra-project.jmyxxj.easypanel.host"
WORKFLOW = "LspLEGA3ZegcYoIH"
PNID, EMPRESA = "1168256669712210", 1


def evento(tel: str, mid: str, texto: str) -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "0", "changes": [{
        "field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "56985677759", "phone_number_id": PNID},
            "contacts": [{"profile": {"name": "Prueba"}, "wa_id": tel}],
            "messages": [{"from": tel, "id": mid, "timestamp": str(int(time.time())), "type": "text",
                          "text": {"body": texto}}]}}]}]}, ensure_ascii=False).encode()


def enviar(url: str, cuerpo: bytes, secreto: str) -> int:
    firma = "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()
    req = urllib.request.Request(url, data=cuerpo, headers={
        "Content-Type": "application/json", "X-Hub-Signature-256": firma, "User-Agent": "cadabra-comparacion"})
    return urllib.request.urlopen(req, timeout=30).status


def get_n8n(ruta: str, clave: str) -> dict:
    req = urllib.request.Request(N8N + ruta, headers={"X-N8N-API-KEY": clave})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


async def respuesta_plataforma(conexion, desde: dt.datetime) -> tuple[str, list[str], int] | None:
    for _ in range(40):
        await conexion.execute(text("select set_config('app.tenant_id', :t, false)"), {"t": str(EMPRESA)})
        fila = (await conexion.execute(text(
            "select id, latencia_ms from platform.agent_executions where iniciado_en >= :d order by iniciado_en limit 1"
        ), {"d": desde})).first()
        if fila:
            eventos = (await conexion.execute(text(
                "select tipo, nombre, salida from platform.execution_events where execution_id = :i order by id"
            ), {"i": fila.id})).all()
            herramientas = [e.nombre for e in eventos if e.tipo == "herramienta" and e.nombre != "post_turno"]
            final = next((e.salida.get("respuesta", "") for e in eventos if e.tipo == "llm"), "")
            post = next((e.salida for e in eventos if e.nombre == "post_turno"), None)
            return final, herramientas, fila.latencia_ms, post
        await conexion.rollback()
        await asyncio.sleep(2)
    return None


def respuesta_n8n(clave: str, desde: dt.datetime) -> tuple[str, list[str]] | None:
    for _ in range(40):
        datos = get_n8n(f"/api/v1/executions?workflowId={WORKFLOW}&limit=5&includeData=true", clave)["data"]
        for e in datos:
            if dt.datetime.fromisoformat(e["startedAt"].replace("Z", "+00:00")) < desde or not e.get("stoppedAt"):
                continue
            run = ((e.get("data") or {}).get("resultData") or {}).get("runData") or {}
            if "AI Agent" in run:
                salida = run["AI Agent"][0]["data"]["main"][0][0]["json"].get("output", "")
                herramientas = [n for n in run if n in {
                    "stock_producto", "ventas_periodo", "top_productos", "saldo_cliente", "mostrar_menu",
                    "crm_guardar_lead", "crm_actualizar_estado"}]
                post = {n: run[n][0]["data"]["main"][0][0]["json"] for n in run
                        if (n.startswith("Detectar") or n == "Score: calcular")
                        and run[n][0].get("data", {}).get("main", [[None]])[0]}
                return salida, herramientas, post
        time.sleep(3)
    return None


async def main() -> None:
    secreto, clave_n8n, tel, *mensajes = sys.argv[1:]
    engine = create_async_engine(get_settings().database_url.get_secret_value())
    async with engine.connect() as conexion:
        for i, texto in enumerate(mensajes, 1):
            mid = f"wamid.COMPARA_{int(time.time())}_{i}"
            t = dt.datetime.now(dt.UTC)
            enviar(PLATAFORMA, evento(tel, mid + "_P", texto), secreto)
            p = await respuesta_plataforma(conexion, t)
            t = dt.datetime.now(dt.UTC)
            enviar(N8N + "/webhook/whatsapp-agent", evento(tel, mid + "_N", texto), secreto)
            n = respuesta_n8n(clave_n8n, t)
            print(f"\n### {i}. «{texto}»")
            print(f"PLATAFORMA {('(' + str(p[2]) + ' ms, herramientas: ' + ', '.join(p[1]) + ')') if p else ''}:")
            print("  " + (p[0] if p else "SIN RESPUESTA"))
            print(f"N8N {('(herramientas: ' + ', '.join(n[1]) + ')') if n else ''}:")
            print("  " + (n[0] if n else "SIN RESPUESTA"))
            if p:
                print("POST PLATAFORMA: " + json.dumps(p[3], ensure_ascii=False, default=str)[:900])
            if n:
                print("POST N8N: " + json.dumps(n[2], ensure_ascii=False, default=str)[:900])
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
