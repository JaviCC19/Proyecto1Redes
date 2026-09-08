# Proyecto 1 - Uso de un protocolo existente (MCP)

CC3067 Redes, Universidad del Valle de Guatemala. Un chatbot de
terminal ("host", en términos de MCP) que se comunica con la API de
Anthropic Messages y orquesta herramientas del Model Context Protocol
(MCP) servidas por procesos locales, usando un **cliente y servidor
JSON-RPC 2.0 / MCP escritos a mano**, sin SDK de MCP, sin FastMCP y sin
el SDK de Anthropic en ninguna parte del código propio del proyecto.

> Estado: este checkpoint implementa las funcionalidades **1 a la 6**
> del enunciado (núcleo del chatbot + los dos servidores MCP locales
> oficiales + nuestro propio servidor MCP, tanto local como remoto). El
> análisis con Wireshark y el informe final (funcionalidades 7-10)
> todavía no forman parte de esta entrega: requieren una captura de red
> real sobre un despliegue en la nube ya activo (ver "Roadmap" abajo).

## Por qué "sin SDK"

El enunciado exige que el protocolo MCP se implemente de forma manual:
"La implementación del protocolo debe realizarse de forma manual, es
decir, que deben implementarse todo el formato e intercambio de
mensajes utilizando JSON-RPC, sin utilizar librerías o SDKs que
implementen MCP, tales como FastMCP". Concretamente, en este
repositorio:

- [`src/host/mcp_client.py`](src/host/mcp_client.py) implementa a mano
  el transporte por stdio (JSON delimitado por saltos de línea), el
  handshake de `initialize`, la correlación de solicitudes/respuestas
  y `tools/list` / `tools/call`, usando únicamente `subprocess`, `json`
  y `threading` de la librería estándar.
- [`src/servers/offers_server/server.py`](src/servers/offers_server/server.py)
  (nuestro propio servidor MCP) implementa a mano el lado del servidor
  de ese mismo protocolo, usando únicamente `sys` y `json`.
- [`src/host/llm_client.py`](src/host/llm_client.py) se comunica con la
  API de Anthropic Messages mediante HTTPS puro (`requests`), no con el
  SDK de Python `anthropic`.

