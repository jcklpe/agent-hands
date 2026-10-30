#!/usr/bin/env python3
"""Offline checks for where the token goes, pagination, redirects, throttling, error kinds and identity."""
import datetime
import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import canvas_auth as support

TOKEN = "synthetic-canvas-token-7f3a"
ORIGIN = "https://example.instructure.com"
ACCOUNT = support.Account("example", ORIGIN, "1001", "CANVAS_TOKEN_EXAMPLE", None, ("123",))


def reply(status=200, body=None, headers=None, raw=None):
    data = raw if raw is not None else json.dumps([] if body is None else body).encode("utf-8")
    merged = {"content-type": "application/json; charset=utf-8"}
    merged.update({name.lower(): value for name, value in (headers or {}).items()})
    return support.Response(status, merged, data)


class FakeTransport:
    """Records every request; plays back a fixed list of responses. No network."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.sent = []

    def send(self, method, url, headers, body=None, token=None):
        self.sent.append({"method": method, "url": url, "headers": dict(headers), "body": body, "token": token})
        if not self.responses:
            raise AssertionError("unexpected request: " + url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item(url) if callable(item) else item


class TransportTest(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {"CANVAS_TOKEN_EXAMPLE": TOKEN}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.sleeps = []

    def client(self, *responses):
        transport = FakeTransport(*responses)
        return support.Client(ACCOUNT, transport, sleep=self.sleeps.append), transport

    def assert_kind(self, kind, function, *args, **kwargs):
        with self.assertRaises(support.CanvasError) as raised:
            function(*args, **kwargs)
        self.assertEqual(raised.exception.kind, kind, str(raised.exception))
        self.assertNotIn(TOKEN, str(raised.exception))
        return raised.exception

    def test_requests_carry_string_ids_header_and_token_only_for_the_origin(self):
        client, transport = self.client(reply(body={"id": "1001"}))
        self.assertEqual(client.get("/api/v1/users/self"), {"id": "1001"})
        sent = transport.sent[0]
        self.assertEqual(sent["url"], ORIGIN + "/api/v1/users/self")
        self.assertEqual(sent["headers"]["Accept"], "application/json+canvas-string-ids")
        self.assertEqual(sent["token"], TOKEN)
        self.assertNotIn("Authorization", sent["headers"])
        self.assertNotIn(TOKEN, repr(client))

    def test_targets_outside_the_api_are_refused_before_sending(self):
        for target in ("/login", "//evil.example.com/api/v1/x", "/api/v1/../login", "/api/v1/%2e%2e/login", "https://evil.example.com/api/v1/users/self", "http://example.instructure.com/api/v1/users/self", "https://user@example.instructure.com/api/v1/users/self"):
            with self.subTest(target=target):
                client, transport = self.client()
                self.assert_kind("url_refused", client.get, target)
                self.assertEqual(transport.sent, [])

    def test_pagination_follows_opaque_next_links_and_adds_per_page(self):
        second = ORIGIN + "/api/v1/courses/123/assignments?page=bookmark:abc&per_page=100"
        third = ORIGIN + "/api/v1/courses/123/assignments?page=bookmark:def&per_page=100"
        client, transport = self.client(
            reply(body=[{"id": "1"}], headers={"Link": f'<{ORIGIN}/api/v1/courses/123/assignments?page=1>; rel="current", <{second}>; rel="next"'}),
            reply(body=[{"id": "2"}], headers={"Link": f'<{third}>; rel="next", <{ORIGIN}/api/v1/courses/123/assignments?page=1>; rel="first"'}),
            reply(body=[{"id": "3"}], headers={"Link": f'<{ORIGIN}/api/v1/courses/123/assignments?page=1>; rel="first"'}))
        result = client.paginate("/api/v1/courses/123/assignments", [("include[]", ["all_dates", "submission"])])
        self.assertEqual([item["id"] for item in result.items], ["1", "2", "3"])
        self.assertEqual(result.pages, 3)
        self.assertEqual(transport.sent[0]["url"], ORIGIN + "/api/v1/courses/123/assignments?include%5B%5D=all_dates&include%5B%5D=submission&per_page=100")
        self.assertEqual([sent["url"] for sent in transport.sent[1:]], [second, third])

    def test_link_header_parsing(self):
        parse = support.parse_link_header
        self.assertEqual(parse('<https://a/api/v1/x?page=2>; rel="next", <https://a/api/v1/x?page=9>; rel="last"'), {"next": "https://a/api/v1/x?page=2", "last": "https://a/api/v1/x?page=9"})
        self.assertEqual(parse('<https://a/api/v1/x?page=2>;rel=next'), {"next": "https://a/api/v1/x?page=2"})
        self.assertEqual(parse('<https://a/api/v1/x?page=2>; rel="next prev"'), {"next": "https://a/api/v1/x?page=2", "prev": "https://a/api/v1/x?page=2"})
        self.assertNotIn("next", parse('<https://a/api/v1/x?page=1>; rel="current"'))
        self.assertEqual(parse(None), {})

    def test_unsafe_next_links_cycles_and_the_page_cap_fail_the_listing(self):
        for link in ('<https://evil.example.com/api/v1/x?page=2>; rel="next"', f'<{ORIGIN}/login?page=2>; rel="next"', f'<http://example.instructure.com/api/v1/x?page=2>; rel="next"'):
            with self.subTest(link=link):
                client, transport = self.client(reply(body=[{"id": "1"}], headers={"Link": link}))
                self.assert_kind("url_refused", client.paginate, "/api/v1/x")
                self.assertEqual(len(transport.sent), 1)
        first = ORIGIN + "/api/v1/x?per_page=100"
        client, _ = self.client(reply(body=[], headers={"Link": f'<{ORIGIN}/api/v1/x?page=2>; rel="next"'}), reply(body=[], headers={"Link": f'<{first}>; rel="next"'}))
        error = self.assert_kind("pagination_cycle", client.paginate, "/api/v1/x")
        self.assertEqual(error.pages_read, 2)
        endless = [lambda url, n=n: reply(body=[{"id": str(n)}], headers={"Link": f'<{ORIGIN}/api/v1/x?page={n + 2}>; rel="next"'}) for n in range(6)]
        client, transport = self.client(*endless)
        error = self.assert_kind("page_cap", client.paginate, "/api/v1/x", max_pages=5)
        self.assertEqual((error.pages_read, len(transport.sent)), (5, 5))
        client, _ = self.client(reply(body={"not": "a list"}))
        self.assert_kind("malformed", client.paginate, "/api/v1/x")
        client, _ = self.client(reply(body=[{"id": "1"}], headers={"Link": f'<{ORIGIN}/api/v1/x?page=2>; rel="next"'}), reply(status=500))
        error = self.assert_kind("server_error", client.paginate, "/api/v1/x")
        self.assertEqual(error.pages_read, 1)

    def test_redirects(self):
        client, transport = self.client(reply(status=302, headers={"Location": "/api/v1/users/self?moved=1"}, raw=b""), reply(body={"id": "1001"}))
        self.assertEqual(client.get("/api/v1/users/self"), {"id": "1001"})
        self.assertEqual(transport.sent[1]["url"], ORIGIN + "/api/v1/users/self?moved=1")
        client, transport = self.client(reply(status=302, headers={"Location": "https://files.example.net/api/v1/users/self"}, raw=b""))
        self.assert_kind("url_refused", client.get, "/api/v1/users/self")
        self.assertEqual(len(transport.sent), 1)
        client, transport = self.client(reply(status=302, headers={"Location": "/api/v1/a"}, raw=b""), reply(status=302, headers={"Location": "/api/v1/b"}, raw=b""))
        self.assert_kind("redirect_refused", client.get, "/api/v1/users/self")
        self.assertEqual(len(transport.sent), 2)
        client, transport = self.client(reply(status=302, headers={"Location": "/api/v1/a"}, raw=b""))
        self.assert_kind("redirect_refused", client.request, "POST", "/api/v1/courses/123/pages", data={"wiki_page[title]": "x"})
        self.assertEqual(len(transport.sent), 1)

    def test_reads_back_off_a_bounded_number_of_times_and_writes_never_retry(self):
        client, transport = self.client(reply(status=429, headers={"Retry-After": "3"}, raw=b""), reply(status=403, raw=b"403 Forbidden (Rate Limit Exceeded)"), reply(body={"ok": True}))
        self.assertEqual(client.get("/api/v1/users/self"), {"ok": True})
        self.assertEqual((self.sleeps, len(transport.sent)), ([3, 4], 3))
        self.sleeps.clear()
        client, transport = self.client(*[reply(status=429, raw=b"") for _ in range(4)])
        self.assert_kind("throttled", client.get, "/api/v1/users/self")
        self.assertEqual((self.sleeps, len(transport.sent)), ([2, 4, 8], 4))
        self.sleeps.clear()
        client, transport = self.client(reply(status=429, raw=b""))
        error = self.assert_kind("throttled", client.request, "PUT", "/api/v1/courses/123/pages/9", data={"wiki_page[title]": "x"})
        self.assertIn("not retried", str(error))
        self.assertEqual((self.sleeps, len(transport.sent)), ([], 1))
        self.assertEqual(transport.sent[0]["headers"]["Content-Type"], "application/x-www-form-urlencoded")
        self.assertEqual(transport.sent[0]["body"], b"wiki_page%5Btitle%5D=x")

    def test_error_classification(self):
        cases = [
            (reply(status=401, body={"errors": [{"message": "Invalid access token."}]}), "token_rejected"),
            (reply(status=401, raw=b"", headers={"WWW-Authenticate": 'Bearer realm="canvas-lms"'}), "token_rejected"),
            (reply(status=401, body={"status": "unauthorized", "errors": [{"message": "user not authorized to perform that action"}]}, headers={"WWW-Authenticate": 'Bearer realm="canvas-lms"'}), "denied"),
            (reply(status=401, raw=b""), "denied"),
            (reply(status=403, body={"message": "That page has been disabled for this course"}), "denied"),
            (reply(status=404, body={"errors": [{"message": "The specified resource does not exist."}]}), "not_found"),
            (reply(status=422, body={"errors": {"title": [{"message": "is too long"}]}}), "request_rejected"),
            (reply(status=500, raw=b"<html>oops</html>", headers={"Content-Type": "text/html"}), "server_error"),
            (reply(status=200, raw=b"{not json"), "malformed"),
            (reply(status=200, raw=b"<html></html>", headers={"Content-Type": "text/html"}), "malformed"),
        ]
        for response, kind in cases:
            with self.subTest(kind=kind, status=response.status):
                client, _ = self.client(response)
                self.assert_kind(kind, client.get, "/api/v1/courses/123")
        client, _ = self.client(reply(status=422, body={"errors": {"title": [{"message": "is too long"}]}}))
        self.assertIn("is too long", str(self.assert_kind("request_rejected", client.get, "/api/v1/courses/123")))
        client, _ = self.client(reply(raw=b'while(1);{"id": "1"}'))
        self.assertEqual(client.get("/api/v1/courses/123"), {"id": "1"})

    def test_ids_are_kept_exactly(self):
        self.assertEqual(support.id_string(123450000000000789012), "123450000000000789012")
        self.assertEqual(support.id_string("123450000000000789012"), "123450000000000789012")
        self.assertEqual(support.id_string(json.loads('{"id": 9007199254740993}')["id"]), "9007199254740993")
        for value in (True, None, 1.5, -1, "12a", ""):
            with self.subTest(value=value):
                self.assert_kind("malformed", support.id_string, value)

    def test_identity(self):
        client, _ = self.client(reply(body={"id": "1001", "name": "Example User"}))
        self.assertEqual(support.verify_identity(client)["id"], "1001")
        client, _ = self.client(reply(body={"id": 2002, "name": "Someone Else"}))
        self.assert_kind("identity_mismatch", support.verify_identity, client)
        unconfirmed = support.Client(support.Account("example", ORIGIN, "", ACCOUNT.token_env, None, ()), FakeTransport())
        self.assert_kind("identity_unconfirmed", support.verify_identity, unconfirmed)


class WhoamiCommandTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"CANVAS_CONFIG_DIR": str(self.root)}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(support._file_settings.clear)
        env = self.root / ".env"
        env.write_text(f"CANVAS_TOKEN_EXAMPLE={TOKEN}\n")
        env.chmod(0o600)

    def run_whoami(self, user_id):
        entry = {"alias": "example", "base_url": ORIGIN, "user_id": user_id, "token_env": "CANVAS_TOKEN_EXAMPLE", "courses": []}
        (self.root / "canvas-accounts.json").write_text(json.dumps({"accounts": [entry]}))
        transport = FakeTransport(reply(body={"id": "1001", "name": "Example User"}), reply(body={"time_zone": "America/Chicago", "primary_email": "person@example.com", "login_id": "person"}))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = support.main(["whoami", "example"], transport=transport, today=datetime.date(2026, 10, 29))
        for text in (out.getvalue(), err.getvalue()):
            self.assertNotIn(TOKEN, text)
            self.assertNotIn("person@example.com", text)
        return code, out.getvalue(), err.getvalue()

    def test_whoami_reports_identity_without_contact_details(self):
        code, out, _ = self.run_whoami("")
        self.assertEqual(code, 0)
        self.assertIn('record "user_id": "1001"', out)
        self.assertIn("America/Chicago", out)
        code, out, _ = self.run_whoami("1001")
        self.assertIn("Identity matches", out)
        code, _, err = self.run_whoami("2002")
        self.assertEqual(code, 1)
        self.assertIn("[identity_mismatch]", err)


class _Handler(http.server.BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        _Handler.seen.append((self.path, self.headers.get("Authorization")))
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/target")
            self.end_headers()
        elif self.path == "/big":
            body = b"x" * 2048
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("LINK", '<https://example.instructure.com/api/v1/x?page=2>; rel="next"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


class UrllibTransportTest(unittest.TestCase):
    """The real transport against a loopback server: redirects are returned, never followed."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.seen.clear()

    def test_redirect_is_returned_and_not_followed(self):
        response = support.UrllibTransport().send("GET", self.base + "/start", {"Accept": support.ACCEPT}, token=TOKEN)
        self.assertEqual(response.status, 302)
        self.assertEqual(response.header("location"), "/target")
        self.assertEqual(_Handler.seen, [("/start", f"Bearer {TOKEN}")])

    def test_header_names_are_case_insensitive_and_size_is_capped(self):
        response = support.UrllibTransport().send("GET", self.base + "/list", {})
        self.assertIn('rel="next"', response.header("Link"))
        with self.assertRaises(support.CanvasError) as raised:
            support.UrllibTransport(max_bytes=1024).send("GET", self.base + "/big", {})
        self.assertEqual(raised.exception.kind, "too_large")

    def test_connection_failure_is_a_network_error_without_the_token(self):
        closed = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        port = closed.server_address[1]
        closed.server_close()
        with self.assertRaises(support.CanvasError) as raised:
            support.UrllibTransport(timeout=5).send("GET", f"http://127.0.0.1:{port}/x", {}, token=TOKEN)
        self.assertEqual(raised.exception.kind, "network_error")
        self.assertNotIn(TOKEN, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
