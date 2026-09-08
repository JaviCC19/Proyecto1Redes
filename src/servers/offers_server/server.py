#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from typing import Any, Optional

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



def send(message: dict) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def build_response(msg_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def build_error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _dispatch(name: str, arguments: dict) -> dict:
    """Runs one tool implementation and returns the MCP 'tools/call' result
    shape (content blocks + isError), without touching any transport."""
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        raise KeyError(name)
    try:
        result = impl(arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "isError": False,
        }
    except Exception as exc:  # noqa: BLE001 - tool errors are reported as MCP errors, not crashes
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}


def handle_message(message: dict) -> Optional[dict]:
    """Transport-agnostic core of the server: given one parsed JSON-RPC
    request/notification object, returns the JSON-RPC response object to
    send back, or None if the message was a notification (no response
    expected) or malformed. Used by both the stdio main loop (functionality
    #5, local server) and the HTTP transport (functionality #6, remote
    server) so the protocol logic itself is implemented exactly once."""
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method is None:
        return None

    if msg_id is None:
        # Notification (e.g. notifications/initialized): no response.
        return None

    if method == "initialize":
        return build_response(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    if method == "tools/list":
        return build_response(msg_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            return build_response(msg_id, _dispatch(name, arguments))
        except KeyError:
            return build_error(msg_id, -32601, f"Unknown tool: {name}")
    if method == "ping":
        return build_response(msg_id, {})

    return build_error(msg_id, -32601, f"Method not found: {method}")


def main() -> None:
    """stdio transport (functionality #5): one JSON-RPC message per line
    on stdin, one JSON-RPC message per line on stdout."""
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_message(message)
        if response is not None:
            send(response)


if __name__ == "__main__":
    main()
