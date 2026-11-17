"""Exercise the real curl transport with synthetic credentials and loopback HTTP only."""

import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit


CLIENT = Path(__file__).resolve().parents[1] / "scripts" / "client.sh"
SYNTHETIC = "synthetic-msal-transport-credential.not-a-real-token"


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="msal-transport-test-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.requests = []
        requests = self.requests

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                requests.append((self.command, self.path, dict(self.headers), body))
                if self.path == "/disconnect":
                    self.close_connection = True
                    return
                if self.path == "/redirect":
                    self.send_response(302)
                    self.send_header("Location", f"http://localhost:{self.server.server_port}/bytes")
                    self.end_headers()
                    return
                if self.path == "/forbidden":
                    self.send_response(403)
                    body = b'{"error":{"code":"Denied","message":"synthetic refusal"}}'
                else:
                    self.send_response(200)
                    body = b"PK\x03\x04synthetic-docx" if self.path == "/bytes" else b'{"ok":true}'
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_PATCH = do_PUT = handle_request

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.secret = self.root / "synthetic-secret"
        self.secret.write_text(SYNTHETIC)
        self.secret.chmod(0o600)
        (self.root / "temp").mkdir()
        (self.root / "bin").mkdir()
        (self.root / "curl-home").mkdir()
        (self.root / "curl-home" / ".curlrc").write_text('header = "X-Unwanted-Default: present"\n')
        real_curl = shutil.which("curl")
        self.assertIsNotNone(real_curl)
        # Observe actual executable arguments and environment before replacing this process with real curl. Only synthetic data is used.
        wrapper = self.root / "bin" / "curl"
        wrapper.write_text(f"#!{sys.executable}\n" + """import json, os, sys
from pathlib import Path
secret = Path(os.environ['MSAL_TEST_SECRET_FILE']).read_text()
with open(os.environ['MSAL_TEST_ARGV'], 'a') as handle:
    handle.write(json.dumps({'argv': sys.argv[1:], 'secretInEnvironment': any(secret in value for value in os.environ.values()), 'tokenVariableExported': 'm365_msal_token' in os.environ}) + '\\n')
os.execv(os.environ['MSAL_TEST_CURL'], [os.environ['MSAL_TEST_CURL'], *sys.argv[1:]])
""")
        wrapper.chmod(0o700)
        self.env = {
            **os.environ,
            "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            "TMPDIR": str(self.root / "temp"),
            "CURL_HOME": str(self.root / "curl-home"),
            "MSAL_TEST_CLIENT": str(CLIENT),
            "MSAL_TEST_SECRET_FILE": str(self.secret),
            "MSAL_TEST_ARGV": str(self.root / "argv.jsonl"),
            "MSAL_TEST_CURL": real_curl,
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
            # An inherited exported variable with this name must not make the acquired credential reach curl's environment.
            "m365_msal_token": "inherited-placeholder",
        }

    def call(self, method="GET", endpoint="/json", body="", *options):
        script = '''source "$MSAL_TEST_CLIENT"
_m365_access_token() { cat "$MSAL_TEST_SECRET_FILE"; }
set -ax
_m365_http_msal "$@"
'''
        result = subprocess.run(["bash", "-c", script, "test", method, "example", self.base + endpoint, body, *options], env=self.env, capture_output=True, text=True, timeout=15)
        self.assertNotIn(SYNTHETIC, result.stdout + result.stderr)
        self.assertEqual(list((self.root / "temp").iterdir()), [])
        log = self.root / "argv.jsonl"
        if log.exists():
            self.assertNotIn(SYNTHETIC, log.read_text())
            for line in log.read_text().splitlines():
                entry = json.loads(line)
                self.assertEqual(entry["argv"][0], "-q")
                self.assertFalse(entry["secretInEnvironment"])
                self.assertFalse(entry["tokenVariableExported"])
        return result

    def assert_authenticated(self, request):
        self.assertEqual(request[2].get("Authorization"), "Bearer " + SYNTHETIC)
        self.assertNotIn("X-Unwanted-Default", request[2])

    def test_get_json_upload_and_download_keep_credentials_off_arguments_and_traces(self):
        result = self.call("GET", "/json", "", "--data-urlencode", "$select=id", "-H", "Prefer: synthetic")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        self.assertEqual(parse_qs(urlsplit(self.requests[-1][1]).query), {"$select": ["id"]})
        self.assertEqual(self.requests[-1][2]["Prefer"], "synthetic")

        result = self.call("PATCH", "/json", '{"value":"synthetic"}')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.requests[-1][3], b'{"value":"synthetic"}')

        upload = self.root / "upload.bin"
        upload.write_bytes(b"synthetic\x00upload")
        result = self.call("PUT", "/json", "", "--upload-file", str(upload), "-H", 'If-Match: "synthetic-etag"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.requests[-1][3], upload.read_bytes())
        self.assertEqual(self.requests[-1][2]["If-Match"], '"synthetic-etag"')

        output = self.root / "download.docx"
        result = self.call("GET", "/bytes", "", "--output-file", str(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), b"PK\x03\x04synthetic-docx")
        for request in self.requests:
            self.assert_authenticated(request)

    def test_download_redirect_does_not_forward_authorization_to_another_host(self):
        result = self.call("GET", "/redirect", "", "--output-file", str(self.root / "redirect.docx"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.requests), 2)
        self.assert_authenticated(self.requests[0])
        self.assertNotIn("Authorization", self.requests[1][2])

    def test_failures_clean_up_and_invalid_tokens_never_send_a_request(self):
        result = self.call("GET", "/forbidden")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Denied: synthetic refusal", result.stderr)
        output = self.root / "failed.docx"
        result = self.call("GET", "/disconnect", "", "--output-file", str(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        count = len(self.requests)
        for value in ("", SYNTHETIC + "\r\nInjected: header"):
            self.secret.write_text(value)
            result = self.call()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid bearer token", result.stderr)
        self.assertEqual(len(self.requests), count)


if __name__ == "__main__":
    unittest.main()
