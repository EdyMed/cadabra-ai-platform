"""Paridad con n8n: el perfil que arma Python debe ser IDÉNTICO al del nodo "Consolidar contexto".

Ejecuta el JavaScript original de n8n con Node (si está instalado) sobre las fichas reales de las empresas y
sobre fichas sintéticas que recorren todas las ramas, y compara texto a texto.
"""
import json
import os
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.perfil import construir_perfil, ficha_cliente, negocio_configurado
from cadabra.conversations.deteccion import ContextoDeteccion, detectar_agenda, detectar_interes

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"

SINTETICAS = [
    {},
    {"agenda": {"activa": False}},
    {
        "tono": {"trato": "usted", "emojis": "🙂"},
        "agenda": {"tipo": "visita", "dias": [1, 3], "hora_inicio": "09:00", "hora_fin": "18:00", "duracion_min": 30,
                   "anticipacion_horas": 24, "lugar": "Oficina", "pide_correo": False},
        "negocio": {"descripcion": "vendemos X para {empresa}", "horario": "L-V", "pagos": "transferencia",
                    "no_prometer": "plazos"},
        "faq": [{"p": "¿envían?", "r": "sí"}, {"p": "incompleta"}],
        "catalogo": {"unidad": "caja", "sinonimos": [{"dice": "chela", "buscar": "cerveza"}],
                     "categorias_menu": "A y B"},
        "interes": {"categorias": [{"nombre": "A"}, {"nombre": "B"}]},
        "menu": {"texto_owner": "Hola jefe", "botones_cliente": [{"id": "a", "title": "A"}]},
        "escalamiento": "deriva con {asistente}",
        "fuentes": {"catalogo": {"tipo": "google_sheets"}},
        "configurado": True,
    },
    {"tono": {"texto": "Tono propio de {asistente}"}, "catalogo": {"texto": "Catálogo propio de {empresa}"},
     "configurado": False, "negocio": {"descripcion": "algo"}},
]
LEAD = {"nombre": "Pedro", "negocio": "Almacén", "producto": "Empanadas", "estado": "Cotización Enviada",
        "comuna": None, "vendedor": "", "fecha_cita": "2026-11-20", "hora_cita": "10:00", "agenda": "Pendiente",
        "desde": "2026-10-01"}
HISTORIAL_DESC = [{"role": "assistant", "content": "¿Con quién tengo el gusto?"}, {"role": "user", "content": "hola"}]


def casos() -> list[dict]:
    reales = json.loads((FIXTURES / "fichas_reales.json").read_text(encoding="utf-8"))
    base = [{"empresa": f["empresa"], "nombre_empresa": f["nombre_empresa"], "nombre_asistente": f["nombre_asistente"],
             "config": f["config"]} for f in reales]
    base += [{"empresa": 9, "nombre_empresa": "Empresa X", "nombre_asistente": "Ana", "config": c} for c in SINTETICAS]
    con_lead = [{**c, "lead": LEAD, "historial_desc": HISTORIAL_DESC} for c in base]
    return base + con_lead


@pytest.mark.skipif(shutil.which("node") is None, reason="se necesita Node para ejecutar el código de n8n")
def test_perfil_identico_a_n8n(tmp_path):
    lista = casos()
    archivo = tmp_path / "casos.json"
    archivo.write_text(json.dumps(lista, ensure_ascii=False), encoding="utf-8")
    salida = subprocess.run(
        ["node", str(FIXTURES / "ejecutar_n8n.js"), str(RAIZ / "scripts/n8n/consolidar_contexto_n8n.js"), str(archivo)],
        capture_output=True, check=True,
    )
    esperado = json.loads(salida.stdout.decode("utf-8"))

    for caso, n8n in zip(lista, esperado, strict=True):
        perfil = asdict(construir_perfil(caso["config"], caso["nombre_asistente"], caso["nombre_empresa"]))
        perfil_n8n = dict(n8n["perfil"])
        perfil_n8n.pop("calendar_id")  # la agenda en Calendar queda en n8n por ahora
        assert perfil == perfil_n8n, f"empresa {caso['empresa']}"
        assert ficha_cliente(caso.get("lead")) == n8n["ficha_cliente"]
        assert negocio_configurado(caso["config"]) == n8n["negocio_configurado"]

        historial = [dict(h) for h in reversed(caso.get("historial_desc") or [])]
        ctx = ContextoTurno(empresa=1, nombre_empresa="", nombre_asistente="", config={}, perfil=None,  # type: ignore[arg-type]
                            telefono="", phone_number_id="", mensaje="", historial=historial)
        assert ctx.historial_texto() == n8n["history_text"]


# ---- Detectar interés / Detectar agenda (nodos Code de n8n) ---------------------------------------------------

