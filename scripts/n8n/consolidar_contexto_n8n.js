const ctx = $('Determinar rol').first().json;

// ---- Ficha del cliente en el CRM (memoria de largo plazo) ----
const fichaCliente = (() => {
  const l = ctx.lead;
  if (!l) return '(Sin ficha en el CRM: es un contacto nuevo o todavía no mostró interés de compra.)';
  const v = (x) => (x === null || x === undefined || String(x).trim() === '') ? null : String(x).trim();
  const filas = [
    ['Nombre', v(l.nombre)], ['Negocio', v(l.negocio)], ['Producto de interés', v(l.producto)],
    ['Etapa comercial', v(l.estado)], ['Comuna', v(l.comuna)],
    ['Vendedor asignado', v(l.vendedor)],
    ['Cita', v(l.fecha_cita) ? (l.fecha_cita + (v(l.hora_cita) ? ' ' + l.hora_cita : '') + (v(l.agenda) ? ' (' + l.agenda + ')' : '')) : null],
    ['Cliente desde', v(l.desde)],
  ].filter(([, x]) => x);
  return filas.length ? filas.map(([k, x]) => '- ' + k + ': ' + x).join('\n') : '(Ficha en el CRM sin datos todavía.)';
})();
const rows = $input.all().map(i => i.json).filter(r => r && r.role && r.content).reverse();
const history = rows.map(r => ({ role: r.role, content: r.content }));
const historyText = history.map(h => h.role + ': ' + h.content).join('\n');

// ---- Ficha del agente por empresa (agente_empresas_config.config) ----
// Cada bloque tiene un texto por defecto genérico; la empresa 1 (Sofía) guarda en su
// ficha el texto original de la panadería, así que su comportamiento no cambia.
const cfg = (ctx.config && typeof ctx.config === 'object') ? ctx.config : {};
const asist = ctx.nombre_asistente || 'Asistente';
const empresaNom = ctx.nombre_empresa || 'la empresa';
const t = (v, d) => (typeof v === 'string' && v.trim()) ? v.trim() : d;
const sub = s => String(s || '').split('{asistente}').join(asist).split('{empresa}').join(empresaNom);
const neg = cfg.negocio || {}, cat = cfg.catalogo || {}, tono = cfg.tono || {}, ag = cfg.agenda || {};
const menu = cfg.menu || {}, interes = cfg.interes || {};
const DIAS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];

const descripcion = t(neg.descripcion, '')
  ? ', ' + sub(neg.descripcion)
  : '. Respondes consultas de productos y precios, ayudas a tus clientes y agendas citas, siempre usando las HERRAMIENTAS disponibles.';

const categorias_menu = t(cat.categorias_menu, 'las categorías de nuestro catálogo');

let catalogo = t(cat.texto, '');
if (!catalogo) {
  const l = ['## Catálogo — cómo atender consultas de productos',
    '- Categorías principales del negocio: ' + categorias_menu + '.',
    '- Si el cliente pregunta en general ("qué venden", "qué productos tienes"), menciona brevemente esas categorías y pregúntale cuál quiere ver CON PRECIO. No recites productos de memoria.',
    '- Cuando elija una categoría o nombre un producto, usa stock_producto pasando SOLO la(s) palabra(s) clave (sin relleno como "de" o "por favor"). Si da vacío, reintenta con una palabra más general antes de decir que no hay.',
    '- DISPONIBILIDAD: ' + t(cat.disponibilidad, 'los productos que devuelve la herramienta están disponibles; para pedidos grandes o urgentes, sugiere confirmar con un vendedor.')];
  if (t(cat.unidad, '')) l.push('- Unidad de venta: ' + cat.unidad + '. Si no especifican, aclara la unidad.');
  if (Array.isArray(cat.sinonimos)) cat.sinonimos.forEach(s => { if (s && s.dice && s.buscar) l.push('- Si el cliente dice "' + s.dice + '" → busca "' + s.buscar + '".'); });
  catalogo = l.join('\n');
}
catalogo = sub(catalogo);

const escalamiento = sub(t(cfg.escalamiento, 'Ofrece derivar a un vendedor cuando: el cliente quiera cerrar un pedido, negociar precios o condiciones, haya un reclamo, o lleves 3 turnos sin resolver su necesidad.'));

