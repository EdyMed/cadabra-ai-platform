"""Validación de la firma X-Hub-Signature-256 que Meta agrega a cada webhook.

Meta firma el cuerpo CRUDO de la petición con HMAC-SHA256 usando el App Secret.
Hay que validar sobre los bytes recibidos, nunca sobre el JSON re-serializado.
"""
import hashlib
import hmac


def firma_valida(cuerpo: bytes, cabecera: str | None, app_secret: str) -> bool:
    if not cabecera or not cabecera.startswith("sha256=") or not app_secret:
        return False
    esperado = "sha256=" + hmac.new(app_secret.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecera)
