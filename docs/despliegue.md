# Despliegue en el VPS (EasyPanel)

Una sola imagen, dos apps en EasyPanel. Nada de esto toca n8n: el webhook de Meta sigue apuntando a n8n
hasta la Etapa 6.

1. **Imagen:** `docker build -f docker/Dockerfile -t 127.0.0.1:5000/cadabra-ai-platform:latest .` y `docker push` al
   registro local del VPS (mismo método que `crm-panel`).
2. **App `plataforma-api`:** imagen anterior, puerto 8000, dominio propio (p. ej. `plataforma.appcadabra.cl`),
   variables `CADABRA_*` en Entorno. Health check: `GET /healthz`.
3. **App `plataforma-worker`:** misma imagen, comando
   `taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas`, mismas variables, sin dominio.
4. **Redis:** `CADABRA_REDIS_URL` apunta al Redis existente (las claves de la plataforma usan el prefijo `plat:`).
5. **Base de datos:** `CADABRA_DATABASE_URL` al Supabase actual con un rol propio de la plataforma, sin
   `BYPASSRLS`. Las migraciones (`alembic upgrade head`) se ejecutan solo con aprobación.

Ojo con EasyPanel: un valor con `#` en Entorno se corta (ver la nota de ApiTransferencias).
