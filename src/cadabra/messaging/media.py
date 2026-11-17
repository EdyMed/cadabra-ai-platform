"""Descarga de archivos que mandan los clientes (audio, foto, documento) desde la Graph API de Meta.

Igual que n8n ("Obtener URL media" → "Descargar binario"): primero se pide la URL temporal del archivo y luego
se descarga con el mismo token. Solo lectura: sirve también en modo ensayo.
"""
from dataclasses import dataclass

import httpx

# Tope de tamaño: Whisper acepta hasta 25 MB; nada que el agente lea necesita más.
MAX_BYTES = 25 * 1024 * 1024


class ArchivoMuyGrande(Exception):
    pass


@dataclass(frozen=True)
class Archivo:
    contenido: bytes
    mime: str


async def descargar(media_id: str, token: str, version: str = "v21.0",
                    http: httpx.AsyncClient | None = None) -> Archivo:
    propio = http is None
    http = http or httpx.AsyncClient(timeout=60)
    cabecera = {"Authorization": f"Bearer {token}"}
    try:
        r = await http.get(f"https://graph.facebook.com/{version}/{media_id}", headers=cabecera)
        r.raise_for_status()
        datos = r.json()
        if int(datos.get("file_size") or 0) > MAX_BYTES:
            raise ArchivoMuyGrande(datos.get("file_size"))
        r = await http.get(datos["url"], headers=cabecera)
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:
            raise ArchivoMuyGrande(len(r.content))
        return Archivo(r.content, datos.get("mime_type") or r.headers.get("content-type") or "")
    finally:
        if propio:
            await http.aclose()
