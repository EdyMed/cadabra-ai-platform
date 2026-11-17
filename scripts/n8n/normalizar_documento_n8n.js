// Nodo "Normalizar documento" del workflow LspLEGA3ZegcYoIH, copiado tal cual el 17-11-2026.
const meta = $('Extraer media').first().json;
const texto = ($input.first().json.text || '').trim();
const caption = (meta.caption || '').trim();
const nombre = meta.filename || 'documento';
let user_message;
if (texto) {
  user_message = '[El cliente envió un DOCUMENTO (' + nombre + '). Contenido extraído: ' + texto.slice(0, 4000) + ']';
} else {
  user_message = '[El cliente envió un DOCUMENTO (' + nombre + ') pero no pude extraer texto (puede ser un PDF escaneado o una imagen). Pídele amablemente que te lo mande como foto o que escriba lo que necesita.]';
}
if (caption) user_message += '\nTexto del cliente: ' + caption;
return [{ json: {
  from: meta.from,
  phone_number_id: meta.phone_number_id,
  user_message,
  message_id: meta.message_id,
  timestamp: meta.timestamp
}}];
