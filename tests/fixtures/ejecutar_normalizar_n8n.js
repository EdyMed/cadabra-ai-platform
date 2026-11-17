// Ejecuta el código ORIGINAL de los nodos "Normalizar audio / imagen / documento" de n8n.
// Uso: node ejecutar_normalizar_n8n.js <codigo.js> <casos.json>   (cada caso: { meta, entrada })
//   meta    = salida de "Extraer media" (caption, filename…);  entrada = salida de Whisper / Vision / PDF
const fs = require('fs');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
const casos = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const salida = casos.map((c) => {
  const $ = () => ({ first: () => ({ json: c.meta }) });
  const $input = { first: () => ({ json: c.entrada }) };
  return new Function('$', '$input', codigo)($, $input)[0].json.user_message;
});
process.stdout.write(JSON.stringify(salida));
