#!/usr/bin/env python3
"""
server.py - "Offers Recommendation" MCP server

Industry use case (retail / e-commerce): a promotions engine that a
chatbot can use to ask the customer a few questions (interests, budget,
preferred category) and, based on the answers, recommend which
available offer/deal suits them best.

This is a from-scratch, local MCP server implemented with the Python
standard library ONLY. It speaks JSON-RPC 2.0 over stdio exactly like
the official reference servers (filesystem, git), but none of the MCP
protocol handling is imported from a library: the initialize handshake,
message framing (newline-delimited JSON on stdout/stdin), method
dispatch and error handling are all written here by hand, per the
project requirement ("la implementación del protocolo debe realizarse
de forma manual... sin utilizar librerías o SDKs que implementen MCP").

Run standalone (for manual testing) with:
    python3 server.py
and feed it JSON-RPC lines on stdin, e.g.:
    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"test","version":"0.0"}}}
    {"jsonrpc":"2.0","method":"notifications/initialized"}
    {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
    {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"match_offers","arguments":{"interests":["musica","tecnologia"],"max_budget":300}}}

See README.md in this folder for the full tool specification and more
examples.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from offers_data import OFFERS, CLAIMS

PROTOCOL_VERSION = "2025-11-25"
SERVER_NAME = "offers-recommendation-server"
SERVER_VERSION = "1.0.0"

# ---------------------------------------------------------------------
# Tool specification (hand-written JSON Schema, mirrors what the MCP
# spec expects a "tools/list" result to look like).
# ---------------------------------------------------------------------
TOOLS = [
    {
        "name": "list_offers",
        "description": "Lista todas las ofertas/promociones disponibles, opcionalmente "
                        "filtradas por categoría.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Categoría a filtrar (ej. electronica, comida, viajes, "
                                    "ropa, tecnologia, hogar, entretenimiento, educacion). "
                                    "Opcional: si se omite, se listan todas.",
                }
            },
        },
    },
    {
        "name": "get_offer_details",
        "description": "Obtiene el detalle completo de una oferta específica dado su id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offer_id": {"type": "string", "description": "Identificador de la oferta, ej. OF-001"},
            },
            "required": ["offer_id"],
        },
    },
    {
        "name": "match_offers",
        "description": "Recomienda las ofertas que más le podrían interesar a un cliente, "
                        "en base a sus intereses, presupuesto máximo y/o categoría "
                        "preferida. Se usa después de hacerle un par de preguntas al "
                        "usuario sobre lo que busca.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "interests": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Palabras clave de interés del cliente, ej. "
                                    "['musica', 'tecnologia']",
                },
                "preferred_category": {
                    "type": "string",
                    "description": "Categoría preferida por el cliente, si la mencionó.",
                },
                "max_budget": {
                    "type": "number",
                    "description": "Presupuesto máximo (precio final) que el cliente "
                                    "está dispuesto a pagar.",
                },
                "top_n": {
                    "type": "integer",
                    "description": "Cuántas recomendaciones devolver (default 3).",
                },
            },
        },
    },
    {
        "name": "claim_offer",
        "description": "Registra que un cliente reclamó/aceptó una oferta específica.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offer_id": {"type": "string"},
                "customer_name": {"type": "string"},
            },
            "required": ["offer_id", "customer_name"],
        },
    },
]


# ---------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------
def _find_offer(offer_id: str) -> dict | None:
    for offer in OFFERS:
        if offer["id"] == offer_id:
            return offer
    return None


def tool_list_offers(args: dict) -> dict:
    category = args.get("category")
    offers = OFFERS
    if category:
        offers = [o for o in OFFERS if o["category"].lower() == category.lower()]
    return {"count": len(offers), "offers": offers}


def tool_get_offer_details(args: dict) -> dict:
    offer_id = args["offer_id"]
    offer = _find_offer(offer_id)
    if offer is None:
        raise ValueError(f"No existe una oferta con id '{offer_id}'")
    return offer


def tool_match_offers(args: dict) -> dict:
    interests = [w.lower() for w in args.get("interests", [])]
    preferred_category = (args.get("preferred_category") or "").lower()
    max_budget = args.get("max_budget")
    top_n = int(args.get("top_n") or 3)

    scored = []
    for offer in OFFERS:
        score = 0.0
        reasons = []

        if preferred_category and offer["category"].lower() == preferred_category:
            score += 3
            reasons.append("coincide con la categoría preferida")

        tag_overlap = set(interests) & set(t.lower() for t in offer["tags"])
        if tag_overlap:
            score += len(tag_overlap) * 1.5
            reasons.append(f"coincide en intereses: {', '.join(sorted(tag_overlap))}")

        if max_budget is not None:
            if offer["price_final"] <= max_budget:
                score += 2
                reasons.append("está dentro del presupuesto")
            else:
                score -= 2
                reasons.append("excede el presupuesto indicado")

        # Small bonus for higher discounts so ties favor better deals.
        score += offer["discount_percent"] / 100.0

        scored.append({"offer": offer, "score": round(score, 2), "reasons": reasons})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_n]
    return {
        "criteria": {
            "interests": interests,
            "preferred_category": preferred_category or None,
            "max_budget": max_budget,
        },
        "recommendations": top,
    }


def tool_claim_offer(args: dict) -> dict:
    offer_id = args["offer_id"]
    customer_name = args["customer_name"]
    offer = _find_offer(offer_id)
    if offer is None:
        raise ValueError(f"No existe una oferta con id '{offer_id}'")
    claim = {"offer_id": offer_id, "customer_name": customer_name, "offer_title": offer["title"]}
    CLAIMS.append(claim)
    return {"status": "claimed", "claim": claim, "total_claims": len(CLAIMS)}


TOOL_IMPLS = {
    "list_offers": tool_list_offers,
    "get_offer_details": tool_get_offer_details,
    "match_offers": tool_match_offers,
    "claim_offer": tool_claim_offer,
}


# ---------------------------------------------------------------------
# Hand-rolled JSON-RPC / MCP plumbing (no SDK)
# ---------------------------------------------------------------------
def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def send_result(msg_id, result: dict) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def send_error(msg_id, code: int, message: str) -> None:
    send({"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}})


def handle_initialize(msg_id, params: dict) -> None:
    send_result(msg_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    })


def handle_tools_list(msg_id, params: dict) -> None:
    send_result(msg_id, {"tools": TOOLS})


def handle_tools_call(msg_id, params: dict) -> None:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        send_error(msg_id, -32601, f"Unknown tool: {name}")
        return
    try:
        result = impl(arguments)
        send_result(msg_id, {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "isError": False,
        })
    except Exception as exc:  # noqa: BLE001 - tool errors are reported as MCP errors, not crashes
        send_result(msg_id, {
            "content": [{"type": "text", "text": str(exc)}],
            "isError": True,
        })


def handle_ping(msg_id, params: dict) -> None:
    send_result(msg_id, {})


REQUEST_HANDLERS = {
    "initialize": handle_initialize,
    "tools/list": handle_tools_list,
    "tools/call": handle_tools_call,
    "ping": handle_ping,
}


def main() -> None:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method is None:
            continue  # not a request/notification we understand

        if msg_id is None:
            # Notification (e.g. notifications/initialized): no response.
            continue

        handler = REQUEST_HANDLERS.get(method)
        if handler is None:
            send_error(msg_id, -32601, f"Method not found: {method}")
            continue

        handler(msg_id, params)


if __name__ == "__main__":
    main()
