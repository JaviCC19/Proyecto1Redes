# Proyecto 1 - Uso de un protocolo existente (MCP)

CC3067 Redes, Universidad del Valle de Guatemala. A terminal chatbot
("host", in MCP terms) that talks to the Anthropic Messages API and
orchestrates Model Context Protocol (MCP) tools served by local
processes, using a **hand-written JSON-RPC 2.0 / MCP client and
server**, with no MCP SDK, no FastMCP, and no Anthropic SDK anywhere in
the project's own code.

> Status: this checkpoint implements functionalities **1 through 5** of
> the assignment (chatbot core + the two official local MCP servers +
> our own custom local MCP server). The remote deployment, the
> Wireshark analysis and the final report (functionalities 6-10) are
> not part of this delivery yet.

## Why "no SDK"

The assignment requires the MCP protocol to be implemented manually:
"La implementación del protocolo debe realizarse de forma manual, es
decir, que deben implementarse todo el formato e intercambio de
mensajes utilizando JSON-RPC, sin utilizar librerías o SDKs que
implementen MCP, tales como FastMCP". Concretely, in this repo:

- [`src/host/mcp_client.py`](src/host/mcp_client.py) implements the
  stdio transport (newline-delimited JSON), the `initialize` handshake,
  request/response correlation and `tools/list` / `tools/call` by hand,
  using only `subprocess`, `json` and `threading` from the standard
  library.
- [`src/servers/offers_server/server.py`](src/servers/offers_server/server.py)
  (our own MCP server) implements the server side of that same protocol
  by hand, with only `sys` and `json`.
- [`src/host/llm_client.py`](src/host/llm_client.py) talks to the
  Anthropic Messages API with plain HTTPS (`requests`), not the
  `anthropic` Python SDK.

