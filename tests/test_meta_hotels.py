"""Offline tests for Meta planning and mocked transport; no live Meta requests."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_meta_hotels as mod

ID = "12345678-abcd-4321-9876-123456789012"
OTHER = "12345678-abcd-4321-9876-123456789013"
CATALOGUE, WABA = "101", "202"


def snapshot():
    return {"version": 1, "properties": [{
        "id": ID, "title": "Villa & sea", "description": "Public description",
        "url": "https://pwanistays.com/property.html?id=" + ID,
        "images": ["https://example.com/cover.jpg"],
        "price": "confidential", "commission_rate": "confidential"}]}


class FakeGraph:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def request(self, method, path, params=None):
        self.calls.append((method, path, params))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def preflight(remote=None, linked=None, vertical="hotels"):
    return [{"id": CATALOGUE, "vertical": vertical},
            {"data": [{"id": item} for item in ([CATALOGUE] if linked is None else linked)]},
            {"data": [] if remote is None else remote}]


class PlanTests(unittest.TestCase):
    def test_official_hotel_shape_stable_namespace_and_no_private_rate(self):
        first = mod.payloads(snapshot())
        self.assertEqual(first, mod.payloads(snapshot()))
        self.assertEqual(first[0]["hotel_id"], mod.PREFIX + ID)
        self.assertEqual(first[0]["images"], [{"image_url": "https://example.com/cover.jpg"}])
        self.assertEqual(set(first[0]), {"hotel_id", "name", "description", "brand", "url", "images"})
        self.assertNotIn("confidential", json.dumps(first))
        self.assertNotIn("address", first[0])

    def test_approved_address_only_and_no_fabricated_metadata(self):
        address = {"city": "Mombasa", "country": "Kenya", "latitude": -4.0, "longitude": 39.7}
        self.assertEqual(mod.payloads(snapshot(), {ID: {"address": address}})[0]["address"], address)
        for details in [{ID: {"base_price": 0}}, {OTHER: {"address": address}},
                        {ID: {"address": {"latitude": 0}}},
                        {ID: {"address": {"latitude": 99, "longitude": 0}}},
                        {ID: {"address": {"latitude": float("nan"), "longitude": 0}}}]:
            with self.subTest(details=details), self.assertRaises(mod.SyncError):
                mod.payloads(snapshot(), details)

    def test_rejects_empty_duplicate_invalid_source_and_photos(self):
        bad_sources = [{}, {"version": 1, "properties": []}]
        value = snapshot()
        value["properties"] *= 2
        bad_sources.append(value)
        for field, invalid in [("id", "broken"), ("url", "https://elsewhere.example/"),
                               ("images", []), ("images", ["http://example.com/a.jpg"]),
                               ("images", ["https://example.com/a.jpg"] * 11),
                               ("images", ["https://example.com/a.jpg"] * 2),
                               ("title", " ")]:
            value = snapshot()
            value["properties"][0][field] = invalid
            bad_sources.append(value)
        for value in bad_sources:
            with self.subTest(value=value), self.assertRaises(mod.SyncError):
                mod.payloads(value)

    def test_default_cli_is_offline_and_does_not_write_a_plan(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text(json.dumps(snapshot()))
            stdout = io.StringIO()
            with patch.object(mod, "Graph") as graph, contextlib.redirect_stdout(stdout):
                self.assertEqual(mod.main(["--source", str(source)]), 0)
            graph.assert_not_called()
            self.assertEqual(json.loads(stdout.getvalue())["mode"], "offline_dry_run")
            self.assertNotIn("hotels", json.loads(stdout.getvalue()))
            self.assertEqual(list(Path(folder).iterdir()), [source])

    def test_public_plan_path_and_unsafe_flags_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text(json.dumps(snapshot()))
            for flags in [["--plan", str(mod.ROOT / "catalogue/private-plan.json")],
                          ["--plan", str(mod.ROOT / "private-plan.json")],
                          ["--connect"], ["--prune"]]:
                with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(mod.main(["--source", str(source)] + flags), 1)

    def test_only_selects_known_property_after_full_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            value = snapshot()
            other = dict(value["properties"][0], id=OTHER,
                         url="https://pwanistays.com/property.html?id=" + OTHER)
            value["properties"].append(other)
            source.write_text(json.dumps(value))
            stdout = io.StringIO()
            with patch.object(mod, "Graph") as graph, contextlib.redirect_stdout(stdout):
                self.assertEqual(mod.main(["--source", str(source), "--only", ID]), 0)
            graph.assert_not_called()
            self.assertEqual(json.loads(stdout.getvalue())["property_count"], 1)
            for invalid in ["broken", "12345678-abcd-4321-9876-123456789014"]:
                with contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(mod.main(["--source", str(source), "--only", invalid]), 1)
            # Selecting one valid row must not hide invalid remaining source rows.
            value["properties"][1]["images"] = []
            source.write_text(json.dumps(value))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(mod.main(["--source", str(source), "--only", ID]), 1)

    def test_only_and_prune_refused_before_graph_calls(self):
        with patch.object(mod, "Graph") as graph, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(mod.main(["--apply", "--prune", "--only", ID]), 1)
        graph.assert_not_called()


class SyncTests(unittest.TestCase):
    def test_internal_empty_or_duplicate_plan_cannot_prune_remote_items(self):
        items = mod.payloads(snapshot())
        for value in [[], items * 2, [{"hotel_id": "unrelated"}]]:
            graph = FakeGraph([])
            with self.subTest(value=value), self.assertRaises(mod.SyncError):
                mod.synchronize(graph, CATALOGUE, WABA, value, prune=True)
            self.assertEqual(graph.calls, [])

    def test_catalogue_and_link_preflight_fail_without_writes(self):
        for replies in [preflight(vertical="commerce"), preflight(linked=[]),
                        preflight(linked=["999"]),
                        preflight(remote=[{"id": "301", "hotel_id": mod.PREFIX + ID}] * 2)]:
            graph = FakeGraph(replies)
            with self.subTest(replies=replies), self.assertRaises(mod.SyncError):
                mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()))
            self.assertTrue(all(method == "GET" for method, _, _ in graph.calls))

    def test_namespaced_identity_creates_then_updates_without_duplicates(self):
        items = mod.payloads(snapshot())
        graph = FakeGraph(preflight() + [{"id": "301"}])
        self.assertEqual(mod.synchronize(graph, CATALOGUE, WABA, items),
                         {"created": 1, "updated": 0, "deleted": 0})
        self.assertEqual(graph.calls[-1][1], CATALOGUE + "/hotels")
        graph = FakeGraph(preflight(remote=[{"id": "301", "hotel_id": mod.PREFIX + ID}]) + [{"success": True}])
        self.assertEqual(mod.synchronize(graph, CATALOGUE, WABA, items)["updated"], 1)
        self.assertEqual(graph.calls[-1][1], "301")
        self.assertNotIn("hotel_id", graph.calls[-1][2])

    def test_no_default_deletions_and_explicit_prune_only_our_managed_uuid(self):
        remote = [{"id": "301", "hotel_id": mod.PREFIX + OTHER},
                  {"id": "302", "hotel_id": "unrelated"},
                  {"id": "303", "hotel_id": mod.PREFIX + "not-a-uuid"}]
        graph = FakeGraph(preflight(remote) + [{"id": "304"}])
        mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()))
        self.assertFalse(any(method == "DELETE" for method, _, _ in graph.calls))
        graph = FakeGraph(preflight(remote) + [{"id": "304"}, {"success": True}])
        self.assertEqual(mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()), prune=True)["deleted"], 1)
        self.assertEqual([path for method, path, _ in graph.calls if method == "DELETE"], ["301"])

    def test_failed_upsert_prevents_all_pruning(self):
        graph = FakeGraph(preflight([{"id": "301", "hotel_id": mod.PREFIX + OTHER}]) +
                          [mod.SyncError("Rejected by Meta")])
        with self.assertRaises(mod.SyncError):
            mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()), prune=True)
        self.assertFalse(any(method == "DELETE" for method, _, _ in graph.calls))

    def test_connect_is_explicit_verified_and_never_replaces_other_catalogue(self):
        graph = FakeGraph(preflight(linked=[]) + [{"success": True},
                          {"data": [{"id": CATALOGUE}]}, {"id": "301"}])
        mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()), connect=True)
        writes = [(path, data) for method, path, data in graph.calls if method == "POST"]
        self.assertEqual(writes[0], (WABA + "/product_catalogs", {"catalog_id": CATALOGUE}))
        graph = FakeGraph(preflight(linked=[]) + [{"success": True}, {"data": []}])
        with self.assertRaises(mod.SyncError):
            mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()), connect=True)
        self.assertFalse(any(path == CATALOGUE + "/hotels" for method, path, _ in graph.calls if method == "POST"))
        graph = FakeGraph(preflight(linked=["999"]))
        with self.assertRaises(mod.SyncError):
            mod.synchronize(graph, CATALOGUE, WABA, mod.payloads(snapshot()), connect=True)
        self.assertTrue(all(method == "GET" for method, _, _ in graph.calls))

    def test_pagination_uses_cursors_not_remote_urls_and_rejects_repeated_cursor(self):
        graph = FakeGraph([{"data": [{"id": "1"}], "paging": {
            "next": "https://untrusted.example/?access_token=secret", "cursors": {"after": "cursor"}}},
            {"data": [{"id": "2"}]}])
        self.assertEqual(len(mod.list_edge(graph, "101/hotels", "id")), 2)
        self.assertEqual(graph.calls[-1][1], "101/hotels")
        self.assertEqual(graph.calls[-1][2]["after"], "cursor")
        graph = FakeGraph([{"data": [], "paging": {"next": "x", "cursors": {"after": "same"}}}] * 2)
        with self.assertRaises(mod.SyncError):
            mod.list_edge(graph, "101/hotels", "id")


class TransportTests(unittest.TestCase):
    def test_http_error_explains_endpoint_and_code_without_leaking_credentials(self):
        token = "test-private-token"
        graph = mod.Graph(token, "v26.0")
        graph.opener = Mock()
        body = {"error": {"code": 100, "error_subcode": 33, "type": "GraphMethodException",
                          "message": "Unsupported get request. Check permissions. " + token +
                          " https://example.com/?access_token=other-secret"},
                "request_headers": {"Authorization": "Bearer " + token},
                "debug": "must-not-be-logged"}
        graph.opener.open.side_effect = HTTPError(
            "https://example.com/", 400, "Bad Request", {}, io.BytesIO(json.dumps(body).encode()))
        with self.assertRaises(mod.SyncError) as raised:
            graph.request("GET", CATALOGUE, {"fields": "id,name,vertical"})
        error = str(raised.exception)
        for expected in ["GET " + CATALOGUE, "HTTP 400", "code=100", "error_subcode=33",
                         "GraphMethodException", "Check permissions"]:
            self.assertIn(expected, error)
        for secret in [token, "other-secret", "must-not-be-logged", "Authorization"]:
            self.assertNotIn(secret, error)

    def test_unstructured_http_body_is_not_logged(self):
        graph = mod.Graph("test-private-token", "v26.0")
        graph.opener = Mock()
        graph.opener.open.side_effect = HTTPError(
            "https://example.com/", 400, "Bad Request", {}, io.BytesIO(b"private-token-and-debug-html"))
        with self.assertRaises(mod.SyncError) as raised:
            graph.request("POST", CATALOGUE + "/hotels", {})
        self.assertIn("POST " + CATALOGUE + "/hotels", str(raised.exception))
        self.assertIn("no structured error details", str(raised.exception))
        self.assertNotIn("private-token-and-debug-html", str(raised.exception))

    def test_redaction_removes_other_tokens_and_control_characters(self):
        graph = mod.Graph("configured-token", "v26.0")
        result = graph.safe_message("Error\nBearer other-secret client_secret=app-secret "
                                    "EAAotherTokenValue1234567890 " + "x" * 60)
        for secret in ["other-secret", "app-secret", "EAAotherTokenValue1234567890", "x" * 60, "\n"]:
            self.assertNotIn(secret, result)
        self.assertIn("Error", result)

    def test_json_error_in_success_status_is_explained_and_redacted(self):
        graph = mod.Graph("configured-token", "v26.0")
        graph.opener = Mock()
        graph.opener.open.return_value = io.BytesIO(json.dumps({"error": {
            "code": 190, "message": "Invalid access token configured-token"}}).encode())
        with self.assertRaises(mod.SyncError) as raised:
            graph.request("GET", CATALOGUE)
        self.assertIn("code=190", str(raised.exception))
        self.assertNotIn("configured-token", str(raised.exception))

    def test_bearer_header_and_encoded_nested_payload_no_token_in_url(self):
        graph = mod.Graph("test-private-token", "v26.0")
        graph.opener = Mock()
        graph.opener.open.return_value = io.BytesIO(b'{"id":"301"}')
        graph.request("POST", "101/hotels", mod.payloads(snapshot())[0])
        req = graph.opener.open.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer test-private-token")
        self.assertNotIn("test-private-token", req.full_url)
        self.assertEqual(json.loads(parse_qs(req.data.decode())["images"][0]),
                         [{"image_url": "https://example.com/cover.jpg"}])
        self.assertIsNone(mod.NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example"))

    def test_transport_errors_and_version_validation_do_not_expose_remote_text(self):
        for version in ["", "26.0", "v26.1", "v26.0/evil"]:
            with self.assertRaises(mod.SyncError):
                mod.Graph("token", version)
        graph = mod.Graph("test-private-token", "v26.0")
        graph.opener = Mock()
        graph.opener.open.side_effect = HTTPError("https://example/?token=test-private-token", 403,
                                                  "test-private-token", {}, None)
        with self.assertRaises(mod.SyncError) as error:
            graph.request("GET", "101")
        self.assertNotIn("test-private-token", str(error.exception))
        self.assertIn("403", str(error.exception))


if __name__ == "__main__":
    unittest.main()
