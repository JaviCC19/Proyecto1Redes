# Offers Recommendation MCP Server

Custom, from-scratch MCP server implemented for functionalities **#5**
(local) and **#6** (the same server, remote) of Proyecto 1 (CC3067
Redes, UVG). It does **not** use the MCP SDK, FastMCP, or any similar
library: the JSON-RPC 2.0 message framing, the `initialize` handshake
and the `tools/list` / `tools/call` dispatch are all hand-written in
[`server.py`](./server.py) using only the Python standard library
(`sys`, `json`), and shared by both transports below.

## Industry use case

A retail / e-commerce **promotions ("offers") engine**. The chatbot
asks the customer a short series of questions (what they're interested
in, their budget, a preferred category) and the server ranks the
catalog of available deals to recommend the one(s) that best match the
answers.

## Transport

Two transports expose the exact same tools and the exact same
`handle_message()` dispatch logic (`server.py`); only the framing
around the JSON-RPC messages changes.

### Local: stdio (functionality #5)

- **Type:** stdio (the server is spawned as a child process; JSON-RPC
  messages are exchanged over its stdin/stdout).
- **Framing:** one JSON object per line (newline-delimited JSON), UTF-8
  encoded. No `Content-Length` headers.
- All server-side logging goes to **stderr**, never to stdout, so stdout
  stays reserved exclusively for JSON-RPC messages.

### Remote: HTTP (functionality #6)

Implemented in [`http_server.py`](./http_server.py) with only
`http.server` from the standard library (no Flask/FastAPI, no MCP
SDK) - a simplified version of the MCP "Streamable HTTP" transport:
one JSON-RPC message POSTed, one JSON-RPC message back in the response
body (we don't implement the SSE upgrade / server push path, since
this project's client only ever does one request/response at a time).

| Endpoint      | Method | Body                     | Response                                                        |
|---------------|--------|--------------------------|-------------------------------------------------------------------|
| `/mcp`        | POST   | one JSON-RPC 2.0 message | `200` + JSON-RPC response for a request; `202` + empty body for a notification |
| `/health`     | GET    | -                        | `200 {"status": "ok"}` (used by Cloud Run health checks)          |

Auth: if the `MCP_AUTH_TOKEN` environment variable is set on the
server, every `/mcp` request must carry `Authorization: Bearer
<token>`, or the server replies `401`. Left unset for local testing.

Deploying it (e.g. to Google Cloud Run):

```bash
cd src/servers/offers_server
docker build -t offers-mcp .
docker run -p 8080:8080 -e MCP_AUTH_TOKEN=change-me offers-mcp   # test locally first

# then, once you have gcloud configured:
../../../scripts/deploy_offers_cloud_run.sh
```

Point the chatbot at the deployed URL by setting, in `.env`:

```bash
OFFERS_REMOTE_URL=https://<your-service>-xxxxxxxxxx.a.run.app
OFFERS_AUTH_TOKEN=change-me
```

`src/host/mcp_manager.py` picks the remote client (`MCPHttpClient` in
[`src/host/mcp_http_client.py`](../../host/mcp_http_client.py)) instead
of spawning the local subprocess whenever `OFFERS_REMOTE_URL` is set -
everything else (tool schema, chatbot prompt, logging) stays identical.

## Protocol version

`2025-11-25` (matches `MCP_PROTOCOL_VERSION` in
[`src/host/mcp_client.py`](../../host/mcp_client.py)).

## How to run it

Standalone, for manual testing (stdio):

```bash
cd src/servers/offers_server
python3 server.py
```

Then type/paste JSON-RPC requests (one per line) into stdin - see
"Examples" below.

Standalone, over HTTP:

```bash
cd src/servers/offers_server
PORT=8080 python3 http_server.py
curl -X POST http://localhost:8080/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

In the actual project the server is started automatically by the
chatbot host (see [`src/host/mcp_manager.py`](../../host/mcp_manager.py)),
exactly like the official Filesystem and Git MCP servers - locally over
stdio by default, or remotely over HTTP when `OFFERS_REMOTE_URL` is
configured.

## Tools exposed

### `list_offers`

Lists every offer in the catalog, optionally filtered by category.

| param      | type   | required | description                                   |
|------------|--------|----------|------------------------------------------------|
| `category` | string | no       | e.g. `electronica`, `comida`, `viajes`, `ropa`, `tecnologia`, `hogar`, `entretenimiento`, `educacion` |

### `get_offer_details`

Returns the full record for one offer.

| param      | type   | required | description         |
|------------|--------|----------|----------------------|
| `offer_id` | string | yes      | e.g. `OF-001`        |

### `match_offers`

The core recommendation tool. Scores every offer against the
customer's answers and returns the top matches with the reasoning
behind each score.

| param                | type            | required | description                                             |
|----------------------|-----------------|----------|-----------------------------------------------------------|
| `interests`          | array\<string\> | no       | keywords describing what the customer likes               |
| `preferred_category` | string          | no       | category the customer mentioned, if any                   |
| `max_budget`         | number          | no       | maximum final price the customer is willing to pay         |
| `top_n`               | integer         | no       | how many recommendations to return (default `3`)          |

Scoring (simple, transparent heuristic - see `tool_match_offers` in
`server.py`):

- `+3` if the offer's category equals `preferred_category`.
- `+1.5` per overlapping keyword between `interests` and the offer's
  `tags`.
- `+2` if `price_final <= max_budget`, `-2` if it exceeds it.
- `+discount_percent / 100` as a small tie-breaker favoring bigger
  discounts.

### `claim_offer`

Registers that a customer accepted/claimed a given offer (kept in
memory for the lifetime of the server process; a real deployment would
persist this in a database).

| param           | type   | required | description         |
|-----------------|--------|----------|----------------------|
| `offer_id`      | string | yes      | e.g. `OF-001`        |
| `customer_name` | string | yes      | who is claiming it   |

## Examples (raw JSON-RPC, one line each)

**1. Handshake**

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test-client","version":"0.0.1"}}}
```

Response:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"offers-recommendation-server","version":"1.0.0"}}}
```

```json
{"jsonrpc":"2.0","method":"notifications/initialized"}
```

**2. Discover tools**

```json
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
```

**3. Ask for a recommendation**

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"match_offers","arguments":{"interests":["musica","tecnologia"],"max_budget":300}}}
```

