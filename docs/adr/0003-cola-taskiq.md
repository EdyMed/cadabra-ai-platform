# ADR 0003: Taskiq sobre Redis como cola

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

Taskiq (async nativo) con `taskiq-redis`, reintentos con `SimpleRetryMiddleware` y cola `plat:cola:eventos` en el Redis existente. En la Etapa 4 se agrega un buzón por conversación (lista + candado con TTL) para garantizar orden y agrupar mensajes.

## Alternativas descartadas

Celery: orientado a código síncrono y más pesado de operar. ARQ: su autor lo declaró en modo solo mantenimiento. SAQ: alternativa de respaldo.

## Consecuencias

La API y los workers comparten el broker; el orden por conversación es responsabilidad de la Etapa 4.
