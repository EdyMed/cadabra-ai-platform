# ADR 0001: Monolito modular en un solo repositorio

- Estado: aceptada
- Fecha: 2026-11-17

## Decisión

Una imagen Docker y dos procesos (api, worker) en EasyPanel. Módulos por dominio dentro de `src/cadabra`; se separan en servicios solo cuando exista una razón operativa medible.

## Alternativas descartadas

Microservicios desde el inicio: más despliegues, red y observabilidad sin beneficio con el volumen actual (2 empresas).

## Consecuencias

Un despliegue simple en el VPS actual; los límites entre módulos se cuidan con imports y pruebas.