def _node(codigo: str, casos_json: list[dict], tmp_path) -> list[dict]:
    archivo = tmp_path / "casos_nodo.json"
    archivo.write_text(json.dumps(casos_json, ensure_ascii=False), encoding="utf-8")
    salida = subprocess.run(
        ["node", str(FIXTURES / "ejecutar_nodo_n8n.js"), str(RAIZ / "scripts/n8n" / codigo), str(archivo)],
        capture_output=True, check=True, env={**os.environ, "TZ": "UTC"},   # el servidor de n8n corre en UTC
    )
    return json.loads(salida.stdout.decode("utf-8"))


CONFIG_PAN = json.loads((FIXTURES / "fichas_reales.json").read_text(encoding="utf-8"))[0]["config"]
PIDIO_NOMBRE = [{"role": "user", "content": "quiero hablar con un vendedor"},
                {"role": "assistant", "content": "Dale, te paso con un vendedor 🙌 ¿A nombre de quién lo anoto?"}]
CASOS_INTERES = [
    (CONFIG_PAN, "cuánto vale la empanada de pino?", []),
    (CONFIG_PAN, "hola", []),
    (CONFIG_PAN, "quiero hablar con un vendedor", []),
    (CONFIG_PAN, "soy Pedro, local los tres cerditos", PIDIO_NOMBRE),
    (CONFIG_PAN, "edy", PIDIO_NOMBRE),
    (CONFIG_PAN, "mi negocio es Almacén Don Pepe", PIDIO_NOMBRE),
    (CONFIG_PAN, "me llamo maría de la paz", PIDIO_NOMBRE),
    ({}, "necesito cotizar 200 unidades", []),
    ({"interes": {"senales": "(arriendo|visita)"}}, "quiero una visita", []),
    ({"interes": {"categorias": [{"nombre": "Bad", "regex": "("}]}}, "precio", []),
]
AHORA = ["2026-11-17T15:00:00Z", "2026-11-21T02:30:00Z"]   # martes 12:00 Chile · viernes 23:30 Chile
AGENDA = {"tipo": "visita", "dias": [1, 2, 3, 4, 5], "hora_inicio": "09:00", "hora_fin": "18:00", "duracion_min": 30,
          "anticipacion_horas": 2, "correo_negocio": "ventas@x.cl", "lugar": "Oficina"}
CASOS_AGENDA = [
    ({}, "quiero agendar una reunión mañana a las 10 con pedro@x.cl", []),
    ({}, "hola, precios", []),
    ({"agenda": {"activa": False}}, "agendar mañana a las 10 a@b.cl", []),
    ({"agenda": AGENDA}, "una visita el viernes a las 11:30, correo ana@empresa.cl, para revisar catálogo", []),
    ({"agenda": AGENDA}, "visita el domingo a las 11 a@b.cl", []),
    ({"agenda": AGENDA}, "visita hoy a las 3 pm a@b.cl", []),
    ({"agenda": {**AGENDA, "pide_correo": False}}, "visita el 25/11 a las 9", []),
    ({}, "reunión pasado mañana 12:30, juan@mail.com, Cotización Mayorista", []),
    ({}, "reunión el lunes a las 9 x@y.cl",
     [{"role": "assistant", "content": "Listo ✅ Te agendé la reunión para el 2026-11-23 a las 09:00."}]),
    ({}, "quiero agendar", []),
]


@pytest.mark.skipif(shutil.which("node") is None, reason="se necesita Node para ejecutar el código de n8n")
def test_detectar_interes_identico_a_n8n(tmp_path):
    casos = [{"ctx": {"config": c, "user_message": m, "history": h, "from": "56900000001"},
              "ahora_utc": AHORA[0]} for c, m, h in CASOS_INTERES]
    for caso, n8n in zip(casos, _node("detectar_interes_n8n.js", casos, tmp_path), strict=True):
        c = caso["ctx"]
        assert detectar_interes(c["config"], c["user_message"], c["history"], c["from"]) == n8n, c["user_message"]


@pytest.mark.skipif(shutil.which("node") is None, reason="se necesita Node para ejecutar el código de n8n")
def test_detectar_agenda_identico_a_n8n(tmp_path):
    casos = [{"ctx": {"config": c, "user_message": m, "history": h, "from": "56900000001",
                      "nombre_asistente": "Sofía", "nombre_empresa": "Cadabra Demo"}, "ahora_utc": a}
             for a in AHORA for c, m, h in CASOS_AGENDA]
    for caso, n8n in zip(casos, _node("detectar_agenda_n8n.js", casos, tmp_path), strict=True):
        c = caso["ctx"]
        ahora = datetime.fromisoformat(caso["ahora_utc"]).astimezone(ZoneInfo("America/Santiago")).replace(tzinfo=None)
        python = detectar_agenda(ContextoDeteccion(c["config"], c["user_message"], c["history"], c["from"],
                                                   c["nombre_asistente"], c["nombre_empresa"]), ahora)
        assert python == n8n, (caso["ahora_utc"], c["user_message"])
