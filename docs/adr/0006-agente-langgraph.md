# ADR 0006: Un agente con herramientas sobre LangGraph

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

Un grafo LangGraph por agente con herramientas tipadas (Pydantic), checkpointer en Postgres e interrupciones para aprobación humana. LangChain solo para los adaptadores de modelos. Multiagente solo cuando exista un caso que lo justifique (p. ej. facturación SII con permisos y confirmación propios).

## Alternativas descartadas

Multiagente por defecto: más costo y latencia sin un caso real hoy.

## Consecuencias

Se instala con el extra `agente` en la Etapa 4; la base no depende de LangGraph.
