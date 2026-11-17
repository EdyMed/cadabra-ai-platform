// Ejecuta el código ORIGINAL de un nodo Code de n8n que lee $('Consolidar contexto').first().json.
// Uso: node ejecutar_nodo_n8n.js <codigo.js> <casos.json>   (cada caso: { ctx, ahora_utc })
// "ahora_utc" congela new Date() para que "mañana" o "el viernes" den lo mismo en n8n y en Python.
const fs = require('fs');
const codigo = fs.readFileSync(process.argv[2], 'utf8');
const casos = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const DateReal = Date;
const salida = casos.map((c) => {
  const fijo = new DateReal(c.ahora_utc).getTime();
  global.Date = class extends DateReal {
    constructor(...a) { if (a.length === 0) super(fijo); else super(...a); }
    static now() { return fijo; }
  };
  try {
    const $ = () => ({ first: () => ({ json: c.ctx }) });
    return new Function('$', codigo)($)[0].json;
  } finally { global.Date = DateReal; }
});
process.stdout.write(JSON.stringify(salida));
