// Puntaje con pesos fijos + SQL de guardado (valores saneados: números con Number(), textos con '' escapado).
let d;
try { d = JSON.parse($json.choices[0].message.content); } catch (e) { return []; }
const PI = { compra: 40, cotizacion: 35, agendar: 30, consulta_producto: 20, soporte_postventa: 5 };
const puntos = {
  intencion: PI[d.intencion] || 0,
  categoria: d.categoria ? 10 : 0,
  cantidad: d.cantidad ? 15 : 0,
  negocio: d.es_negocio ? 15 : 0,
  urgencia: d.urgencia === 'alta' ? 15 : d.urgencia === 'media' ? 8 : 0,
  pide_humano: d.pide_humano ? 5 : 0,
};
const score = Math.min(100, Object.values(puntos).reduce((a, b) => a + b, 0));
const registrar = ['compra', 'cotizacion', 'consulta_producto', 'agendar'].includes(d.intencion) && !!(d.categoria || d.cantidad);

const ctx = $('Consolidar contexto').first().json;
const emp = Number(ctx.empresa);
const cid = Number(String(ctx.from || '').replace(/[^0-9]/g, ''));
if (!emp || !cid) return [];
const esc = (s) => String(s).replace(/'/g, "''");
const det = esc(JSON.stringify({ ...d, puntos, modelo: 'gpt-4o-mini' }));
const prod = d.categoria ? "'" + esc(String(d.categoria).slice(0, 60)) + "'" : 'null';
const viejo = "crm.crm_leads.score is null or crm.crm_leads.score_at < now() - interval '14 days'";
const sql = `insert into crm.crm_leads (empresa, contact_id, phone, producto_interes, estado_crm, origen_lead, bot_activo, score, score_detalle, score_at)
select ${emp}, ${cid}, ${cid}, ${prod}, 'Nuevo Lead', 'WhatsApp (IA)', true, ${score}, '${det}'::jsonb, now()
where ${registrar} or exists (select 1 from crm.crm_leads where empresa = ${emp} and contact_id = ${cid})
on conflict (empresa, contact_id) do update set
  score = case when ${viejo} then excluded.score else greatest(crm.crm_leads.score, excluded.score) end,
  score_detalle = case when ${viejo} or excluded.score >= crm.crm_leads.score then excluded.score_detalle else crm.crm_leads.score_detalle end,
  score_at = now(),
  producto_interes = coalesce(crm.crm_leads.producto_interes, excluded.producto_interes)
returning id, score;`;
return [{ json: { score, registrar, puntos, clasificacion: d, sql } }];