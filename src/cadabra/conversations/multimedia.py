"""Audios, fotos y documentos → texto para el agente. Traducción del bloque "2 · PROCESAMIENTO MULTIMEDIA" de n8n.

  audio     → Whisper (español)                    "Whisper transcribir" + "Normalizar audio"
  image     → GPT-4o lee la foto                   "GPT-4o Vision" + "Normalizar imagen"
  document  → texto del PDF                        "Extraer texto PDF" + "Normalizar documento"
  otro tipo → aviso fijo al cliente                "Enviar aviso (otros)"

Los textos que recibe el agente tienen el mismo formato que en n8n (paridad probada en tests/test_multimedia.py).
La instrucción de lectura de fotos ya NO es la de n8n: ver INSTRUCCION_IMAGEN.
Diferencia con n8n: si algo falla (Meta, OpenAI, PDF dañado) el turno sigue con el texto de respaldo en vez
de cortarse sin responder.
"""
import base64
import io
import logging
from dataclasses import dataclass

from openai import AsyncOpenAI
from pypdf import PdfReader

from cadabra.messaging.media import Archivo

log = logging.getLogger(__name__)

TIPOS = {"audio", "image", "document"}

AVISO_OTROS = ("Por ahora puedo leer texto, notas de voz, fotos y PDF 🙌. Ese tipo de mensaje no lo puedo procesar; "
               "cuéntame por texto o mándame una foto y te ayudo.")

# Instrucción neutral, válida para cualquier empresa. La de n8n nombraba los productos de la panadería y el modelo
# respondía "no es un producto de panadería o pastelería": esas palabras activaban la detección de interés
# (conversations/deteccion.py) con categorías falsas. Aquí solo se describe lo que se ve, sin opinar.
INSTRUCCION_IMAGEN = (
    "Describe en español, de forma breve y objetiva, lo que muestra esta imagen que un cliente envió por WhatsApp a "
    "un negocio. Si es un producto, di qué producto es, con sus características visibles (tipo, sabor, tamaño, marca, "
    "cantidad). Si es un documento (lista de pedido, comprobante, factura, cotización), transcribe su texto con los "
    "ítems y cantidades. Describe solo lo que se ve: no opines si se relaciona con el negocio ni menciones rubros o "
    "productos que no aparezcan en la imagen."
)


@dataclass(frozen=True)
class Medio:
    tipo: str            # audio | image | document
    caption: str = ""
    filename: str = ""


# ── Textos para el agente (idénticos a los nodos "Normalizar …") ──────────────────────────────────────────────

def texto_audio(transcripcion: str) -> str:
    return transcripcion.strip() or "(nota de voz vacía)"


def texto_imagen(lectura: str, caption: str) -> str:
    lectura = lectura.strip() or "(no pude leer la imagen)"
    caption = caption.strip()
    return f"[El cliente envió una IMAGEN. Lectura automática: {lectura}]" + (f"\nTexto del cliente: {caption}"
                                                                               if caption else "")


def texto_documento(contenido: str, filename: str, caption: str) -> str:
    contenido, caption, nombre = contenido.strip(), caption.strip(), filename or "documento"
    if contenido:
        texto = f"[El cliente envió un DOCUMENTO ({nombre}). Contenido extraído: {contenido[:4000]}]"
    else:
        texto = (f"[El cliente envió un DOCUMENTO ({nombre}) pero no pude extraer texto (puede ser un PDF escaneado "
                 "o una imagen). Pídele amablemente que te lo mande como foto o que escriba lo que necesita.]")
    return texto + (f"\nTexto del cliente: {caption}" if caption else "")


# ── Lectores ─────────────────────────────────────────────────────────────────────────────────────────────────

def extraer_pdf(contenido: bytes) -> str:
    lector = PdfReader(io.BytesIO(contenido))
    return "\n".join((pagina.extract_text() or "") for pagina in lector.pages)


def _es_pdf(archivo: Archivo, filename: str) -> bool:
    return "pdf" in archivo.mime.lower() or filename.lower().endswith(".pdf") or archivo.contenido[:5] == b"%PDF-"


def _extension_audio(mime: str) -> str:
    mime = mime.split(";")[0].strip().lower()
    return {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "m4a", "audio/amr": "amr",
            "audio/wav": "wav", "audio/webm": "webm"}.get(mime, "ogg")


async def transcribir(archivo: Archivo, cliente: AsyncOpenAI, modelo: str) -> str:
    r = await cliente.audio.transcriptions.create(
        model=modelo, language="es",
        file=(f"nota.{_extension_audio(archivo.mime)}", archivo.contenido, archivo.mime or "audio/ogg"),
    )
    return r.text or ""


async def leer_imagen(archivo: Archivo, caption: str, cliente: AsyncOpenAI, modelo: str) -> str:
    instruccion = INSTRUCCION_IMAGEN + (f' El cliente escribió junto a la imagen: "{caption}".' if caption else "")
    datos = base64.b64encode(archivo.contenido).decode()
    r = await cliente.chat.completions.create(model=modelo, max_tokens=500, messages=[{"role": "user", "content": [
        {"type": "text", "text": instruccion},
        {"type": "image_url", "image_url": {"url": f"data:{archivo.mime or 'image/jpeg'};base64,{datos}"}},
    ]}])
    return r.choices[0].message.content or ""


async def a_texto(medio: Medio, archivo: Archivo | None, cliente: AsyncOpenAI,
                  modelo_audio: str, modelo_vision: str) -> str:
    """Texto que recibe el agente. `archivo` None = no se pudo descargar (se usa el texto de respaldo)."""
    try:
        if archivo is not None and medio.tipo == "audio":
            return texto_audio(await transcribir(archivo, cliente, modelo_audio))
        if archivo is not None and medio.tipo == "image":
            return texto_imagen(await leer_imagen(archivo, medio.caption, cliente, modelo_vision), medio.caption)
        if archivo is not None and medio.tipo == "document":
            contenido = extraer_pdf(archivo.contenido) if _es_pdf(archivo, medio.filename) else ""
            return texto_documento(contenido, medio.filename, medio.caption)
    except Exception:  # un archivo ilegible no debe dejar al cliente sin respuesta
        log.exception("no se pudo leer el archivo del cliente", extra={"datos": {"tipo": medio.tipo}})
    return {"audio": texto_audio(""), "image": texto_imagen("", medio.caption)}.get(
        medio.tipo, texto_documento("", medio.filename, medio.caption))
