import os

# Variables mínimas para importar la app sin .env (nunca secretos reales en las pruebas).
os.environ.setdefault("CADABRA_META_APP_SECRET", "secreto-de-prueba")
os.environ.setdefault("CADABRA_META_VERIFY_TOKEN", "token-de-prueba")
os.environ.setdefault("CADABRA_REDIS_URL", "redis://localhost:6379/15")
