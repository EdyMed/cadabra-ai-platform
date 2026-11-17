"""Configuración por variables de entorno (prefijo CADABRA_). Ningún secreto vive en el código."""
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CADABRA_", extra="ignore")

    entorno: str = "local"
    database_url: SecretStr | None = None
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    meta_app_secret: SecretStr
    meta_verify_token: SecretStr
    # Ventana para descartar reintentos de Meta del mismo message_id.
    dedupe_ttl_segundos: int = 172_800
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
