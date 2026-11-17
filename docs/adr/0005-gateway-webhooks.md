# ADR 0005: Gateway de webhooks rápido y seguro

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

El endpoint `/webhooks/whatsapp` valida `X-Hub-Signature-256` sobre el cuerpo crudo, verifica `hub.verify_token`, descarta duplicados por `message_id` (Redis, prefijo `plat:wamid:`, 48 h), encola y responde 200. No llama al modelo ni a la base.

## Alternativas descartadas

Procesar dentro del request (como hoy en n8n): Meta reintenta si la respuesta tarda.

## Consecuencias

El prefijo distinto al de n8n (`wamid:`) permite que n8n reenvíe mensajes a la plataforma durante la convivencia.
