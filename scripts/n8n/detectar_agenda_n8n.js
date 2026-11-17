const ctx = $('Consolidar contexto').first().json;
const hist = ctx.history || [];
// texto = últimos turnos del USUARIO + mensaje actual (los datos pueden venir repartidos)
const histUser = hist.filter(h => h.role==='user').slice(-4).map(h=>h.content).join(' \n ');
const full = (histUser + ' \n ' + (ctx.user_message||''));
// INTENCIÓN: puede venir del historial. Pero los DATOS (hora/fecha/correo/motivo)
// se extraen SOLO del mensaje ACTUAL (si no, agarra la hora de una reunión anterior).
const low = (ctx.user_message||'').toLowerCase();
const lowFull = full.toLowerCase();
const wa = ctx.from;
// ¿hay intención de agendar? (mira historial + actual)
const ag = (ctx.config && ctx.config.agenda) || {};
if (ag.activa === false) return [{ json: { agendar:false, motivo:'agenda desactivada' } }];
const tipoAg = String(ag.tipo || 'reunión');
const quiereAgendar = /(agendar|agenda|reuni[oó]n|reunirnos|c[ií]ta|juntarnos|reservar hora|hora para)/.test(lowFull) || lowFull.includes(tipoAg.toLowerCase());
if (!quiereAgendar) return [{ json: { agendar:false, motivo:'sin intencion' } }];

// --- extraer CORREO (solo del mensaje actual) ---
const em = (ctx.user_message||'').match(/[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}/i);
const correo = em ? em[0] : null;

