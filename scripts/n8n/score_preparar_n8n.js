// Arma la petición al clasificador con los últimos mensajes del cliente y las categorías de la ficha.
const ctx = $('Consolidar contexto').first().json;
const cfg = ctx.config || {};
const cats = (((cfg.interes || {}).categorias) || []).map(c => c && c.nombre).filter(Boolean);
const previos = (ctx.history || []).filter(h => h.role === 'user').slice(-5).map(h => '- ' + String(h.content).slice(0, 400));
const actual = String(ctx.user_message || '').slice(0, 1500);
const negocio = String((cfg.negocio || {}).descripcion || ctx.nombre_empresa || '').slice(0, 400);

const categoria = cats.length
  ? { anyOf: [{ type: 'string', enum: cats }, { type: 'null' }] }
  : { type: ['string', 'null'] };
const schema = {
  type: 'object', additionalProperties: false,
  required: ['intencion', 'categoria', 'cantidad', 'es_negocio', 'urgencia', 'pide_humano', 'resumen'],
  properties: {
    intencion: { type: 'string', enum: ['compra', 'cotizacion', 'agendar', 'consulta_producto', 'soporte_postventa', 'reclamo', 'saludo_o_charla', 'otro'] },
    categoria,
    cantidad: { type: ['string', 'null'], description: 'Cantidad o volumen mencionado (ej. "200 unidades", "3 docenas"), o null' },
    es_negocio: { type: 'boolean', description: 'true si el cliente compra para un negocio (local, restaurant, empresa, almacén, etc.)' },
    urgencia: { type: 'string', enum: ['alta', 'media', 'baja', 'sin_dato'] },
    pide_humano: { type: 'boolean' },
    resumen: { type: 'string', description: 'Qué busca el cliente, en máximo 15 palabras, en español' },
  },
};
const sys = 'Clasificas a clientes que escriben por WhatsApp a un negocio, para priorizar el seguimiento comercial. '
  + 'Negocio: ' + negocio + '. '
  + (cats.length ? 'Categorías de producto válidas: ' + cats.join(', ') + '. ' : '')
  + 'Considera TODO lo que el cliente ha dicho (mensajes previos + actual), no solo el último. '
  + 'intencion: compra = quiere comprar/hacer un pedido; cotizacion = pide precios para comprar o una cotización; agendar = quiere reunión/visita/cita; '
  + 'consulta_producto = pregunta por productos sin intención clara de compra; saludo_o_charla = saludo, gracias o charla sin consulta. '
  + 'urgencia: alta si dice hoy/mañana/urgente/esta semana; media si da un plazo cercano; baja si dice más adelante; si no dice nada, sin_dato. '
  + 'No inventes datos: si algo no se menciona, usa null/false/sin_dato.';
const user = (previos.length ? 'Mensajes anteriores del cliente:\n' + previos.join('\n') + '\n\n' : '') + 'Mensaje actual:\n' + actual;
return [{ json: { body: {
  model: 'gpt-4o-mini', temperature: 0, max_tokens: 250,
  response_format: { type: 'json_schema', json_schema: { name: 'lead', strict: true, schema } },
  messages: [{ role: 'system', content: sys }, { role: 'user', content: user }],
} } }];