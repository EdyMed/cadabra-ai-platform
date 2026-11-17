// Ejecuta el código ORIGINAL del nodo "Consolidar contexto" de n8n sobre casos de prueba.
// Uso: node ejecutar_n8n.js <codigo_n8n.js> <casos.json>   → imprime la salida de n8n por caso (JSON).
const fs = require('fs');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
const casos = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const salida = casos.map((c) => {
  const ctx = { ...c, lead: c.lead || null };
  const $ = () => ({ first: () => ({ json: ctx }) });
  const $input = { all: () => (c.historial_desc || []).map((r) => ({ json: r })) };
  return new Function('$', '$input', codigo)($, $input)[0].json;
});
process.stdout.write(JSON.stringify(salida));
