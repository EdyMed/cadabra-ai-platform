"""Genera src/cadabra/agents/prompt.py desde el prompt de sistema exportado de n8n."""
import re
import sys

origen, destino = sys.argv[1], sys.argv[2]
with open(origen, encoding="utf-8") as f:
    t = f.read()
assert t.startswith("=")
t = t[1:]

mapa = {
    "{{ $json.nombre_asistente }}": "nombre_asistente",
    "{{ $json.nombre_empresa }}": "nombre_empresa",
    "{{ $json.perfil.descripcion }}": "descripcion",
    "{{ $json.empresa }}": "empresa",
    "{{ $json.rol }}": "rol",
    "{{ $json.rut_cliente }}": "rut_cliente",
    "{{ $now.format('yyyy-MM-dd HH:mm') }}": "fecha_hora",
    "{{ $now.setLocale('es').toFormat('cccc') }}": "dia_semana",
    "{{ $json.history_text }}": "historial",
    "{{ $json.ficha_cliente }}": "ficha_cliente",
    "{{ $json.perfil.info_negocio }}": "info_negocio",
    "{{ $json.perfil.catalogo }}": "catalogo",
    "{{ $json.perfil.categorias_menu }}": "categorias_menu",
    "{{ $json.perfil.escalamiento }}": "escalamiento",
    "{{ $json.perfil.categorias_interes }}": "categorias_interes",
    "{{ $json.perfil.tono }}": "tono",
    "{{ $json.perfil.agenda }}": "agenda",
}
for expr, campo in mapa.items():
    t = t.replace(expr, "\x00" + campo + "\x01")
quedan = re.findall(r"\{\{.*?\}\}", t)
assert not quedan, quedan
# Llaves literales del texto se duplican para str.format; luego se insertan los campos.
t = t.replace("{", "{{").replace("}", "}}").replace("\x00", "{").replace("\x01", "}")
assert '"""' not in t and "\\" not in t

cabecera = '''"""Prompt de sistema del agente: copia fiel del prompt del nodo "AI Agent" de n8n.

Generado desde el workflow LspLEGA3ZegcYoIH (17-11-2026) con scripts/generar_prompt.py.
Mientras convivan n8n y la plataforma, un cambio de texto se hace en LOS DOS lados.
"""
from dataclasses import asdict

from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.perfil import ficha_cliente

PLANTILLA = """'''

pie = '''"""


def armar_prompt(ctx: ContextoTurno, fecha_hora: str, dia_semana: str) -> str:
    """Completa la plantilla con los datos del turno (equivale a las expresiones {{ }} de n8n)."""
    perfil = asdict(ctx.perfil)
    for no_usado in ("menu", "fuente_catalogo"):
        perfil.pop(no_usado)
    return PLANTILLA.format(
        nombre_asistente=ctx.nombre_asistente,
        nombre_empresa=ctx.nombre_empresa,
        empresa=ctx.empresa,
        rol=ctx.rol,
        rut_cliente=ctx.rut_cliente or "",
        fecha_hora=fecha_hora,
        dia_semana=dia_semana,
        historial=ctx.historial_texto(),
        ficha_cliente=ficha_cliente(ctx.lead),
        **perfil,
    )
'''
with open(destino, "w", encoding="utf-8", newline="\n") as f:
    f.write(cabecera + t + pie)
print("campos:", sorted(set(re.findall(r"(?<!\{)\{([a-z_]+)\}(?!\})", t))))
