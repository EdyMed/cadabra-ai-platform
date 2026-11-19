"""Etapas propias del cliente: qué ve el agente, qué puede escribir y que la detección no retroceda leads."""
from typing import Any

from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.etapas import estado_valido, etapas_propias, texto_prompt
from cadabra.agents.perfil import construir_perfil
from cadabra.agents.prompt import armar_prompt
from cadabra.tools import crm
from cadabra.tools.base import EntornoHerramienta

CONFIG = {"etapas": [
    {"nombre": "Nuevo Lead", "fija": True},
    {"nombre": "Esperando pago", "fija": False, "id": "a",
     "criterio": "cuando confirma el pedido\n\ny dice que va a transferir"},
    {"nombre": "Solo manual", "fija": False, "id": "b"},                                  # sin criterio
    {"nombre": "Oculta", "fija": False, "id": "c", "criterio": "nunca", "oculta": True},
    {"nombre": "Cotización Enviada", "fija": False, "id": "d", "criterio": "x"},          # pisa una fija
    {"nombre": "Inactivo", "fija": True, "oculta": True},
]}


def contexto(config: dict[str, Any]) -> ContextoTurno:
    return ContextoTurno(empresa=7, nombre_empresa="Demo", nombre_asistente="Sofía", config=config,
                         perfil=construir_perfil(config, "Sofía", "Demo"), telefono="56900000001",
                         phone_number_id="PN", mensaje="hola", rol="customer")


class SesionFalsa:
    """Registra el SQL; responde que el lead existe (id 10)."""

    def __init__(self) -> None:
        self.sql: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, consulta, params=None):
        self.sql.append((str(consulta), dict(params or {})))

        class R:
            def scalar(self):
                return 10
        return R()


def test_solo_las_propias_visibles_con_criterio():
    propias = etapas_propias(CONFIG)
    assert [e.nombre for e in propias] == ["Esperando pago"]
    assert propias[0].criterio == "cuando confirma el pedido y dice que va a transferir"   # una sola línea


def test_estado_valido():
    assert estado_valido(CONFIG, "Esperando pago")
    assert estado_valido(CONFIG, "Requiere Vendedor") and estado_valido(CONFIG, "Inactivo")   # fijas siempre
    assert not estado_valido(CONFIG, "Solo manual")      # sin criterio: solo el panel la usa
    assert not estado_valido(CONFIG, "Oculta")
    assert not estado_valido(CONFIG, "Etapa inventada")
    assert not estado_valido({}, "Esperando pago")       # otra empresa sin esa etapa


def test_maximo_cuatro():
    config = {"etapas": [{"nombre": f"E{i}", "fija": False, "criterio": "c"} for i in range(6)]}
    assert len(etapas_propias(config)) == 4


def test_prompt_sin_etapas_propias_no_cambia():
    ctx = contexto({})
    assert texto_prompt({}) == ""
    assert "ETAPAS PROPIAS" not in armar_prompt(ctx, "hoy", "lunes")


def test_prompt_con_etapas_propias():
    prompt = armar_prompt(contexto(CONFIG), "hoy", "lunes")
    assert prompt.rstrip().endswith('- "Esperando pago" → criterio del negocio: cuando confirma el pedido y dice que '
                                    "va a transferir")
    assert "Solo manual" not in prompt and "Oculta" not in prompt


async def test_herramienta_mueve_a_etapa_propia():
    sesion = SesionFalsa()
    ent = EntornoHerramienta(ctx=contexto(CONFIG), sesion=sesion, whatsapp=None, ensayo=False)  # type: ignore[arg-type]
    r = await crm.actualizar_estado(ent, crm.CambioEstado(estado_crm="Esperando pago"))
    assert "aviso" not in r
    sql, params = sesion.sql[-1]
    assert "estado_crm = :estado_crm" in sql and params["estado_crm"] == "Esperando pago"


async def test_herramienta_rechaza_etapa_que_no_existe_pero_guarda_lo_demas():
    sesion = SesionFalsa()
    ent = EntornoHerramienta(ctx=contexto(CONFIG), sesion=sesion, whatsapp=None, ensayo=False)  # type: ignore[arg-type]
    r = await crm.actualizar_estado(ent, crm.CambioEstado(estado_crm="Solo manual", nombre="Pedro"))
    assert "no existe" in r["aviso"]
    sql, params = sesion.sql[-1]
    assert "estado_crm" not in sql and params["nombre"] == "Pedro"


async def test_guardar_lead_sin_etapa_no_retrocede():
    sesion = SesionFalsa()
    ent = EntornoHerramienta(ctx=contexto(CONFIG), sesion=sesion, whatsapp=None, ensayo=False)  # type: ignore[arg-type]
    await crm.guardar_lead(ent, crm.DatosLead(producto_interes="Pan"))
    sql, params = sesion.sql[-1]
    assert crm.SQL_ESTADO_SUAVE in sql
    assert params["estado_crm"] == "En Conversación" and "Cotización Enviada" not in params["reactivables"]


async def test_deteccion_requiere_vendedor_no_es_suave():
    sesion = SesionFalsa()
    await crm.guardar_en_crm(sesion, 7, "56900000001", {"estado_crm": "Requiere Vendedor"}, estado_suave=False)
    sql, _ = sesion.sql[-1]
    assert "estado_crm = :estado_crm" in sql and "case" not in sql