The **official** Filesystem and Git MCP servers (functionality #4)
are pre-built reference servers we *use* as external processes - the
assignment explicitly asks for them "existentes (oficiales)". Whatever
they use internally is irrelevant: our client never imports their code,
it only exchanges JSON-RPC messages with them over stdio, exactly like
it does with our own custom server.

## Architecture

```
                     ┌───────────────────────────┐
                     │   chatbot.py  (Anfitrión)  │
                     │  - Anthropic Messages API  │
                     │  - session context         │
                     └─────────────┬──────────────┘
                                   │  MCPClient (hand-written JSON-RPC over stdio)
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌─────────▼────────┐ ┌──────────▼─────────┐
     │  fs   (official) │ │  git  (official)  │ │ offers  (custom)   │
     │ @modelcontext-   │ │  mcp-server-git   │ │ src/servers/       │
     │ protocol/server- │ │  (PyPI, spawned   │ │ offers_server      │
     │ filesystem (npx) │ │  as subprocess)   │ │ (this project)     │
     └──────────────────┘ └───────────────────┘ └─────────────────────┘
```

Every JSON-RPC message crossing any of these three connections is
logged by [`src/host/logger.py`](src/host/logger.py) - printed live to
the console and appended to `logs/mcp_interactions.log`.

## Features implemented (mapped to the assignment)

| # | Functionality | Where |
|---|----------------|-------|
| 1 | LLM connection at the API level | `src/host/llm_client.py` |
| 2 | Multi-turn session context | `src/host/context.py` |
| 3 | Log of every MCP request/response | `src/host/logger.py` |
| 4 | Official Filesystem + Git MCP servers | `src/host/mcp_manager.py` |
| 5 | Custom local MCP server (industry use case: offer/deal recommendation) | `src/servers/offers_server/` (spec in its own [README](src/servers/offers_server/README.md)) |

## Requirements

- Python 3.10+
- Node.js + `npx` (used to run the official Filesystem MCP server on demand - no manual install needed, `npx` fetches it automatically the first time)
- An Anthropic API key (the course provides $5 in free credits, no card required) - https://console.anthropic.com

## Setup

```bash
git clone <this repo>
cd Proyecto1Redes

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY=sk-ant-...
```

## Running the chatbot

```bash
./scripts/run_chatbot.sh
# or directly:
python3 src/host/chatbot.py
```

On startup the host spawns and initializes the three MCP servers
(`offers`, `fs`, `git`), prints the JSON-RPC handshake to the console,
and drops you into a chat prompt. Type `salir` to quit.

Two sandboxed folders are created automatically the first time you run
it (both git-ignored):

- `workspace/` - the only directory the Filesystem MCP server is
  allowed to touch.
- `workspace_git/` - the repository the Git MCP server is bound to.
  It is initialized with a single `git init` the first time (the
  official `mcp-server-git` package does not expose a `git_init`
  tool and refuses to start at all if `--repository` does not already
  point at a valid repo - see the comment in `mcp_manager.py` for
  details). Every subsequent operation (creating the README, staging
  it, committing it) goes through MCP.

### Demo scenario for functionality #4

Ask the chatbot something like:

> "Crea un archivo README.md en el workspace que diga 'Proyecto 1
> Redes', agrégalo al repositorio git y haz commit con el mensaje
> 'Initial commit'."

The model will call `fs__write_file` and then `git__git_add` +
`git__git_commit`, all visible in the console log and in
`logs/mcp_interactions.log`.

### Demo scenario for functionality #5

> "Hola, ¿tienen alguna promoción interesante?"

The chatbot should ask a couple of clarifying questions (interests,
budget, preferred category) and then call `offers__match_offers` to
recommend the best matching deal from the catalog. Full tool spec,
JSON-RPC examples and more sample conversations are in
[`src/servers/offers_server/README.md`](src/servers/offers_server/README.md).

## Verifying the MCP plumbing without an API key

```bash
python3 scripts/smoke_test.py
```

Starts all three MCP servers, lists their tools and exercises one tool
call on each (recommend an offer, write+read a file, init/add/commit/
status a git repo) — useful to confirm the transport works
independently of the LLM integration.

## Logging

Every JSON-RPC request, response and notification is:

- printed to the console as `[MCP][<server>] --> / <-- id=... ...`
- appended as a structured JSON line to `logs/mcp_interactions.log`

## Project layout

```
src/
  host/
    chatbot.py       # entry point / chat loop
    llm_client.py     # Anthropic Messages API client (plain HTTPS)
    context.py         # session/context manager
    logger.py           # JSON-RPC interaction logger
    mcp_client.py         # hand-written MCP client (JSON-RPC over stdio)
    mcp_manager.py          # spawns/owns the fs, git and offers servers
    env_loader.py             # tiny .env reader
  servers/
    offers_server/
      server.py      # our own MCP server (hand-written, no SDK)
      offers_data.py  # sample offer/deal catalog
      README.md        # protocol spec, tools, usage examples
scripts/
  run_chatbot.sh
  smoke_test.py
logs/                 # created at runtime (git-ignored except this folder)
```

## Roadmap (not part of this delivery)

- [ ] Functionality 6: deploy the offers MCP server remotely (Cloud
      Run / Cloudflare) and have the chatbot use it exactly like the
      local one.
- [ ] Functionality 7: Wireshark capture and JSON-RPC message
      classification (sync / request / response) for the remote
      transport.
- [ ] Functionalities 8-10: written report (spec, Wireshark analysis
      across OSI/TCP-IP layers, conclusions).
- [ ] Optional UI extra credit.

## Academic integrity note

This project's own code (`src/host/*.py`,
`src/servers/offers_server/*.py`) implements the MCP JSON-RPC protocol
from scratch, referencing only the public specification
(https://modelcontextprotocol.io/specification/2025-11-25) and the
JSON-RPC 2.0 spec (https://www.jsonrpc.org/specification) - not any
MCP SDK source code. The official Filesystem and Git servers used in
functionality #4 are third-party reference implementations, used as
required by the assignment, and are not part of "our" protocol
implementation.
