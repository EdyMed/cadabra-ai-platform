const ctx = $('Consolidar contexto').first().json;
// Analizar el mensaje ACTUAL + el historial reciente del cliente (por el buffer,
// un turno puede ser corto como 'de pino'; el interés/producto puede estar en turnos previos).
const histUser = (ctx.history || []).filter(h => h.role === 'user').map(h => h.content).join(' ');
const msg = ((histUser + ' ' + (ctx.user_message || ''))).toLowerCase();
const wa = ctx.from;
// Detectar producto por palabras clave del catálogo real
const cfgI = (ctx.config && ctx.config.interes) || {};
const cats = Array.isArray(cfgI.categorias) ? cfgI.categorias : [];
let producto = null;
for (const c of cats) { try { if (c && c.regex && new RegExp(c.regex, 'i').test(msg)) { producto = c.nombre; break; } } catch (e) { /* regex inválida en la ficha */ } }
// Señales de interés comercial: base genérica + las del rubro (ficha)
let interes = /(precio|valor|cu[aá]nto|cotiza|comprar|pedido|encargo|reserva|disponib|stock)/.test(msg);
if (!interes && cfgI.senales) { try { interes = new RegExp(cfgI.senales, 'i').test(msg); } catch (e) {} }
// Sin categorías en la ficha, el interés comercial basta para registrarlo como 'Otro'
if (!producto && interes && cats.length === 0) producto = 'Otro';
// Petición de HANDOFF a humano (mira SOLO el mensaje actual, no el historial)
const msgActual = (ctx.user_message || '').toLowerCase();
const pideHumano = /(vendedor|hablar con (alguien|una persona|un humano|un ejecutivo|un asesor)|con una persona|atenci[oó]n humana|asesor|ejecutivo)/.test(msgActual);
// ¿El ÚLTIMO mensaje del bot pidió el NOMBRE? Entonces la respuesta del cliente ES el nombre.
const hist = ctx.history || [];
let ultimoBot = '';
for (let i = hist.length - 1; i >= 0; i--) { if (hist[i].role === 'assistant') { ultimoBot = (hist[i].content||'').toLowerCase(); break; } }
const botPidioNombre = /(a nombre de qui[eé]n|con qui[eé]n tengo el gusto|nombre de la persona|c[oó]mo te llamas|tu nombre|qui[eé]n eres|a qui[eé]n anoto)/.test(ultimoBot);
// Capturar nombre: el mensaje actual del cliente, limpio (quitar 'soy', 'me llamo', 'local', etc.)
let nombreCap = null, negocioCap = null;
if (botPidioNombre) {
  const t = (ctx.user_message || '').trim();
  // separar posible 'nombre, local X' o 'nombre y el local es X'
  let resto = t;
  // 1) extraer el NEGOCIO si viene con marcador explícito ('local X', 'negocio X', 'mi local es X', 'del local X')
  const mNeg = t.match(/(?:mi\s+)?(?:local|negocio|tienda|restaurant\w*|caf[eé]|almac[eé]n|sushi|kiosco|food ?truck)\s+(?:se\s+llama\s+|es\s+|:\s*)?([\wáéíóúñ' ]{2,40})/i);
  if (mNeg) { negocioCap = mNeg[1].trim(); resto = t.replace(mNeg[0], '').trim(); }
  // 2) el NOMBRE es lo que queda antes de una coma/marcador (quitar prefijos 'soy', 'me llamo')
  resto = resto.replace(/[,;].*$/, '').trim();
  resto = resto.replace(/^(hola\s+)?(soy|me llamo|mi nombre es|es|soy el|soy la)\s+/i, '').trim();
  resto = resto.replace(/\s+(del|de la|de|el|la)\s*$/i, '').trim();
  // si tras quitar el negocio no queda nombre (ej. 'local los tres cerditos'), nombre queda null
  if (resto && resto.length >= 2 && resto.length <= 30 && !/^(local|negocio|el|la|los|las)$/i.test(resto)) nombreCap = resto;
  // capitalizar
  const _min = new Set(['de','del','la','las','los','el','y','o','a','en','con','por','para','un','una']);
  const cap = s => (s||'').split(/\s+/).map((w,i) => { if(!w) return w; const l=w.toLowerCase(); if(i>0 && _min.has(l)) return l; return w.charAt(0).toUpperCase()+w.slice(1); }).join(' ');
  if (nombreCap) nombreCap = cap(nombreCap);
  if (negocioCap) negocioCap = cap(negocioCap);
}
// ¿Estamos en un handoff pendiente? (la ficha ya está en Requiere Vendedor o el bot pidió nombre tras pedir vendedor)
const enHandoff = /(vendedor|pasar con|te contact|a la brevedad)/.test(ultimoBot);

const debeRegistrar = (!!producto && interes && !!wa) || (pideHumano && !!wa) || (botPidioNombre && !!nombreCap && !!wa);
const body = { contact_id: wa, phone: wa, origen_lead: 'whatsapp' };
if (producto) body.producto_interes = producto;
if (nombreCap) body.nombre = nombreCap;
if (negocioCap) body.nombre_negocio = negocioCap;
if (pideHumano) { body.estado_crm = 'Requiere Vendedor'; }
// Si el bot pidió nombre en contexto de handoff y el cliente lo dio → guardar + CORTAR (bot_activo=false)
if (botPidioNombre && nombreCap && enHandoff) { body.estado_crm = 'Requiere Vendedor'; body.bot_activo = false; }
if (!body.estado_crm) body.estado_crm = 'En Conversación';
return [{ json: Object.assign({ debeRegistrar, pideHumano, capturoNombre: !!nombreCap, corte: (botPidioNombre && nombreCap && enHandoff) }, body) }];