# Offers Recommendation MCP Server

Custom, from-scratch **local** MCP server implemented for functionality
**#5** of Proyecto 1 (CC3067 Redes, UVG). It does **not** use the MCP
SDK, FastMCP, or any similar library: the JSON-RPC 2.0 message framing,
the `initialize` handshake and the `tools/list` / `tools/call` dispatch
are all hand-written in [`server.py`](./server.py) using only the
Python standard library (`sys`, `json`).

## Industry use case

A retail / e-commerce **promotions ("offers") engine**. The chatbot
asks the customer a short series of questions (what they're interested
in, their budget, a preferred category) and the server ranks the
catalog of available deals to recommend the one(s) that best match the
answers.

## Transport

- **Type:** stdio (the server is spawned as a child process; JSON-RPC
  messages are exchanged over its stdin/stdout).
- **Framing:** one JSON object per line (newline-delimited JSON), UTF-8
  encoded. No `Content-Length` headers.
- All server-side logging goes to **stderr**, never to stdout, so stdout
  stays reserved exclusively for JSON-RPC messages.

## Protocol version

`2025-11-25` (matches `MCP_PROTOCOL_VERSION` in
[`src/host/mcp_client.py`](../../host/mcp_client.py)).

## How to run it

Standalone, for manual testing:

```bash
cd src/servers/offers_server
python3 server.py
```

Then type/paste JSON-RPC requests (one per line) into stdin - see
"Examples" below. In the actual project it is spawned automatically by
the chatbot host (see [`src/host/mcp_manager.py`](../../host/mcp_manager.py)),
exactly like the official Filesystem and Git MCP servers.

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
