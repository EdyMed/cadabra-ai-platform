# Despliegue en el VPS (EasyPanel)

Dominio de la API: **`plataforma.appcadabra.cl`** (aprobado el 17-11-2026).

Una sola imagen, dos apps en EasyPanel. Nada de esto toca n8n: el webhook de Meta sigue apuntando a n8n
hasta la Etapa 6, y todas las líneas entran con `motor = 'n8n'`.

## 1. Base de datos (una vez)

1. Supabase → SQL Editor → ejecutar `scripts/supabase_roles.sql` con dos contraseñas nuevas (sin `#`).
2. En la PC, crear `.env` (desde `.env.example`) con la URL del **migrador**, usando el *Session pooler* de Supabase (puerto 5432; el de
   transacciones, 6543, no sirve con asyncpg):
   `CADABRA_DATABASE_URL=postgresql+asyncpg://platform_migrator.cexowmypklxngbjsxryf:CLAVE@HOST_POOLER:5432/postgres`
3. `.venv/Scripts/alembic upgrade head` → crea el schema `platform` (0001) y carga empresas y líneas (0002).

## 2. DNS

Hostinger → Dominios → `appcadabra.cl` → DNS → registro **A** `plataforma` → `76.13.229.111`.

## 3. Imagen

Docker no está instalado en la PC: la imagen se construye en el VPS, como el panel CRM.

```powershell
# Desde la carpeta del proyecto (pide la contraseña de root)
ssh root@76.13.229.111 "mkdir -p /opt/cadabra-ai-platform"
scp -r pyproject.toml alembic.ini src migrations docker root@76.13.229.111:/opt/cadabra-ai-platform/
ssh root@76.13.229.111 "cd /opt/cadabra-ai-platform && docker build -f docker/Dockerfile -t 127.0.0.1:5000/cadabra-ai-platform:latest . && docker push 127.0.0.1:5000/cadabra-ai-platform:latest"
```

## 4. Apps en EasyPanel

| App | Imagen | Comando | Dominio |
| --- | --- | --- | --- |
| `plataforma-api` | `127.0.0.1:5000/cadabra-ai-platform:latest` | (el de la imagen) | `plataforma.appcadabra.cl` → puerto 8000 |
| `plataforma-worker` | la misma | `taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas` | ninguno |

Variables en Entorno (ambas apps), con la URL del rol **`platform_app`** (no la del migrador):

```
CADABRA_ENTORNO=produccion
CADABRA_DATABASE_URL=postgresql+asyncpg://platform_app.cexowmypklxngbjsxryf:CLAVE@HOST_POOLER:5432/postgres
CADABRA_REDIS_URL=redis://<redis de EasyPanel>:6379/0
CADABRA_META_APP_SECRET=...
CADABRA_META_VERIFY_TOKEN=...
```

Ojo con EasyPanel: un valor con `#` en Entorno se corta (ver la nota de ApiTransferencias).

## 5. Verificación

- `https://plataforma.appcadabra.cl/healthz` → `{"estado":"ok","redis":true}`.
- Un POST firmado a `/webhooks/whatsapp` aparece en los logs del worker como "evento de WhatsApp recibido".
