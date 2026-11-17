"""Audios, fotos y documentos: mismos textos que n8n, y la entrada los convierte antes del buzón."""
import io
import json
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfWriter

from cadabra.conversations import multimedia
from cadabra.conversations.entrada import leer_mensajes
from cadabra.messaging.media import Archivo

RAIZ = Path(__file__).resolve().parents[1]


def _n8n(codigo: str, casos: list[dict], tmp_path) -> list[str]:
    archivo = tmp_path / "casos.json"
    archivo.write_text(json.dumps(casos, ensure_ascii=False), encoding="utf-8")
    salida = subprocess.run(["node", str(RAIZ / "tests/fixtures/ejecutar_normalizar_n8n.js"),
                             str(RAIZ / "scripts/n8n" / codigo), str(archivo)], capture_output=True, check=True)
    return json.loads(salida.stdout.decode("utf-8"))


def test_audio_igual_a_n8n(tmp_path):
    textos = ["  quiero 3 docenas de empanadas de pino  ", "", "   "]
    esperado = _n8n("normalizar_audio_n8n.js", [{"meta": {}, "entrada": {"text": t}} for t in textos], tmp_path)
    assert [multimedia.texto_audio(t) for t in textos] == esperado


def test_imagen_igual_a_n8n(tmp_path):
    casos = [("Una empanada de pino horneada.", ""), ("Lista: 20 pino, 10 queso", " para el sábado "),
             ("", ""), ("", "esta")]
    esperado = _n8n("normalizar_imagen_n8n.js", [
        {"meta": {"caption": c}, "entrada": {"choices": [{"message": {"content": lectura}}]}} for lectura, c in casos
    ], tmp_path)
    assert [multimedia.texto_imagen(lectura, c) for lectura, c in casos] == esperado


def test_documento_igual_a_n8n(tmp_path):
    largo = "x" * 5000
    casos = [("Pedido: 20 empanadas", "pedido.pdf", ""), ("", "escaneo.pdf", "mi pedido"), (largo, "", "")]
    esperado = _n8n("normalizar_documento_n8n.js", [
        {"meta": {"filename": f, "caption": c}, "entrada": {"text": t}} for t, f, c in casos
    ], tmp_path)
    assert [multimedia.texto_documento(t, f, c) for t, f, c in casos] == esperado


def test_lee_datos_del_archivo():
    evento = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "PN"}, "messages": [
        {"id": "w1", "from": "569", "type": "document",
         "document": {"id": "M1", "mime_type": "application/pdf", "filename": "pedido.pdf", "caption": "ojo"}}]}}]}]}
    [m] = leer_mensajes(evento)
    assert (m.tipo, m.media_id, m.filename, m.caption, m.texto) == ("document", "M1", "pedido.pdf", "ojo", "")


class _ClienteQueFalla:
    """Si OpenAI falla, el agente recibe el texto de respaldo (n8n cortaba el turno sin responder)."""
    def __getattr__(self, _):
        raise RuntimeError("OpenAI caído")


@pytest.mark.parametrize("tipo, esperado", [
    ("audio", "(nota de voz vacía)"),
    ("image", "[El cliente envió una IMAGEN. Lectura automática: (no pude leer la imagen)]"),
])
async def test_respaldo_si_openai_falla(tipo, esperado):
    medio = multimedia.Medio(tipo)
    assert await multimedia.a_texto(medio, Archivo(b"x", "audio/ogg"), _ClienteQueFalla(), "w", "v") == esperado


async def test_pdf_sin_texto_y_archivo_no_pdf():
    pdf = PdfWriter()
    pdf.add_blank_page(width=100, height=100)

    b = io.BytesIO()
    pdf.write(b)
    for archivo in (Archivo(b.getvalue(), "application/pdf"), Archivo(b"PK...", "application/msword")):
        texto = await multimedia.a_texto(multimedia.Medio("document", filename="x.pdf"), archivo,
                                         _ClienteQueFalla(), "w", "v")
        assert "no pude extraer texto" in texto


def test_instruccion_de_fotos_no_nombra_rubros():
    """Si la instrucción nombra productos, el modelo los repite y la detección de interés los toma como del cliente."""
    import re
    assert not re.search(r"panader|pastel|empanada|pan\b|sopaipilla", multimedia.INSTRUCCION_IMAGEN, re.I)