Response (`result.content[0].text` is a JSON string with the ranked
recommendations):

```json
{"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{\"criteria\": {...}, \"recommendations\": [{\"offer\": {\"id\": \"OF-001\", ...}, \"score\": 5.0, \"reasons\": [\"coincide en intereses: musica, tecnologia\", \"está dentro del presupuesto\"]}, ...]}"}],"isError":false}}
```

**4. Claim an offer**

```json
{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"claim_offer","arguments":{"offer_id":"OF-001","customer_name":"Javier"}}}
```

## How the chatbot uses it

`src/host/mcp_manager.py` spawns this script as a subprocess (alias
`offers`) alongside the official Filesystem and Git servers. Tool names
exposed to the LLM are namespaced as `offers__<tool_name>` so the model
can tell which MCP server to route each call to. A typical
conversation:

```
Usuario: Hola, quiero ver si hay alguna promoción que me convenga.
Chatbot: ¡Claro! ¿Qué tipo de cosas te interesan (tecnología, comida,
         viajes, ropa...) y tienes un presupuesto en mente?
Usuario: Me gusta la música y la tecnología, y no quiero pasar de Q300.
Chatbot: [llama a offers__match_offers con interests=["musica","tecnologia"], max_budget=300]
         Te recomiendo los audífonos inalámbricos (OF-001): están a
         Q200, dentro de tu presupuesto, y encajan con música y
         tecnología. ¿Quieres que la reclame a tu nombre?
```
