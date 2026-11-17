"""Detecciones automáticas después de cada turno (sin modelo de IA, solo reglas).

Traducción de los nodos "Detectar interés (auto)" y "Detectar agenda (auto)" de n8n (originales en scripts/n8n/).
tests/test_paridad_n8n.py ejecuta el JavaScript original y compara: si cambias una regla, cámbiala en ambos lados.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cadabra.agents.perfil import DIAS

# ---- interés comercial, pedido de humano y captura de nombre ------------------------------------------------

SENALES_BASE = re.compile(r"(precio|valor|cu[aá]nto|cotiza|comprar|pedido|encargo|reserva|disponib|stock)")
PIDE_HUMANO = re.compile(r"(vendedor|hablar con (alguien|una persona|un humano|un ejecutivo|un asesor)|con una persona"
                         r"|atenci[oó]n humana|asesor|ejecutivo)")
BOT_PIDIO_NOMBRE = re.compile(r"(a nombre de qui[eé]n|con qui[eé]n tengo el gusto|nombre de la persona|c[oó]mo te llamas"
                              r"|tu nombre|qui[eé]n eres|a qui[eé]n anoto)")
MARCADOR_NEGOCIO = re.compile(r"(?:mi\s+)?(?:local|negocio|tienda|restaurant[A-Za-z0-9_]*|caf[eé]|almac[eé]n|sushi"
                              r"|kiosco|food ?truck)\s+(?:se\s+llama\s+|es\s+|:\s*)?([A-Za-z0-9_áéíóúñ' ]{2,40})", re.I)
EN_HANDOFF = re.compile(r"(vendedor|pasar con|te contact|a la brevedad)")
MINUSCULAS = {"de", "del", "la", "las", "los", "el", "y", "o", "a", "en", "con", "por", "para", "un", "una"}


def capitalizar(texto: str) -> str:
    palabras = re.split(r"\s+", texto or "")
    return " ".join(
        p if not p else (p.lower() if i > 0 and p.lower() in MINUSCULAS else p[0].upper() + p[1:])
        for i, p in enumerate(palabras)
    )


def _ultimo_del_bot(historial: list[dict[str, str]]) -> str:
    for h in reversed(historial):
        if h.get("role") == "assistant":
            return (h.get("content") or "").lower()
    return ""


def _regex_ficha(patron: str, texto: str) -> bool:
    """Regex escrita en la ficha de la empresa: si es inválida, no detecta (igual que n8n)."""
    try:
        return re.search(patron, texto, re.I) is not None
    except re.error:
        return False


def detectar_interes(config: dict[str, Any], mensaje: str, historial: list[dict[str, str]], telefono: str) -> dict:
    """¿Registrar el lead? ¿Pidió un humano? ¿Dio su nombre después de que el bot se lo pidió (corte)?"""
    mensajes_cliente = " ".join(h["content"] for h in historial if h.get("role") == "user")
    texto = (mensajes_cliente + " " + (mensaje or "")).lower()

    cfg = config.get("interes") or {}
    categorias = cfg.get("categorias") if isinstance(cfg.get("categorias"), list) else []
    producto = next((c["nombre"] for c in categorias
                     if isinstance(c, dict) and c.get("regex") and _regex_ficha(c["regex"], texto)), None)
    interes = SENALES_BASE.search(texto) is not None
    if not interes and cfg.get("senales"):
        interes = _regex_ficha(cfg["senales"], texto)
    if not producto and interes and not categorias:
        producto = "Otro"

    pide_humano = PIDE_HUMANO.search((mensaje or "").lower()) is not None
    ultimo_bot = _ultimo_del_bot(historial)
    bot_pidio_nombre = BOT_PIDIO_NOMBRE.search(ultimo_bot) is not None

    nombre = negocio = None
    if bot_pidio_nombre:
        t = (mensaje or "").strip()
        resto = t
        m = MARCADOR_NEGOCIO.search(t)
        if m:
            negocio = m.group(1).strip()
            resto = t.replace(m.group(0), "", 1).strip()
        resto = re.sub(r"[,;].*$", "", resto, count=1).strip()
        resto = re.sub(r"^(hola\s+)?(soy|me llamo|mi nombre es|es|soy el|soy la)\s+", "", resto, count=1, flags=re.I).strip()
        resto = re.sub(r"\s+(del|de la|de|el|la)\s*$", "", resto, count=1, flags=re.I).strip()
        if resto and 2 <= len(resto) <= 30 and not re.fullmatch(r"(local|negocio|el|la|los|las)", resto, re.I):
            nombre = capitalizar(resto)
        if negocio:
            negocio = capitalizar(negocio)

    en_handoff = EN_HANDOFF.search(ultimo_bot) is not None
    corte = bot_pidio_nombre and nombre and en_handoff   # como en JS: puede quedar None (falso)

    datos: dict[str, Any] = {"contact_id": telefono, "phone": telefono, "origen_lead": "whatsapp"}
    if producto:
        datos["producto_interes"] = producto
    if nombre:
        datos["nombre"] = nombre
    if negocio:
        datos["nombre_negocio"] = negocio
    if pide_humano:
        datos["estado_crm"] = "Requiere Vendedor"
    if corte:
        datos["estado_crm"] = "Requiere Vendedor"
        datos["bot_activo"] = False
    datos.setdefault("estado_crm", "En Conversación")

    debe_registrar = bool((producto and interes and telefono) or (pide_humano and telefono)
                          or (bot_pidio_nombre and nombre and telefono))
    return {"debeRegistrar": debe_registrar, "pideHumano": pide_humano, "capturoNombre": bool(nombre),
            "corte": corte, **datos}


# ---- agenda --------------------------------------------------------------------------------------------------

QUIERE_AGENDAR = re.compile(r"(agendar|agenda|reuni[oó]n|reunirnos|c[ií]ta|juntarnos|reservar hora|hora para)")
CORREO = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
HORA_LIBRE = re.compile(r"(?:a\s+las?\s+|las\s+)?(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm|hrs|horas|h)?")
HORA_LAS = re.compile(r"(?:a\s+las?|las)\s+(\d{1,2})(?:[:\.](\d{2}))?\s*(am|pm)?")
DIAS_TEXTO = [("domingo", 0), ("lunes", 1), ("martes", 2), ("mi[eé]rcoles", 3), ("miercoles", 3), ("jueves", 4),
              ("viernes", 5), ("s[aá]bado", 6), ("sabado", 6)]
FECHA_NUM = re.compile(r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{2,4}))?")
MOTIVO = re.compile(r"(?:motivo|para|sobre|por)\s+([A-Za-z0-9_áéíóúñ ]{3,60})")
NO_ES_MOTIVO = re.compile(r"@|\d{1,2}[:h]|las |ma[ñn]ana|hoy")
YA_CONFIRMO = re.compile(r"(te agend[ée]|reuni[oó]n .{0,30}agendada)")


@dataclass(frozen=True)
class ContextoDeteccion:
    config: dict[str, Any]
    mensaje: str
    historial: list[dict[str, str]]
    telefono: str
    nombre_asistente: str
    nombre_empresa: str


def _dia_js(d: datetime) -> int:
    """Día de la semana como getDay() de JavaScript (domingo = 0)."""
    return (d.weekday() + 1) % 7


def _fecha(mensaje: str, ahora: datetime) -> datetime | None:
    low = mensaje.lower()
    if re.search(r"pasado\s+ma[ñn]ana", low):
        return ahora + timedelta(days=2)
    if re.search(r"ma[ñn]ana", low):
        return ahora + timedelta(days=1)
    if re.search(r"hoy", low):
        return ahora
    for patron, dia in DIAS_TEXTO:
        if re.search(r"\b" + patron + r"\b", low):
            delta = (dia - _dia_js(ahora) + 7) % 7 or 7     # "el viernes" un viernes = el próximo
            return ahora + timedelta(days=delta)
    m = FECHA_NUM.search(mensaje)
    if m:
        anio = (2000 + int(m.group(3)) if len(m.group(3)) == 2 else int(m.group(3))) if m.group(3) else ahora.year
        try:
            return datetime(anio, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None     # JavaScript "corre" fechas imposibles (31/2 → 3/3); aquí se descartan
    return None


def detectar_agenda(ctx: ContextoDeteccion, ahora_local: datetime) -> dict:
    """¿El cliente ya dio fecha, hora y correo? Arma el evento, o un aviso si está fuera del horario permitido.

    `ahora_local`: hora actual de Chile SIN zona horaria (igual que el truco toLocaleString del nodo de n8n).
    """
    ag = ctx.config.get("agenda") or {}
    if ag.get("activa") is False:
        return {"agendar": False, "motivo": "agenda desactivada"}
    tipo = str(ag.get("tipo") or "reunión")
    previos = " \n ".join(h["content"] for h in [h for h in ctx.historial if h.get("role") == "user"][-4:])
    low_todo = (previos + " \n " + (ctx.mensaje or "")).lower()
    if not (QUIERE_AGENDAR.search(low_todo) or tipo.lower() in low_todo):
        return {"agendar": False, "motivo": "sin intencion"}

    mensaje = ctx.mensaje or ""
    low = mensaje.lower()
    m_correo = CORREO.search(mensaje)
    correo = m_correo.group(0) if m_correo else None

    hh: int | None = None
    mm = 0
    m_hora = HORA_LAS.search(low) or HORA_LIBRE.search(low)
    if m_hora:
        hh = int(m_hora.group(1))
        mm = int(m_hora.group(2)) if m_hora.group(2) else 0
        if m_hora.group(3) == "pm" and hh < 12:
            hh += 12
        if m_hora.group(3) == "am" and hh == 12:
            hh = 0

    fecha = _fecha(mensaje, ahora_local)

    motivo = "Reunión"
    m_motivo = MOTIVO.search(low)
    if m_motivo:
        motivo = capitalizar(m_motivo.group(1).strip())
    else:
        partes = [p.strip() for p in mensaje.split(",") if p.strip()]
        if partes and not NO_ES_MOTIVO.search(partes[-1]):
            motivo = capitalizar(partes[-1])

    pide_correo = ag.get("pide_correo") is not False
    if not (fecha and hh is not None and (correo or not pide_correo) and ctx.telefono):
        return {"agendar": False, "incompleto": True, "tiene_fecha": bool(fecha), "tiene_hora": hh is not None,
                "tiene_correo": bool(correo)}

    dia = datetime(fecha.year, fecha.month, fecha.day)
    duracion = int(ag.get("duracion_min") or 0) or 60
    cuando = dia + timedelta(hours=hh, minutes=mm)
    termino = cuando + timedelta(minutes=duracion)
    inicio = f"{dia:%Y-%m-%d}T{hh:02d}:{mm:02d}:00"
    fin = f"{termino:%Y-%m-%dT%H:%M}:00"

    def minutos(s: Any) -> int | None:
        m = re.search(r"(\d{1,2}):(\d{2})", str(s or ""))
        return int(m.group(1)) * 60 + int(m.group(2)) if m else None

    ini_lim, fin_lim = minutos(ag.get("hora_inicio")), minutos(ag.get("hora_fin"))
    t0 = hh * 60 + mm
    dias = ag.get("dias")
    dias_ok = not isinstance(dias, list) or not dias or _dia_js(dia) in dias
    hora_ok = ini_lim is None or fin_lim is None or (t0 >= ini_lim and t0 + duracion <= fin_lim)
    anticipacion = (float(ag.get("anticipacion_horas") or 0)) * 3600
    ant_ok = (cuando - ahora_local).total_seconds() >= anticipacion
    if not (dias_ok and hora_ok and ant_ok):
        d_txt = ", ".join(DIAS[x] if isinstance(x, int) and 0 <= x < 7 else "" for x in dias) \
            if isinstance(dias, list) and dias else "todos los días"
        h_txt = f" de {ag['hora_inicio']} a {ag['hora_fin']} hrs" if ini_lim is not None and fin_lim is not None else ""
        a_txt = f" y con al menos {ag['anticipacion_horas']} horas de anticipación" if anticipacion else ""
        usted = (ctx.config.get("tono") or {}).get("trato") == "usted"
        return {"agendar": False, "fuera_horario": True, "wa": ctx.telefono,
                "aviso": f"Uy, ese horario no lo tengo disponible 😕. Agendo {d_txt}{h_txt}{a_txt}. "
                         f"¿Qué otro día u hora {'le' if usted else 'te'} acomoda?"}

    hist_bot = " || ".join((h.get("content") or "").lower() for h in ctx.historial if h.get("role") == "assistant")
    if YA_CONFIRMO.search(hist_bot) and f"{dia:%Y-%m-%d}" in hist_bot:
        return {"agendar": False, "motivo": "ya_agendada_misma_fecha"}

    correo_negocio = str(ag["correo_negocio"]).strip() if ag.get("correo_negocio") else None
    tipo_cap = tipo[:1].upper() + tipo[1:]
    titulo = f"{tipo_cap}: {motivo}" if motivo and motivo != "Reunión" else f"{tipo_cap} con cliente WhatsApp +{ctx.telefono}"
    descripcion = (f"{tipo_cap if motivo == 'Reunión' else motivo}\nCliente WhatsApp: +{ctx.telefono}"
                   + (f"\nCorreo: {correo}" if correo else "")
                   + f"\nAgendado por {ctx.nombre_asistente or 'el asistente'} ({ctx.nombre_empresa or ''})")
    return {"agendar": True, "wa": ctx.telefono, "correo": correo, "inicio": inicio, "fin": fin, "motivo": motivo,
            "titulo": titulo, "descripcion": descripcion, "attendees": [x for x in (correo, correo_negocio) if x],
            "calendar_id": str(ag.get("calendar_id") or "primary"), "lugar": ag.get("lugar") or "", "tipo": tipo,
            "mensaje_ok": ag.get("mensaje_confirmacion") or ""}
