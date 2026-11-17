"""El agente: un grafo LangGraph de dos nodos.

    START ──► pensar ──(¿pidió herramientas?)──► herramientas ──┐
                 ▲                │ no                        │
                 │                ▼                           │
                 │               END                          │
                 └────────────────────────────────────────────┘

"pensar" llama al modelo con el prompt de sistema y las herramientas permitidas para el rol; si el modelo pide
herramientas, "herramientas" las ejecuta y se vuelve a pensar. Un límite de iteraciones evita ciclos infinitos.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from cadabra.agents.contexto import ContextoTurno
from cadabra.agents.perfil import DIAS
from cadabra.agents.prompt import armar_prompt
from cadabra.core.config import Settings
from cadabra.tools import herramientas_para
from cadabra.tools.base import EntornoHerramienta, a_langchain

log = logging.getLogger(__name__)


@dataclass
class ResultadoAgente:
    respuesta: str                                   # texto a enviar; "" si no corresponde enviar nada
    modelo: str
    llamadas: list[dict[str, Any]] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0
    error: str | None = None


def construir_grafo(modelo: BaseChatModel, herramientas: list) -> Any:
    modelo_con_herramientas = modelo.bind_tools(herramientas)

    async def pensar(estado: MessagesState) -> dict:
        return {"messages": [await modelo_con_herramientas.ainvoke(estado["messages"])]}

    grafo = StateGraph(MessagesState)
    grafo.add_node("pensar", pensar)
    grafo.add_node("herramientas", ToolNode(herramientas))
    grafo.add_edge(START, "pensar")
    grafo.add_conditional_edges("pensar", tools_condition, {"tools": "herramientas", END: END})
    grafo.add_edge("herramientas", "pensar")
    return grafo.compile()


def crear_modelo(settings: Settings) -> BaseChatModel:
    return ChatOpenAI(
        model=settings.modelo,
        temperature=settings.temperatura,
        api_key=settings.openai_api_key.get_secret_value(),
    )


def texto_a_enviar(salida: str) -> str:
    """Igual que el IF de n8n: tras mostrar_menu el modelo responde "👇"; eso no se envía."""
    return salida if salida.replace("👇", "").strip() else ""


async def responder(ctx: ContextoTurno, entorno: EntornoHerramienta, settings: Settings,
                    modelo: BaseChatModel | None = None) -> ResultadoAgente:
    ahora = datetime.now(ZoneInfo(settings.zona_horaria))
    prompt = armar_prompt(ctx, ahora.strftime("%Y-%m-%d %H:%M"), DIAS[(ahora.weekday() + 1) % 7])

    llamadas: list[dict[str, Any]] = []
    herramientas = [a_langchain(h, entorno, llamadas) for h in herramientas_para(ctx.rol)]
    grafo = construir_grafo(modelo or crear_modelo(settings), herramientas)
    resultado = ResultadoAgente(respuesta="", modelo=settings.modelo, llamadas=llamadas)

    try:
        estado = await grafo.ainvoke(
            {"messages": [SystemMessage(prompt), HumanMessage(ctx.mensaje)]},
            config={"recursion_limit": 2 * settings.max_iteraciones + 1},
        )
    except GraphRecursionError:
        resultado.error = f"el agente superó {settings.max_iteraciones} iteraciones"
        log.warning(resultado.error)
        return resultado

    for m in estado["messages"]:
        if isinstance(m, AIMessage) and m.usage_metadata:
            resultado.tokens_entrada += m.usage_metadata.get("input_tokens", 0)
            resultado.tokens_salida += m.usage_metadata.get("output_tokens", 0)
    final = estado["messages"][-1]
    resultado.respuesta = texto_a_enviar(final.content if isinstance(final.content, str) else "")
    return resultado
