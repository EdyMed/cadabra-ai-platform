"""El grafo del agente con un modelo simulado (sin OpenAI): verifica el ciclo pensar → herramientas → pensar."""
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from cadabra.agents.agente import responder, texto_a_enviar
from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.perfil import construir_perfil
from cadabra.core.config import Settings
from cadabra.messaging.whatsapp_api import ClienteWhatsApp
from cadabra.tools.base import EntornoHerramienta


class ModeloConGuion(BaseChatModel):
    """Devuelve, en orden, las respuestas del guion. Registra lo que recibió."""
    guion: list[AIMessage]
    recibido: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "guion"

    def bind_tools(self, tools, **kwargs):
        self.recibido.append(("herramientas", [t.name for t in tools]))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.recibido.append(("mensajes", messages))
        return ChatResult(generations=[ChatGeneration(message=self.guion.pop(0))])


def contexto(rol: str = "anon") -> ContextoTurno:
    return ContextoTurno(empresa=1, nombre_empresa="Cadabra Demo", nombre_asistente="Sofía", config={},
                         perfil=construir_perfil({}, "Sofía", "Cadabra Demo"), telefono="56900000001",
                         phone_number_id="PN", mensaje="menú", rol=rol)


def entorno(ctx: ContextoTurno, whatsapp: ClienteWhatsApp) -> EntornoHerramienta:
    return EntornoHerramienta(ctx=ctx, sesion=None, whatsapp=whatsapp, ensayo=True)  # type: ignore[arg-type]


async def test_menu_se_envia_y_el_texto_puntero_no():
    ctx = contexto()
    wa = ClienteWhatsApp("token", ensayo=True)
    modelo = ModeloConGuion(guion=[
        AIMessage("", tool_calls=[{"name": "mostrar_menu", "args": {"tipo_menu": "cliente"}, "id": "t1"}]),
        AIMessage("👇", usage_metadata={"input_tokens": 10, "output_tokens": 1, "total_tokens": 11}),
    ])
    r = await responder(ctx, entorno(ctx, wa), Settings(), modelo=modelo)
    assert r.respuesta == ""                                   # "👇" no se envía (igual que n8n)
    assert [ll["herramienta"] for ll in r.llamadas] == ["mostrar_menu"]
    assert wa.enviados[0]["type"] == "interactive"            # el menú sí se envió (en ensayo: registrado)
    assert r.tokens_entrada == 10
    # el prompt de sistema llegó completo y con el nombre del asistente
    primer_llamado = next(x for x in modelo.recibido if x[0] == "mensajes")[1]
    assert "Eres Sofía, la asistente por WhatsApp de Cadabra Demo" in primer_llamado[0].content


async def test_en_ensayo_las_herramientas_que_escriben_no_tocan_la_base():
    ctx = contexto()
    modelo = ModeloConGuion(guion=[
        AIMessage("", tool_calls=[{"name": "crm_guardar_lead", "args": {"nombre": "Pedro"}, "id": "t1"}]),
        AIMessage("¡Listo Pedro!"),
    ])
    r = await responder(ctx, entorno(ctx, ClienteWhatsApp("t", ensayo=True)), Settings(), modelo=modelo)
    assert r.respuesta == "¡Listo Pedro!"
    assert r.llamadas[0]["resultado"]["ensayo"] is True        # sesion=None: si hubiera escrito, fallaría


async def test_anon_no_recibe_herramientas_de_gestion():
    ctx = contexto("anon")
    modelo = ModeloConGuion(guion=[AIMessage("Hola 😊")])
    await responder(ctx, entorno(ctx, ClienteWhatsApp("t")), Settings(), modelo=modelo)
    herramientas = next(x for x in modelo.recibido if x[0] == "herramientas")[1]
    assert "ventas_periodo" not in herramientas and "stock_producto" in herramientas


def test_texto_a_enviar():
    assert texto_a_enviar(" 👇 ") == ""
    assert texto_a_enviar("Hola") == "Hola"


async def test_anon_nunca_recibe_el_menu_del_dueno_aunque_el_modelo_lo_pida():
    ctx = contexto("anon")
    wa = ClienteWhatsApp("t", ensayo=True)
    modelo = ModeloConGuion(guion=[
        AIMessage("", tool_calls=[{"name": "mostrar_menu", "args": {"tipo_menu": "owner"}, "id": "t1"}]),
        AIMessage("👇"),
    ])
    await responder(ctx, entorno(ctx, wa), Settings(), modelo=modelo)
    botones = [b["reply"]["id"] for b in wa.enviados[0]["interactive"]["action"]["buttons"]]
    assert "ventas_periodo" not in botones
