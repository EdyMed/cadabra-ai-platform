"""Paridad con n8n: el perfil que arma Python debe ser IDÉNTICO al del nodo "Consolidar contexto".

Ejecuta el JavaScript original de n8n con Node (si está instalado) sobre las fichas reales de las empresas y
sobre fichas sintéticas que recorren todas las ramas, y compara texto a texto.
"""
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.perfil import construir_perfil, ficha_cliente, negocio_configurado

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
