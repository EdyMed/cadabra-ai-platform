# Motor del agente — mapa del código

Cómo viaja un mensaje de WhatsApp por la plataforma. Cada paso es **un archivo**; si algo falla, el nombre
del paso dice dónde mirar.

```
 Meta ──POST──► messaging/gateway.py         firma, duplicados, encola        (API, responde en < 1 s)
                       │
                       ▼  cola Redis "plat:cola:eventos"
               workers/tareas.py
                 procesar_evento_whatsapp ──► conversations/entrada.py
                                               0. coexistencia → se reenvía a n8n
                                               1. lee los mensajes del evento
                                               2. ¿qué empresa y motor? resolver_linea (db)
                                               3. ¿bot encendido en esta conversación? (bot_activo / pausa)
                                               4. ¿pasó el tope diario?               (conversations/tope.py)
                                               5. audio/foto/PDF → texto              (conversations/multimedia.py)
                                                  otro tipo (sticker, video…) → aviso fijo
                                               6. deja el texto en el buzón           (conversations/buzon.py)
                                               7. agenda procesar_turno
                       │
                       ▼  (espera 8 s: agrupa mensajes seguidos)
                 procesar_turno ─────────► conversations/turno.py
                                               1. ¿soy el último mensaje? si no, termina
                                               2. candado de la conversación (orden)
                                               3. vacía el buzón → texto del turno
                                               4. contexto: empresa, rol, ficha CRM, historial (agents/contexto.py)
                                               5. agente: prompt + herramientas       (agents/agente.py)
                                               6. post_turno en la base: interés → lead, puntaje con IA
                                                                                      (conversations/post_turno.py)
                                               7. guarda el turno y registra la ejecución
                                               8. responde por WhatsApp, cuenta la conversación (n8n) y
                                                  post_turno hacia afuera: alerta al vendedor, evento en
                                                  Calendar, aviso de horario          (integrations/n8n.py)
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
| `conversations/deteccion.py` | Reglas de interés, pedido de humano, nombre y agenda | "Detectar interés / agenda (auto)" |
| `conversations/multimedia.py` + `messaging/media.py` | Descarga el archivo de Meta; Whisper, GPT-4o y PDF → texto | "2 · PROCESAMIENTO MULTIMEDIA" |
| `conversations/puntaje.py` | Clasificador de IA + pesos del puntaje del lead | "Score: …" |
| `integrations/n8n.py` | Webhooks de n8n: alerta al vendedor, contador, Calendar, coexistencia | Workflows auxiliares |

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

## Paridad con n8n

`tests/test_paridad_n8n.py` ejecuta con Node el JavaScript ORIGINAL de n8n ("Consolidar contexto",
"Detectar interés", "Detectar agenda", guardados en `scripts/n8n/`) y exige resultados idénticos en Python.
`scripts/comparar_con_n8n.py` compara respuestas reales de ambos motores; `scripts/verificar_sql.py` prepara
todas las consultas contra la base antes de desplegar.

## Multimedia: diferencias con n8n

- Se convierte **después** de la guarda y el tope (n8n transcribía antes): no se paga Whisper/visión por mensajes
  que no se van a responder.
- Si Meta, OpenAI o el PDF fallan, el agente recibe el texto de respaldo y responde; n8n cortaba sin responder.
- Un documento que no es PDF (Word, Excel) recibe el texto "no pude extraer texto"; en n8n daba error.
- La instrucción de lectura de fotos está escrita para la panadería (empresa 1), igual que en n8n. Pendiente:
  armarla con la descripción del negocio de cada empresa.
