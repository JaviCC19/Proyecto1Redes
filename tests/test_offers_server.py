"""
Unit tests for src/servers/offers_server/server.py - the transport-
agnostic handle_message() dispatch shared by the stdio (functionality
#5) and HTTP (functionality #6) transports, and the match_offers
scoring heuristic.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "servers", "offers_server"))

import server  # noqa: E402
from offers_data import OFFERS  # noqa: E402


class TestHandleMessage(unittest.TestCase):
    def test_initialize(self) -> None:
        resp = server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(resp["result"]["serverInfo"]["name"], server.SERVER_NAME)
        self.assertEqual(resp["result"]["protocolVersion"], server.PROTOCOL_VERSION)

    def test_tools_list_matches_declared_implementations(self) -> None:
        resp = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        listed = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(listed, set(server.TOOL_IMPLS.keys()))

    def test_tools_call_unknown_tool_returns_json_rpc_error(self) -> None:
        resp = server.handle_message({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "does_not_exist", "arguments": {}},
        })
        self.assertEqual(resp["error"]["code"], -32601)

    def test_unknown_method_returns_json_rpc_error(self) -> None:
        resp = server.handle_message({"jsonrpc": "2.0", "id": 4, "method": "not/a/method"})
        self.assertEqual(resp["error"]["code"], -32601)

    def test_notification_returns_none(self) -> None:
        self.assertIsNone(server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))

    def test_malformed_message_without_method_returns_none(self) -> None:
        self.assertIsNone(server.handle_message({"jsonrpc": "2.0", "id": 5}))

    def test_tools_call_list_offers_by_category(self) -> None:
        resp = server.handle_message({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "list_offers", "arguments": {"category": "salud"}},
        })
        self.assertFalse(resp["result"]["isError"])

    def test_tools_call_get_offer_details_unknown_id_is_reported_as_tool_error(self) -> None:
        resp = server.handle_message({
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {"name": "get_offer_details", "arguments": {"offer_id": "OF-999"}},
        })
        # Tool-level errors are still a JSON-RPC *result* with isError=true,
        # not a JSON-RPC error object - the MCP spec reserves the latter
        # for protocol-level failures.
        self.assertTrue(resp["result"]["isError"])


class TestMatchOffers(unittest.TestCase):
    def test_catalog_has_unique_ids(self) -> None:
        ids = [o["id"] for o in OFFERS]
        self.assertEqual(len(ids), len(set(ids)))

    def test_over_budget_offer_is_penalized_below_in_budget_offer(self) -> None:
        result = server.tool_match_offers({
            "interests": ["tecnologia"], "max_budget": 50, "top_n": len(OFFERS),
        })
        scores = {r["offer"]["id"]: r["score"] for r in result["recommendations"]}
        cheap = next(o for o in OFFERS if o["price_final"] <= 50)
        expensive = next(o for o in OFFERS if o["price_final"] > 50)
        self.assertGreater(scores[cheap["id"]], scores[expensive["id"]])

    def test_preferred_category_boosts_matching_offers(self) -> None:
        result = server.tool_match_offers({"preferred_category": "mascotas", "top_n": 1})
        self.assertEqual(result["recommendations"][0]["offer"]["category"], "mascotas")


if __name__ == "__main__":
    unittest.main()
