# Sistema de Auditoría Continua de APIs

## Qué es
Sistema que monitorea APIs REST en el tiempo y detecta problemas en tres
dimensiones: disponibilidad (uptime + latencia), cambios de contrato/schema
(breaking changes), y violaciones de reglas de validación sobre las
respuestas. Guarda histórico y lo muestra en un dashboard.

## Alcance del MVP (NO agregar nada fuera de esto sin que yo lo pida)
- Monitorea endpoints definidos en un archivo de configuración (YAML).
- Tres tipos de chequeo: uptime/latencia, comparación de schema, reglas.
- Persistencia en SQLite (un archivo, sin instalar nada).
- Chequeo periódico con un scheduler mientras el sistema está prendido.
- Demo contra APIs públicas gratuitas sin auth: ReqRes (reqres.in) y
  JSONPlaceholder (jsonplaceholder.typicode.com).
- SIN autenticación contra APIs privadas todavía.
- SIN alertas por email/Slack todavía (fase posterior).
- SIN tests de carga/performance.

## Construcción por fases (una a la vez, NO todo junto)
- Fase 1: motor de chequeo — uptime + latencia, guardado en SQLite.
- Fase 2: detección de cambios de schema (breaking changes).
- Fase 3: validación de reglas definidas en la config.
- Fase 4: dashboard (React) con estado, histórico e incidentes.

## Stack
- Backend: Python + FastAPI
- Cliente HTTP: httpx
- Validación de schema: jsonschema + lógica propia de comparación
- Base de datos: SQLite
- Scheduler: APScheduler
- Frontend: React + Vite (fase 4)

## Reglas de calidad
- Cada chequeo se guarda con timestamp para poder reconstruir el histórico.
- Un cambio de schema NO es necesariamente un error: distinguir entre
  cambio (campo nuevo, no rompe) y breaking change (campo que desaparece
  o cambia de tipo, sí rompe). Marcar la diferencia.
- Si un endpoint no responde, registrar el fallo pero seguir chequeando
  los demás. Un endpoint caído no debe frenar al sistema.
- No inventar: si un chequeo no se puede completar, registrarlo como
  error explícito, no asumir que pasó.