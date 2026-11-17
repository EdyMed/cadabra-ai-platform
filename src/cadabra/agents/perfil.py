"""Convierte la ficha JSONB de la empresa en los textos que usa el prompt.

Traducción directa del nodo "Consolidar contexto" de n8n: cada bloque tiene un texto por defecto genérico y la
ficha puede reemplazarlo. Si cambias algo aquí, el agente responde distinto: mantener en paridad con n8n
mientras convivan.
"""
from dataclasses import dataclass, field
from typing import Any

DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]

MENU_POR_DEFECTO = {
    "texto_owner": 'Hola 👋 ¿Qué necesita? Elija una opción o escríbame directo (ej: "ventas de enero", "top productos").',
    "texto_cliente": "Hola 👋 ¿En qué le ayudo? Elija una opción o escríbame su consulta.",
    "botones_owner": [
        {"id": "ventas_periodo", "title": "Ventas"},
        {"id": "buscar_producto", "title": "Buscar producto"},
        {"id": "agendar", "title": "Agendar reunión"},
    ],
    "botones_cliente": [
        {"id": "ver_productos", "title": "Ver productos"},
        {"id": "precios", "title": "Precios"},
        {"id": "agendar", "title": "Agendar"},
    ],
}


@dataclass(frozen=True)
class Perfil:
    descripcion: str
    catalogo: str
    categorias_menu: str
    escalamiento: str
    tono: str
    info_negocio: str
    categorias_interes: str
    agenda: str
    fuente_catalogo: str
    menu: dict[str, Any] = field(default_factory=dict)


def _texto(valor: Any, por_defecto: str) -> str:
    """El valor si es un texto con contenido; si no, el texto por defecto."""
    return valor.strip() if isinstance(valor, str) and valor.strip() else por_defecto


def construir_perfil(config: dict[str, Any], asistente: str, empresa: str) -> Perfil:
    def sub(s: str) -> str:
        return str(s or "").replace("{asistente}", asistente).replace("{empresa}", empresa)

    neg = config.get("negocio") or {}
    cat = config.get("catalogo") or {}
    tono = config.get("tono") or {}
    ag = config.get("agenda") or {}
    menu = config.get("menu") or {}
    interes = config.get("interes") or {}

    descripcion = (
        ", " + sub(neg["descripcion"])
        if _texto(neg.get("descripcion"), "")
        else ". Respondes consultas de productos y precios, ayudas a tus clientes y agendas citas, "
        "siempre usando las HERRAMIENTAS disponibles."
    )
    categorias_menu = _texto(cat.get("categorias_menu"), "las categorías de nuestro catálogo")

    return Perfil(
        descripcion=descripcion,
        catalogo=sub(_catalogo(cat, categorias_menu)),
        categorias_menu=categorias_menu,
        escalamiento=sub(_texto(
            config.get("escalamiento"),
            "Ofrece derivar a un vendedor cuando: el cliente quiera cerrar un pedido, negociar precios o condiciones, "
            "haya un reclamo, o lleves 3 turnos sin resolver su necesidad.",
        )),
        tono=sub(_tono(tono)),
        info_negocio=_info_negocio(neg, config.get("faq"), sub),
        categorias_interes=", ".join(
            c["nombre"] for c in (interes.get("categorias") or []) if isinstance(c, dict) and c.get("nombre")
        ) or "Otro",
        agenda=_agenda(ag, tono),
        fuente_catalogo=str(((config.get("fuentes") or {}).get("catalogo") or {}).get("tipo") or "erp_supabase"),
        menu=_menu(menu),
    )


def negocio_configurado(config: dict[str, Any]) -> bool:
    if config.get("configurado") is True:
        return True
    return config.get("configurado") is not False and bool(_texto((config.get("negocio") or {}).get("descripcion"), ""))


def ficha_cliente(lead: dict[str, Any] | None) -> str:
    """Lo que el CRM sabe del contacto, en líneas "- Campo: valor"."""
    if not lead:
        return "(Sin ficha en el CRM: es un contacto nuevo o todavía no mostró interés de compra.)"

    def v(x: Any) -> str | None:
        return str(x).strip() if x is not None and str(x).strip() else None

    cita = None
    if v(lead.get("fecha_cita")):
        cita = lead["fecha_cita"]
        if v(lead.get("hora_cita")):
            cita += " " + lead["hora_cita"]
        if v(lead.get("agenda")):
            cita += f" ({lead['agenda']})"
    filas = [
        ("Nombre", v(lead.get("nombre"))), ("Negocio", v(lead.get("negocio"))),
        ("Producto de interés", v(lead.get("producto"))), ("Etapa comercial", v(lead.get("estado"))),
        ("Comuna", v(lead.get("comuna"))), ("Vendedor asignado", v(lead.get("vendedor"))),
        ("Cita", cita), ("Cliente desde", v(lead.get("desde"))),
    ]
    lineas = [f"- {k}: {x}" for k, x in filas if x]
    return "\n".join(lineas) if lineas else "(Ficha en el CRM sin datos todavía.)"


