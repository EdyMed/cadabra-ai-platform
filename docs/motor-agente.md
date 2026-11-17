# Motor del agente — mapa del código

Cómo viaja un mensaje de WhatsApp por la plataforma. Cada paso es **un archivo**; si algo falla, el nombre
del paso dice dónde mirar.

```
 Meta ──POST──► messaging/gateway.py         firma, duplicados, encola        (API, responde en < 1 s)
                       │
                       ▼  cola Redis "plat:cola:eventos"
               workers/tareas.py
                 procesar_evento_whatsapp ──► conversations/entrada.py
                                               1. lee los mensajes del evento         (meta_eventos.py)
                                               2. ¿qué empresa y motor? resolver_linea (db)
                                               3. ¿bot encendido en esta conversación? (bot_activo / pausa)
                                               4. deja el texto en el buzón           (conversations/buzon.py)
                                               5. agenda procesar_turno
                       │
                       ▼  (espera 8 s: agrupa mensajes seguidos)
                 procesar_turno ─────────► conversations/turno.py
                                               1. ¿soy el último mensaje? si no, termina
                                               2. candado de la conversación (orden)
                                               3. vacía el buzón → texto del turno
                                               4. contexto: empresa, rol, ficha CRM, historial (agents/contexto.py)
                                               5. agente: prompt + herramientas       (agents/agente.py)
                                               6. guarda el turno y responde por WhatsApp (messaging/whatsapp_api.py)
                                               7. registra la ejecución (tokens, costo, latencia)
```

## Dónde está cada cosa

| Carpeta | Qué contiene | Equivale en n8n a |
| --- | --- | --- |
| `messaging/` | Entrada (gateway) y salida (API de WhatsApp) | Webhook, "Enviar WhatsApp" |
| `conversations/` | Orden del turno: entrada, buzón, turno | Guarda, Buffer, Tope |
| `agents/contexto.py` | Lee empresa, rol, ficha del CRM e historial | Resolver empresa / rol / historial |
| `agents/perfil.py` | Convierte la ficha JSONB en los textos del prompt | "Consolidar contexto" |
| `agents/prompt.py` | El prompt de sistema, igual al de n8n | Prompt del "AI Agent" |
| `agents/agente.py` | El grafo LangGraph: modelo + herramientas | "AI Agent" + "OpenAI" |
| `tools/` | Una herramienta por archivo, con argumentos tipados | Nodos de herramientas |

## Reglas del motor

- **Modo ensayo** (`CADABRA_MODO_ENSAYO=true`, por defecto): procesa todo, pero **no envía** a WhatsApp ni
  escribe en el CRM ni en el historial; deja la respuesta en el log y en `platform.agent_executions`. Sirve para
  comparar contra n8n sin tocar a ningún cliente.
- Fuera del modo ensayo solo se procesan las líneas con `platform.lineas.motor = 'codigo'`.
- Las herramientas de gestión (ventas, top productos, deudas) **solo se entregan al modelo si el rol es owner**.
  En n8n eso lo decía el prompt; aquí lo garantiza el código.
- `crm_actualizar_estado` solo puede tocar el lead **de la conversación actual y de la empresa actual**
  (en n8n actualizaba por `record_id` sin filtrar empresa).
- La ficha del agente se lee en vivo desde `public.agente_empresas_config` mientras convivan n8n y la plataforma,
  para que un cambio hecho en el panel aplique a ambos.

## Pendiente (siguientes entregas)

Multimedia (audio, imagen, PDF), tope diario, detección automática de interés, alerta al vendedor, agenda en
Google Calendar, puntaje del lead y eventos de coexistencia. Mientras tanto siguen en n8n.
