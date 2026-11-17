# Una sola imagen para la API y los workers; EasyPanel elige el proceso con el comando.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install . && useradd --create-home --uid 10001 cadabra
USER cadabra

EXPOSE 8000
# API (por defecto). Worker: taskiq worker cadabra.workers.broker:broker cadabra.workers.tareas
CMD ["uvicorn", "cadabra.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
