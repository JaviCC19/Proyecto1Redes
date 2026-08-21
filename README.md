# Proyecto 1 - Uso de un protocolo existente (MCP)

CC3067 Redes, Universidad del Valle de Guatemala. Un chatbot de
terminal ("host", en términos de MCP) que se comunica con la API de
Anthropic Messages y orquesta herramientas del Model Context Protocol
(MCP) servidas por procesos locales, usando un **cliente y servidor
JSON-RPC 2.0 / MCP escritos a mano**, sin SDK de MCP, sin FastMCP y sin
el SDK de Anthropic en ninguna parte del código propio del proyecto.

> Estado: este checkpoint implementa las funcionalidades **1 a la 5**
> del enunciado (núcleo del chatbot + los dos servidores MCP locales
> oficiales + nuestro propio servidor MCP local personalizado). El
> despliegue remoto, el análisis con Wireshark y el informe final
> (funcionalidades 6-10) todavía no forman parte de esta entrega.

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
                                   │  MCPClient (JSON-RPC escrito a mano sobre stdio)
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌─────────▼────────┐ ┌──────────▼─────────┐
     │  fs   (oficial)  │ │  git  (oficial)   │ │ offers  (propio)   │
     │ @modelcontext-   │ │  mcp-server-git   │ │ src/servers/       │
     │ protocol/server- │ │  (PyPI, lanzado   │ │ offers_server      │
     │ filesystem (npx) │ │  como subproceso) │ │ (este proyecto)    │
     └──────────────────┘ └───────────────────┘ └─────────────────────┘
```

Todo mensaje JSON-RPC que cruza cualquiera de estas tres conexiones es
registrado por [`src/host/logger.py`](src/host/logger.py) - impreso en
vivo en la consola y agregado a `logs/mcp_interactions.log`.

## Funcionalidades implementadas (mapeadas al enunciado)

| # | Funcionalidad | Dónde |
|---|----------------|-------|
| 1 | Conexión al LLM a nivel de API | `src/host/llm_client.py` |
| 2 | Contexto de sesión multi-turno | `src/host/context.py` |
| 3 | Registro de cada solicitud/respuesta MCP | `src/host/logger.py` |
| 4 | Servidores MCP oficiales Filesystem + Git | `src/host/mcp_manager.py` |
| 5 | Servidor MCP local personalizado (caso de uso industrial: recomendación de ofertas/promociones) | `src/servers/offers_server/` (especificación en su propio [README](src/servers/offers_server/README.md)) |

## Requisitos

- Python 3.10+
- Node.js + `npx` (usado para ejecutar el servidor MCP oficial de
  Filesystem bajo demanda - no requiere instalación manual, `npx` lo
  descarga automáticamente la primera vez)
- Una API key de Anthropic (el curso otorga $5 en créditos gratuitos,
  sin necesidad de tarjeta) - https://console.anthropic.com

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

## Verificar el funcionamiento de MCP sin una API key

```bash
python3 scripts/smoke_test.py
```

Inicia los tres servidores MCP, lista sus herramientas y ejercita una
llamada de herramienta en cada uno (recomendar una oferta,
escribir+leer un archivo, init/add/commit/status de un repositorio
git) — útil para confirmar que el transporte funciona
independientemente de la integración con el LLM.

## Logging

Cada solicitud, respuesta y notificación JSON-RPC es:

- impresa en la consola como `[MCP][<server>] --> / <-- id=... ...`
- agregada como una línea JSON estructurada a
  `logs/mcp_interactions.log`

## Estructura del proyecto

```
src/
  host/
    chatbot.py       # punto de entrada / bucle de chat
    llm_client.py     # cliente de la API de Anthropic Messages (HTTPS puro)
    context.py         # gestor de sesión/contexto
    logger.py           # logger de interacciones JSON-RPC
    mcp_client.py         # cliente MCP escrito a mano (JSON-RPC sobre stdio)
    mcp_manager.py          # lanza y administra los servidores fs, git y offers
    env_loader.py             # lector minimalista de .env
  servers/
    offers_server/
      server.py      # nuestro propio servidor MCP (escrito a mano, sin SDK)
      offers_data.py  # catálogo de ofertas/promociones de ejemplo
      README.md        # especificación del protocolo, herramientas, ejemplos de uso
scripts/
  run_chatbot.sh
  smoke_test.py
logs/                 # creado en tiempo de ejecución (ignorado por git salvo esta carpeta)
```

## Roadmap (no forma parte de esta entrega)

- [ ] Funcionalidad 6: desplegar el servidor MCP de offers de forma
      remota (Cloud Run / Cloudflare) y hacer que el chatbot lo use
      exactamente igual que el local.
- [ ] Funcionalidad 7: captura con Wireshark y clasificación de
      mensajes JSON-RPC (sync / request / response) para el transporte
      remoto.
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
