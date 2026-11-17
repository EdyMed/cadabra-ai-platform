// Nodo "Normalizar audio" del workflow LspLEGA3ZegcYoIH, copiado tal cual el 17-11-2026.
const meta = $('Extraer media').first().json;
const texto = ($input.first().json.text || '').trim();
return [{ json: {
  from: meta.from,
  phone_number_id: meta.phone_number_id,
  user_message: texto || '(nota de voz vacía)',
  message_id: meta.message_id,
  timestamp: meta.timestamp
}}];
