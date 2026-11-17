// Nodo "Normalizar imagen" del workflow LspLEGA3ZegcYoIH, copiado tal cual el 17-11-2026.
const meta = $('Extraer media').first().json;
const resp = $input.first().json;
const lectura = resp?.choices?.[0]?.message?.content?.trim() || '(no pude leer la imagen)';
const caption = (meta.caption || '').trim();
const user_message = '[El cliente envió una IMAGEN. Lectura automática: ' + lectura + ']' + (caption ? ('\nTexto del cliente: ' + caption) : '');
return [{ json: {
  from: meta.from,
  phone_number_id: meta.phone_number_id,
  user_message,
  message_id: meta.message_id,
  timestamp: meta.timestamp
}}];