# ---- bloques del perfil ---------------------------------------------------------------------------------------

def _catalogo(cat: dict[str, Any], categorias_menu: str) -> str:
    if _texto(cat.get("texto"), ""):
        return cat["texto"].strip()
    lineas = [
        "## Catálogo — cómo atender consultas de productos",
        f"- Categorías principales del negocio: {categorias_menu}.",
        '- Si el cliente pregunta en general ("qué venden", "qué productos tienes"), menciona brevemente esas '
        "categorías y pregúntale cuál quiere ver CON PRECIO. No recites productos de memoria.",
        '- Cuando elija una categoría o nombre un producto, usa stock_producto pasando SOLO la(s) palabra(s) clave '
        '(sin relleno como "de" o "por favor"). Si da vacío, reintenta con una palabra más general antes de decir '
        "que no hay.",
        "- DISPONIBILIDAD: " + _texto(
            cat.get("disponibilidad"),
            "los productos que devuelve la herramienta están disponibles; para pedidos grandes o urgentes, sugiere "
            "confirmar con un vendedor.",
        ),
    ]
    if _texto(cat.get("unidad"), ""):
        lineas.append(f"- Unidad de venta: {cat['unidad']}. Si no especifican, aclara la unidad.")
    for s in cat.get("sinonimos") or []:
        if isinstance(s, dict) and s.get("dice") and s.get("buscar"):
            lineas.append(f'- Si el cliente dice "{s["dice"]}" → busca "{s["buscar"]}".')
    return "\n".join(lineas)


def _tono(tono: dict[str, Any]) -> str:
    if _texto(tono.get("texto"), ""):
        return tono["texto"].strip()
    usted = tono.get("trato") == "usted"
    saludo_def = (
        "'¡Hola! 😊 Soy {asistente}, de {empresa}. ¿En qué le puedo ayudar?'" if usted
        else "'¡Hola! 😊 Soy {asistente}. Cuéntame, ¿en qué te puedo ayudar?'"
    )
    return "\n".join([
        "Habla cordial y respetuoso, tratando al cliente SIEMPRE de USTED (nunca de tú). IMPORTANTE: aunque los "
        "ejemplos de estas instrucciones estén escritos en tú, TÚ respondes siempre de usted (\"¿Le gustaría…?\", "
        "\"le muestro\", \"¿en qué le ayudo?\"). Cálido pero profesional." if usted else
        "Habla CERCANO Y NATURAL, tuteando al cliente (de TÚ, no de usted). Cálido pero profesional, sin sonar "
        "acartonado.",
        '- Frases CORTAS y directas. Evita fórmulas rígidas ("no dude en", "hágamelo saber").',
        "- Saludo/bienvenida en el primer mensaje: " + _texto(tono.get("saludo"), saludo_def),
        "- Emojis con moderación (" + _texto(tono.get("emojis"), "😊") + "), no en cada frase.",
        "- Respuestas BREVES para WhatsApp: máximo 4-5 frases.",
        "- Formatea montos en pesos chilenos: $1.234 (punto de miles, sin decimales).",
        "- Muestra los productos con el nombre tal como viene del catálogo (stock_producto).",
    ])


def _info_negocio(neg: dict[str, Any], faq: Any, sub) -> str:
    info = []
    campos = [
        ("horario", "- Horario de atención: {}."), ("direccion", "- Dirección: {}."),
        ("despacho", "- Despacho / delivery: {}"), ("pagos", "- Medios de pago: {}"),
        ("pedido_minimo", "- Pedido mínimo: {}"), ("politicas", "- Políticas: {}"),
        ("no_prometer", "- NUNCA prometas: {}"),
    ]
    for clave, formato in campos:
        if _texto(neg.get(clave), ""):
            info.append(formato.format(neg[clave]))
    for f in faq or []:
        if isinstance(f, dict) and f.get("p") and f.get("r"):
            info.append(f'- Si preguntan "{f["p"]}" → {f["r"]}')
    if not info:
        return ""
    return "## Información del negocio (úsala para responder; no inventes nada fuera de esto)\n" + sub("\n".join(info))