let tonoTxt = t(tono.texto, '');
if (!tonoTxt) {
  const usted = tono.trato === 'usted';
  tonoTxt = [
    usted ? 'Habla cordial y respetuoso, tratando al cliente SIEMPRE de USTED (nunca de tú). IMPORTANTE: aunque los ejemplos de estas instrucciones estén escritos en tú, TÚ respondes siempre de usted ("¿Le gustaría…?", "le muestro", "¿en qué le ayudo?"). Cálido pero profesional.'
          : 'Habla CERCANO Y NATURAL, tuteando al cliente (de TÚ, no de usted). Cálido pero profesional, sin sonar acartonado.',
    '- Frases CORTAS y directas. Evita fórmulas rígidas ("no dude en", "hágamelo saber").',
    '- Saludo/bienvenida en el primer mensaje: ' + t(tono.saludo, usted ? "'¡Hola! 😊 Soy {asistente}, de {empresa}. ¿En qué le puedo ayudar?'" : "'¡Hola! 😊 Soy {asistente}. Cuéntame, ¿en qué te puedo ayudar?'"),
    '- Emojis con moderación (' + t(tono.emojis, '😊') + '), no en cada frase.',
    '- Respuestas BREVES para WhatsApp: máximo 4-5 frases.',
    '- Formatea montos en pesos chilenos: $1.234 (punto de miles, sin decimales).',
    '- Muestra los productos con el nombre tal como viene del catálogo (stock_producto).'
  ].join('\n');
}
tonoTxt = sub(tonoTxt);

const info = [];
if (t(neg.horario, '')) info.push('- Horario de atención: ' + neg.horario + '.');
if (t(neg.direccion, '')) info.push('- Dirección: ' + neg.direccion + '.');
if (t(neg.despacho, '')) info.push('- Despacho / delivery: ' + neg.despacho);
if (t(neg.pagos, '')) info.push('- Medios de pago: ' + neg.pagos);
if (t(neg.pedido_minimo, '')) info.push('- Pedido mínimo: ' + neg.pedido_minimo);
if (t(neg.politicas, '')) info.push('- Políticas: ' + neg.politicas);
if (t(neg.no_prometer, '')) info.push('- NUNCA prometas: ' + neg.no_prometer);
if (Array.isArray(cfg.faq)) cfg.faq.forEach(f => { if (f && f.p && f.r) info.push('- Si preguntan "' + f.p + '" → ' + f.r); });
const info_negocio = info.length ? '## Información del negocio (úsala para responder; no inventes nada fuera de esto)\n' + sub(info.join('\n')) : '';

const categorias_interes = (Array.isArray(interes.categorias) ? interes.categorias.map(c => c && c.nombre).filter(Boolean) : []).join(', ') || 'Otro';

