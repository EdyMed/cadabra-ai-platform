"""Configuración por variables de entorno (prefijo CADABRA_). Ningún secreto vive en el código."""
from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