// --- extraer HORA (ej 'a las 12', '12:30', 'las 3 pm') ---
let hh=null, mm=0;
let mh = low.match(/(?:a\s+las?\s+|las\s+)?(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm|hrs|horas|h)?/);
// buscar específicamente cerca de 'las' para no agarrar el '12' de otra cosa
let mh2 = low.match(/(?:a\s+las?|las)\s+(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?/);
const use = mh2 || mh;
if (use) { hh = parseInt(use[1]); mm = use[2]?parseInt(use[2]):0; const ap=use[3]; if(ap==='pm'&&hh<12)hh+=12; if(ap==='am'&&hh===12)hh=0; }

// --- extraer FECHA ---
// base: ahora en Chile
const now = new Date(new Date().toLocaleString('en-US',{timeZone:'America/Santiago'}));
let fecha = null;
if (/pasado\s+ma[ñn]ana/.test(low)) { fecha = new Date(now); fecha.setDate(fecha.getDate()+2); }
else if (/ma[ñn]ana/.test(low)) { fecha = new Date(now); fecha.setDate(fecha.getDate()+1); }
else if (/hoy/.test(low)) { fecha = new Date(now); }
else {
  // días de la semana: 'el viernes', 'este lunes', 'próximo martes' → el más cercano en el futuro
  const dias = { 'domingo':0,'lunes':1,'martes':2,'mi[eé]rcoles':3,'miercoles':3,'jueves':4,'viernes':5,'s[aá]bado':6,'sabado':6 };
  let diaSemana = null;
  for (const k in dias) { if (new RegExp('\\b'+k+'\\b').test(low)) { diaSemana = dias[k]; break; } }
  if (diaSemana !== null) {
    fecha = new Date(now);
    let delta = (diaSemana - fecha.getDay() + 7) % 7;
    if (delta === 0) delta = 7; // 'el viernes' cuando hoy es viernes = el próximo
    fecha.setDate(fecha.getDate() + delta);
  } else {
    const dm = (ctx.user_message||'').match(/(\d{1,2})[\/\-](\d{1,2})(?:[\/\-](\d{2,4}))?/);
    if(dm){ const y=dm[3]?(dm[3].length===2?2000+parseInt(dm[3]):parseInt(dm[3])):now.getFullYear(); fecha=new Date(y, parseInt(dm[2])-1, parseInt(dm[1])); }
  }
}

// --- MOTIVO: quitar lo ya parseado, tomar frase de motivo ---
let motivo = 'Reunión';
const mm2 = low.match(/(?:motivo|para|sobre|por)\s+([\wáéíóúñ ]{3,60})/);
const _min = new Set(['de','del','la','las','los','el','y','o','a','en','con','por','para','un','una']);
const cap = s => (s||'').split(/\s+/).map((w,i) => { if(!w) return w; const l=w.toLowerCase(); if(i>0 && _min.has(l)) return l; return w.charAt(0).toUpperCase()+w.slice(1); }).join(' ');
if (mm2) motivo = cap(mm2[1].trim());
else { const partes=(ctx.user_message||'').split(',').map(s=>s.trim()).filter(Boolean); const ult=partes[partes.length-1]; if(ult && !/@|\d{1,2}[:h]|las |ma[ñn]ana|hoy/.test(ult)) motivo=cap(ult); }

// ¿tenemos lo mínimo? fecha + hora + correo
const pideCorreo = ag.pide_correo !== false;
const completo = !!(fecha && hh!==null && (correo || !pideCorreo) && wa);
if (!completo) return [{ json: { agendar:false, incompleto:true, tiene_fecha:!!fecha, tiene_hora:hh!==null, tiene_correo:!!correo } }];
// ANTI-LOOP PRECISO: solo bloquea si en el historial YA se confirmó ESTA MISMA fecha+hora.
// (No bloquea reuniones nuevas con otra fecha/hora, aunque el historial tenga confirmaciones viejas.)
// Construir la etiqueta de esta reunión y buscar si ya se confirmó exactamente esa.

// armar inicio/fin (1 hora) en formato local SIN zona (el nodo aplica America/Santiago)
const pad=n=>String(n).padStart(2,'0');
const y=fecha.getFullYear(), mo=pad(fecha.getMonth()+1), d=pad(fecha.getDate());
const inicio = `${y}-${mo}-${d}T${pad(hh)}:${pad(mm)}:00`;
// duración y horario permitido desde la ficha de la empresa
const durMin = Number(ag.duracion_min) || 60;
const finDate = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), hh, mm + durMin);
const fin = `${finDate.getFullYear()}-${pad(finDate.getMonth()+1)}-${pad(finDate.getDate())}T${pad(finDate.getHours())}:${pad(finDate.getMinutes())}:00`;
const DIAS = ['domingo','lunes','martes','miércoles','jueves','viernes','sábado'];
const hm = s => { const m = String(s||'').match(/(\d{1,2}):(\d{2})/); return m ? parseInt(m[1])*60 + parseInt(m[2]) : null; };
const iniLim = hm(ag.hora_inicio), finLim = hm(ag.hora_fin), t0 = hh*60 + mm, t1 = t0 + durMin;
const diasOk = !Array.isArray(ag.dias) || !ag.dias.length || ag.dias.includes(fecha.getDay());
const horaOk = iniLim === null || finLim === null || (t0 >= iniLim && t1 <= finLim);
const antMs = (Number(ag.anticipacion_horas) || 0) * 3600000;
const cuando = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate(), hh, mm);
const antOk = cuando.getTime() - now.getTime() >= antMs;
if (!diasOk || !horaOk || !antOk) {
  const dTxt = Array.isArray(ag.dias) && ag.dias.length ? ag.dias.map(x => DIAS[x]).join(', ') : 'todos los días';
  const hTxt = (iniLim !== null && finLim !== null) ? ` de ${ag.hora_inicio} a ${ag.hora_fin} hrs` : '';
  const aTxt = antMs ? ` y con al menos ${ag.anticipacion_horas} horas de anticipación` : '';
  const usted = !!(ctx.config && ctx.config.tono && ctx.config.tono.trato === 'usted');
  return [{ json: { agendar:false, fuera_horario:true, wa, aviso: `Uy, ese horario no lo tengo disponible 😕. Agendo ${dTxt}${hTxt}${aTxt}. ¿Qué otro día u hora ${usted ? 'le' : 'te'} acomoda?` } }];
}
// ANTI-LOOP PRECISO: bloquear solo si el bot YA confirmó ('te agendé/agendada') Y menciona
// esta MISMA fecha en el historial. Reuniones con otra fecha SÍ se agendan.
const histBot = hist.filter(h=>h.role==='assistant').map(h=>(h.content||'').toLowerCase()).join(' || ');
const fechaStr = `${y}-${mo}-${d}`;
const confirmoAntes = /(te agend[ée]|reuni[oó]n .{0,30}agendada)/.test(histBot);
const mismaFecha = histBot.includes(fechaStr);
if (confirmoAntes && mismaFecha) return [{ json: { agendar:false, motivo:'ya_agendada_misma_fecha' } }];
const correoNeg = ag.correo_negocio ? String(ag.correo_negocio).trim() : null;
const attendees = [correo, correoNeg].filter(Boolean);
const tipoCap = tipoAg.charAt(0).toUpperCase() + tipoAg.slice(1);
const titulo = (motivo && motivo !== 'Reunión') ? `${tipoCap}: ${motivo}` : `${tipoCap} con cliente WhatsApp +${wa}`;
const descripcion = `${motivo === 'Reunión' ? tipoCap : motivo}\nCliente WhatsApp: +${wa}` + (correo ? `\nCorreo: ${correo}` : '') + `\nAgendado por ${ctx.nombre_asistente || 'el asistente'} (${ctx.nombre_empresa || ''})`;
return [{ json: { agendar:true, wa, correo, inicio, fin, motivo, titulo, descripcion, attendees, calendar_id: String(ag.calendar_id || 'primary'), lugar: ag.lugar || '', tipo: tipoAg, mensaje_ok: ag.mensaje_confirmacion || '' } }];