let agenda;
if (ag.activa === false) {
  agenda = '## AGENDA\nEste negocio NO agenda citas por WhatsApp. Si el cliente quiere agendar, ofrécele que un vendedor lo contacte para coordinar. NO uses las tools de calendario.';
} else {
  const tipo = t(ag.tipo, 'reunión');
  const ust = tono.trato === 'usted';
  const pideCorreo = ag.pide_correo !== false;
  const datos = pideCorreo ? 'fecha, hora y correo' : 'fecha y hora';
  let horario = '';
  const restringido = (Array.isArray(ag.dias) && ag.dias.length > 0) || !!(ag.hora_inicio && ag.hora_fin);
  if (Array.isArray(ag.dias) && ag.dias.length) horario += 'Días disponibles: ' + ag.dias.map(d => DIAS[d]).filter(Boolean).join(', ') + '. ';
  if (ag.hora_inicio && ag.hora_fin) horario += 'Horario: de ' + ag.hora_inicio + ' a ' + ag.hora_fin + ' hrs. ';
  if (ag.duracion_min) horario += 'Cada ' + tipo + ' dura ' + ag.duracion_min + ' minutos. ';
  if (ag.anticipacion_horas) horario += 'Se agenda con al menos ' + ag.anticipacion_horas + ' horas de anticipación. ';
  if (ag.lugar) horario += 'Lugar: ' + ag.lugar + '. ';
  agenda = [
    '## AGENDAR ' + tipo.toUpperCase() + ' — EL SISTEMA LA CREA, TÚ SOLO PIDES LOS DATOS',
    'El sistema agenda la ' + tipo + ' AUTOMÁTICAMENTE en segundo plano cuando tiene ' + datos + '. Tu única tarea es RECOPILAR esos datos con naturalidad.',
    horario ? '- ' + horario.trim() + (restringido ? ' Si el cliente pide un día u hora fuera de esto, explícale con amabilidad y ofrécele otra opción dentro del horario. ANTES de rechazar, compara el día pedido con la lista de días disponibles y la hora con el horario: si calza, ESTÁ disponible y NO lo rechaces (aunque antes en la conversación hayas rechazado otro día).' : '') : '',
    '- Para agendar solo necesitas: **' + datos + '** (el motivo es opcional). **NO pidas el nombre del local/negocio.**',
    '- Si FALTAN datos, pídelos' + (pideCorreo ? (ust ? " ('¿para qué fecha y hora? ¿a qué correo le envío la invitación?')." : " ('¿para qué fecha y hora? ¿a qué correo te envío la invitación?').") : (ust ? " ('¿para qué fecha y hora le acomoda?')." : " ('¿para qué fecha y hora te acomoda?').")),
    "- **PROHIBIDO afirmar que agendaste.** Cuando el cliente da " + datos + ", tu ÚNICA respuesta permitida es EXACTAMENTE algo como: 'Perfecto, coordino la " + tipo + " y " + (ust ? 'le' : 'te') + " llega la confirmación en un momento 😊'. NUNCA digas 'quedó agendada', 'está agendada', 'te envié la invitación', 'nos vemos ahí' ni menciones la hora como confirmada — el SISTEMA agenda y confirma él mismo justo después de tu mensaje. Si tú también confirmas, el cliente recibe DOS confirmaciones (mala experiencia). Solo di que estás coordinando, nada más.",
    '- NO uses las tools de calendario tú mismo; el sistema se encarga.',
    '- Tú NO conoces la disponibilidad del calendario: NUNCA digas que un horario está ocupado o no disponible, ni propongas otra hora por tu cuenta, salvo que el día u hora pedidos estén FUERA de los días/horario indicados arriba. Si el cliente dio los datos necesarios, responde SOLO la frase de coordinación.'
  ].filter(Boolean).join('\n');
}

const menuDef = {
  texto_owner: 'Hola 👋 ¿Qué necesita? Elija una opción o escríbame directo (ej: "ventas de enero", "top productos").',
  texto_cliente: 'Hola 👋 ¿En qué le ayudo? Elija una opción o escríbame su consulta.',
  botones_owner: [{ id: 'ventas_periodo', title: 'Ventas' }, { id: 'buscar_producto', title: 'Buscar producto' }, { id: 'agendar', title: 'Agendar reunión' }],
  botones_cliente: [{ id: 'ver_productos', title: 'Ver productos' }, { id: 'precios', title: 'Precios' }, { id: 'agendar', title: 'Agendar' }]
};
const perfilMenu = {
  texto_owner: t(menu.texto_owner, menuDef.texto_owner),
  texto_cliente: t(menu.texto_cliente, menuDef.texto_cliente),
  botones_owner: Array.isArray(menu.botones_owner) && menu.botones_owner.length ? menu.botones_owner.slice(0, 3) : menuDef.botones_owner,
  botones_cliente: Array.isArray(menu.botones_cliente) && menu.botones_cliente.length ? menu.botones_cliente.slice(0, 3) : menuDef.botones_cliente
};

return [{ json: {
  empresa: ctx.empresa,
  nombre_empresa: ctx.nombre_empresa,
  nombre_asistente: ctx.nombre_asistente,
  rol: ctx.rol,
  rut_cliente: ctx.rut_cliente,
  from: ctx.from,
  phone_number_id: ctx.phone_number_id,
  user_message: ctx.user_message,
  message_id: ctx.message_id,
  history,
  ficha_cliente: fichaCliente,
  history_text: historyText || '(sin historial previo)',
  config: cfg,
  negocio_configurado: cfg.configurado === true || (cfg.configurado !== false && !!t(neg.descripcion, '')),
  perfil: { descripcion, catalogo, categorias_menu, escalamiento, tono: tonoTxt, info_negocio, categorias_interes, agenda, menu: perfilMenu, calendar_id: String(ag.calendar_id || 'primary'), fuente_catalogo: String(((cfg.fuentes || {}).catalogo || {}).tipo || 'erp_supabase') }
}}];