"""Configuración por variables de entorno (prefijo CADABRA_). Ningún secreto vive en el código."""
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CADABRA_", extra="ignore")

    entorno: str = "local"
    database_url: SecretStr | None = None
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    log_level: str = "INFO"

    # Meta. Vacíos por defecto (p. ej. al correr Alembic): el gateway rechaza todo hasta que se configuren.
    meta_app_secret: SecretStr = SecretStr("")
    meta_verify_token: SecretStr = SecretStr("")
    meta_token: SecretStr = SecretStr("")          # token del usuario del sistema de Cadabra (envío)
    meta_graph_version: str = "v21.0"
    # Puerta de entrada: true SOLO cuando el webhook de Meta apunta a la plataforma. Entonces las líneas con
    # motor='n8n' (o sin línea) se reenvían a n8n tal cual, y las con motor='codigo' las atiende la plataforma.
    puerta_entrada: bool = False
    # Alta de líneas (POST /v1/lineas, lo llama el panel tras el Embedded Signup). Sin clave, el endpoint no opera.
    admin_clave: SecretStr = SecretStr("")         # encabezado X-Cadabra-Admin
    url_publica: str = "https://plataforma.appcadabra.cl"   # a dónde apunta el webhook propio de cada línea
    motor_lineas_nuevas: Literal["codigo", "n8n"] = "codigo"
    # Ventana para descartar reintentos de Meta del mismo message_id.
    dedupe_ttl_segundos: int = 172_800

    # Motor del agente
    modo_ensayo: bool = True                       # True: procesa y registra, pero NO envía ni escribe en el CRM
    debounce_segundos: float = 8.0                 # espera para agrupar mensajes seguidos (igual que n8n)
    openai_api_key: SecretStr = SecretStr("")
    modelo: str = "gpt-4o-mini"
    temperatura: float = 0.3
    max_iteraciones: int = 6                       # pasos del agente por turno (n8n: maxIterations = 6)
    zona_horaria: str = "America/Santiago"
    modelo_puntaje: str = "gpt-4o-mini"            # clasificador del puntaje del lead (igual que n8n)
    modelo_audio: str = "whisper-1"                # notas de voz (igual que n8n)
    modelo_vision: str = "gpt-4o"                  # lectura de fotos (igual que n8n)

    # n8n: integraciones que siguen allá (Calendar, alerta al vendedor, contador, coexistencia)
    n8n_url: str = "https://appcadabra-cadabra-project.jmyxxj.easypanel.host"
    n8n_clave: SecretStr = SecretStr("")           # encabezado X-Cadabra-Clave de los webhooks internos


@lru_cache
def get_settings() -> Settings:
    return Settings()