Los servidores MCP **oficiales** de Filesystem y Git (funcionalidad #4)
son servidores de referencia preconstruidos que *usamos* como procesos
externos - el enunciado explícitamente pide que sean "existentes
(oficiales)". Lo que usen internamente es irrelevante: nuestro cliente
nunca importa su código, solo intercambia mensajes JSON-RPC con ellos
por stdio, exactamente igual que con nuestro propio servidor
personalizado.

## Arquitectura

```
                     ┌───────────────────────────┐
                     │   chatbot.py  (Anfitrión)  │
                     │  - API de Anthropic Messages│
                     │  - contexto de sesión       │
                     └─────────────┬──────────────┘
                                   │  MCPClient / MCPHttpClient (JSON-RPC escrito a mano)
              ┌────────────────────┼────────────────────┬──────────────────────┐
              │ stdio               │ stdio                │ stdio                 │ HTTPS
     ┌────────▼────────┐ ┌─────────▼────────┐ ┌──────────▼─────────┐ ┌───────────▼────────────┐
     │  fs   (oficial)  │ │  git  (oficial)   │ │ offers  (propio,    │ │ offers  (propio,        │
     │ @modelcontext-   │ │  mcp-server-git   │ │ local, subproceso)  │ │ remoto, Cloud Run -     │
     │ protocol/server- │ │  (PyPI, lanzado   │ │ src/servers/        │ │ funcionalidad #6,       │
     │ filesystem (npx) │ │  como subproceso) │ │ offers_server        │ │ activo solo si          │
     │                  │ │                   │ │                     │ │ OFFERS_REMOTE_URL está  │
     │                  │ │                   │ │                     │ │ configurado             │
     └──────────────────┘ └───────────────────┘ └─────────────────────┘ └─────────────────────────┘
```

Todo mensaje JSON-RPC que cruza cualquiera de estas conexiones es
registrado por [`src/host/logger.py`](src/host/logger.py) - impreso en
vivo en la consola y agregado a `logs/mcp_interactions.log`. El
servidor `offers` corre localmente por defecto (funcionalidad #5); si
`OFFERS_REMOTE_URL` está configurado en `.env`, el host habla en su
lugar por HTTPS con exactamente el mismo servidor desplegado en la nube
(funcionalidad #6) - ver
[`src/servers/offers_server/README.md`](src/servers/offers_server/README.md#transport).

## Funcionalidades implementadas (mapeadas al enunciado)

| # | Funcionalidad | Dónde |
|---|----------------|-------|
| 1 | Conexión al LLM a nivel de API | `src/host/llm_client.py` |
| 2 | Contexto de sesión multi-turno | `src/host/context.py` |
| 3 | Registro de cada solicitud/respuesta MCP | `src/host/logger.py` |
| 4 | Servidores MCP oficiales Filesystem + Git | `src/host/mcp_manager.py` |
| 5 | Servidor MCP local personalizado (caso de uso industrial: recomendación de ofertas/promociones) | `src/servers/offers_server/` (especificación en su propio [README](src/servers/offers_server/README.md)) |
| 6 | El mismo servidor MCP, desplegado de forma remota (HTTP) | `src/servers/offers_server/http_server.py` + `Dockerfile`, cliente `src/host/mcp_http_client.py`, despliegue con `scripts/deploy_offers_cloud_run.sh` |

## Requisitos

- Python 3.10+
- Node.js + `npx` (usado para ejecutar el servidor MCP oficial de
  Filesystem bajo demanda - no requiere instalación manual, `npx` lo
  descarga automáticamente la primera vez)
- Una API key de Anthropic (el curso otorga $5 en créditos gratuitos,
  sin necesidad de tarjeta) - https://console.anthropic.com
- Opcional, solo para la funcionalidad #6 (desplegar/probar el
  servidor remoto): Docker y/o `gcloud` CLI. No se necesitan para
  correr el chatbot con el servidor de ofertas local (funcionalidad
  #5, comportamiento por defecto).

## Configuración

```bash
git clone <this repo>
cd Proyecto1Redes

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edita .env y define ANTHROPIC_API_KEY=sk-ant-...
```

## Ejecutar el chatbot

```bash
./scripts/run_chatbot.sh
# o directamente:
python3 src/host/chatbot.py
```

Al iniciar, el host lanza e inicializa los tres servidores MCP
(`offers`, `fs`, `git`), imprime el handshake JSON-RPC en la consola,
y te deja en un prompt de chat. Escribe `salir` para salir.

Se crean automáticamente dos carpetas aisladas la primera vez que lo
ejecutas (ambas ignoradas por git):

- `workspace/` - el único directorio que el servidor MCP de Filesystem
  tiene permitido tocar.
- `workspace_git/` - el repositorio al que está vinculado el servidor
  MCP de Git. Se inicializa con un único `git init` la primera vez (el
  paquete oficial `mcp-server-git` no expone una herramienta
  `git_init` y se niega a iniciar si `--repository` no apunta ya a un
  repositorio válido - ver el comentario en `mcp_manager.py` para más
  detalles). Cada operación posterior (crear el README, añadirlo,
  hacer commit) pasa por MCP.

### Escenario de demostración para la funcionalidad #4

Pídele al chatbot algo como:

> "Crea un archivo README.md en el workspace que diga 'Proyecto 1
> Redes', agrégalo al repositorio git y haz commit con el mensaje
> 'Initial commit'."

El modelo llamará a `fs__write_file` y luego a `git__git_add` +
`git__git_commit`, todo visible en el log de consola y en
`logs/mcp_interactions.log`.

### Escenario de demostración para la funcionalidad #5

> "Hola, ¿tienen alguna promoción interesante?"

El chatbot debería hacer un par de preguntas aclaratorias (intereses,
presupuesto, categoría preferida) y luego llamar a
`offers__match_offers` para recomendar la oferta que mejor coincida
del catálogo. La especificación completa de la herramienta, ejemplos
de JSON-RPC y más conversaciones de muestra están en
[`src/servers/offers_server/README.md`](src/servers/offers_server/README.md).

### Escenario de demostración para la funcionalidad #6

1. Despliega el servidor de ofertas a Cloud Run (o pruébalo primero en
   local con Docker) - ver la sección "Remote: HTTP" en
   [`src/servers/offers_server/README.md`](src/servers/offers_server/README.md#transport).
2. En `.env`, define `OFFERS_REMOTE_URL=<url del servicio desplegado>`
   (y `OFFERS_AUTH_TOKEN` si lo configuraste con auth).
3. Corre el chatbot normalmente (`./scripts/run_chatbot.sh`) y pide una
   promoción, igual que en el escenario #5. El log de consola mostrará
   las mismas solicitudes/respuestas JSON-RPC, pero ahora viajando por
   HTTPS hacia el servidor remoto en vez de por stdio hacia un
   subproceso local.
4. `python3 scripts/smoke_test_remote.py` verifica el transporte HTTP
   de punta a punta sin necesitar una API key de Anthropic (funciona
   tanto contra un servidor local levantado por el propio script, como
   contra la URL real ya desplegada si `OFFERS_REMOTE_URL` está
   definido).

## Verificar el funcionamiento de MCP sin una API key

```bash
python3 scripts/smoke_test.py
```

Inicia los tres servidores MCP, lista sus herramientas y ejercita una
llamada de herramienta en cada uno (recomendar una oferta,
escribir+leer un archivo, init/add/commit/status de un repositorio
git) — útil para confirmar que el transporte funciona
independientemente de la integración con el LLM.

## Pruebas unitarias

```bash
./scripts/run_tests.sh
# o directamente:
python3 -m unittest discover -s tests -v
```

`tests/` (46 pruebas) cubre, sin necesitar API key de Anthropic:

| Módulo | Qué prueba |
|---|---|
| `test_context.py` | ventana de historial de sesión (funcionalidad #2) |
| `test_llm_client.py` | breakpoints de prompt caching hacia Claude (`requests.post` interceptado, sin red real) |
| `test_offers_server.py` | dispatch `handle_message()` y scoring de `match_offers`, sin transporte |
| `test_http_server.py` | el transporte HTTP real (funcionalidad #6): levanta un `ThreadingHTTPServer` local y le pega por HTTP de verdad, incluyendo el gate de `MCP_AUTH_TOKEN` |
| `test_mcp_manager.py` | que `OFFERS_REMOTE_URL` cambie correctamente entre servidor local/remoto, y que `close_all()` no se detenga si un cliente falla al cerrar |
| `test_ui.py` | los helpers de formato de terminal |
| `test_env_loader.py` | el parser de `.env` |

Todos con `unittest` de la librería estándar, sin `pytest` ni otra
dependencia nueva.

## Logging

Cada solicitud, respuesta y notificación JSON-RPC es:

- impresa en la consola como `[MCP][<server>] --> / <-- id=... ...`
  (coloreada por dirección: amarillo=solicitud, verde=respuesta,
  rojo=error - ver `src/host/logger.py` / `src/host/ui.py`)
- agregada como una línea JSON estructurada a
  `logs/mcp_interactions.log`

## Optimización de tokens

El chatbot usa `claude-haiku-4-5-20251001` por defecto (overridable con
`ANTHROPIC_MODEL` en `.env`), y dos optimizaciones en cómo se le habla
a la API de Anthropic (ver `src/host/llm_client.py` / `context.py`):

- **Prompt caching**: el prompt de sistema, el listado de herramientas
  y el prefijo de la conversación se marcan con `cache_control:
  {"type": "ephemeral"}`. Como la API de Messages es sin estado y cada
  turno reenvía todo el historial, sin esto se reprocesaría como
  tokens nuevos en cada mensaje - con esto, Anthropic reutiliza el
  prefijo cacheado y solo cobra/procesa lo realmente nuevo. Cada turno
  imprime en consola cuántos tokens vinieron de caché
  (`ui.token_usage_line`).
- **Ventana de historial acotada**: `SessionContext.as_api_messages()`
  solo reenvía las últimas `max_history_turns` (20 por defecto) turnos
  humanos a la API, en vez de una conversación completa que crece sin
  límite. El historial completo se sigue guardando en memoria y en
  disco (`logs/sessions/`) para no perder nada.

## Estructura del proyecto

```
src/
  host/
    chatbot.py       # punto de entrada / bucle de chat
    llm_client.py     # cliente de la API de Anthropic Messages (HTTPS puro)
    context.py         # gestor de sesión/contexto
    logger.py           # logger de interacciones JSON-RPC
    mcp_client.py         # cliente MCP escrito a mano (JSON-RPC sobre stdio)
    mcp_http_client.py      # cliente MCP escrito a mano (JSON-RPC sobre HTTPS, funcionalidad #6)
    mcp_manager.py          # lanza y administra los servidores fs, git y offers (local o remoto)
    env_loader.py             # lector minimalista de .env
  servers/
    offers_server/
      server.py      # nuestro propio servidor MCP (escrito a mano, sin SDK)
      http_server.py   # transporte HTTP del mismo servidor (funcionalidad #6)
      offers_data.py  # catálogo de ofertas/promociones de ejemplo
      Dockerfile         # imagen para desplegar http_server.py en la nube
      README.md            # especificación del protocolo, herramientas, ejemplos de uso
scripts/
  run_chatbot.sh
  run_tests.sh              # corre tests/ (unittest, sin pytest)
  smoke_test.py
  smoke_test_remote.py  # verifica el transporte HTTP de punta a punta
  deploy_offers_cloud_run.sh  # despliega http_server.py a Google Cloud Run
tests/
  test_context.py         # ventana de historial de sesión
  test_llm_client.py        # breakpoints de prompt caching
  test_offers_server.py       # dispatch MCP + scoring de match_offers
  test_http_server.py           # transporte HTTP real (funcionalidad #6)
  test_mcp_manager.py             # switch local/remoto + close_all()
  test_ui.py                        # helpers de formato de terminal
  test_env_loader.py                  # parser de .env
logs/                 # creado en tiempo de ejecución (ignorado por git salvo esta carpeta)
```

## Roadmap (no forma parte de esta entrega)

- [ ] Funcionalidad 7: captura con Wireshark y clasificación de
      mensajes JSON-RPC (sync / request / response) para el transporte
      remoto, contra el servidor de offers ya desplegado (funcionalidad
      #6).
- [ ] Funcionalidades 8-10: informe escrito (especificación, análisis
      de Wireshark a través de las capas OSI/TCP-IP, conclusiones).
- [ ] Extra opcional de UI.

## Nota de integridad académica

El código propio de este proyecto (`src/host/*.py`,
`src/servers/offers_server/*.py`) implementa el protocolo JSON-RPC de
MCP desde cero, referenciando únicamente la especificación pública
(https://modelcontextprotocol.io/specification/2025-11-25) y la
especificación de JSON-RPC 2.0
(https://www.jsonrpc.org/specification) - no el código fuente de
ningún SDK de MCP. Los servidores oficiales de Filesystem y Git
usados en la funcionalidad #4 son implementaciones de referencia de
terceros, usadas según lo requerido por el enunciado, y no forman
parte de "nuestra" implementación del protocolo.