def _agenda(ag: dict[str, Any], tono: dict[str, Any]) -> str:
    if ag.get("activa") is False:
        return ("## AGENDA\nEste negocio NO agenda citas por WhatsApp. Si el cliente quiere agendar, ofrécele que un "
                "vendedor lo contacte para coordinar. NO uses las tools de calendario.")
    tipo = _texto(ag.get("tipo"), "reunión")
    usted = tono.get("trato") == "usted"
    pide_correo = ag.get("pide_correo") is not False
    datos = "fecha, hora y correo" if pide_correo else "fecha y hora"
    dias = ag.get("dias") if isinstance(ag.get("dias"), list) else []
    restringido = bool(dias) or bool(ag.get("hora_inicio") and ag.get("hora_fin"))

    horario = ""
    if dias:
        horario += "Días disponibles: " + ", ".join(DIAS[d] for d in dias if isinstance(d, int) and 0 <= d < 7) + ". "
    if ag.get("hora_inicio") and ag.get("hora_fin"):
        horario += f"Horario: de {ag['hora_inicio']} a {ag['hora_fin']} hrs. "
    if ag.get("duracion_min"):
        horario += f"Cada {tipo} dura {ag['duracion_min']} minutos. "
    if ag.get("anticipacion_horas"):
        horario += f"Se agenda con al menos {ag['anticipacion_horas']} horas de anticipación. "
    if ag.get("lugar"):
        horario += f"Lugar: {ag['lugar']}. "

    if pide_correo:
        pedir = (" ('¿para qué fecha y hora? ¿a qué correo le envío la invitación?')." if usted
                 else " ('¿para qué fecha y hora? ¿a qué correo te envío la invitación?').")
    else:
        pedir = " ('¿para qué fecha y hora le acomoda?')." if usted else " ('¿para qué fecha y hora te acomoda?')."

    lineas = [
        f"## AGENDAR {tipo.upper()} — EL SISTEMA LA CREA, TÚ SOLO PIDES LOS DATOS",
        f"El sistema agenda la {tipo} AUTOMÁTICAMENTE en segundo plano cuando tiene {datos}. Tu única tarea es "
        "RECOPILAR esos datos con naturalidad.",
        ("- " + horario.strip() + (
            " Si el cliente pide un día u hora fuera de esto, explícale con amabilidad y ofrécele otra opción dentro "
            "del horario. ANTES de rechazar, compara el día pedido con la lista de días disponibles y la hora con el "
            "horario: si calza, ESTÁ disponible y NO lo rechaces (aunque antes en la conversación hayas rechazado "
            "otro día)." if restringido else "")) if horario else "",
        f"- Para agendar solo necesitas: **{datos}** (el motivo es opcional). **NO pidas el nombre del local/negocio.**",
        "- Si FALTAN datos, pídelos" + pedir,
        f"- **PROHIBIDO afirmar que agendaste.** Cuando el cliente da {datos}, tu ÚNICA respuesta permitida es "
        f"EXACTAMENTE algo como: 'Perfecto, coordino la {tipo} y {'le' if usted else 'te'} llega la confirmación en un "
        "momento 😊'. NUNCA digas 'quedó agendada', 'está agendada', 'te envié la invitación', 'nos vemos ahí' ni "
        "menciones la hora como confirmada — el SISTEMA agenda y confirma él mismo justo después de tu mensaje. Si tú "
        "también confirmas, el cliente recibe DOS confirmaciones (mala experiencia). Solo di que estás coordinando, "
        "nada más.",
        "- NO uses las tools de calendario tú mismo; el sistema se encarga.",
        "- Tú NO conoces la disponibilidad del calendario: NUNCA digas que un horario está ocupado o no disponible, ni "
        "propongas otra hora por tu cuenta, salvo que el día u hora pedidos estén FUERA de los días/horario indicados "
        "arriba. Si el cliente dio los datos necesarios, responde SOLO la frase de coordinación.",
    ]
    return "\n".join(x for x in lineas if x)


def _menu(menu: dict[str, Any]) -> dict[str, Any]:
    def botones(clave: str) -> list[dict[str, str]]:
        b = menu.get(clave)
        return b[:3] if isinstance(b, list) and b else MENU_POR_DEFECTO[clave]

    return {
        "texto_owner": _texto(menu.get("texto_owner"), MENU_POR_DEFECTO["texto_owner"]),
        "texto_cliente": _texto(menu.get("texto_cliente"), MENU_POR_DEFECTO["texto_cliente"]),
        "botones_owner": botones("botones_owner"),
        "botones_cliente": botones("botones_cliente"),
    }
