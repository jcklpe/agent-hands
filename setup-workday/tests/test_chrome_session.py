"""The standard-library DevTools client against a loopback stand-in for Chrome; no real browser."""

import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import chrome_session as CS  # noqa: E402

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def frame(opcode, payload, fin=True):
    head = bytes([(0x80 if fin else 0) | opcode])
    n = len(payload)
    head += bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n) if n < 65536 else bytes([127]) + struct.pack(">Q", n)
    return head + payload


def read_frame(conn):
    def exact(n):
        data = b""
        while len(data) < n:
            data += conn.recv(n - len(data))
        return data
    first, second = exact(2)
    n = second & 0x7F
    n = struct.unpack(">H", exact(2))[0] if n == 126 else struct.unpack(">Q", exact(8))[0] if n == 127 else n
    assert second & 0x80, "client frames must be masked"
    mask = exact(4)
    return first & 0x0F, bytes(b ^ mask[i % 4] for i, b in enumerate(exact(n)))


class StandIn:
    """Accepts one connection, completes the handshake and answers each command through a handler."""

    def __init__(self, handler):
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port, self.handler, self.received = self.server.getsockname()[1], handler, []
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        conn, _ = self.server.accept()
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        key = [line.split(b": ")[1] for line in request.split(b"\r\n") if line.lower().startswith(b"sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1(key + GUID.encode()).digest())
        conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
        while True:
            try:
                opcode, payload = read_frame(conn)
            except (OSError, IndexError, ValueError):
                return
            if opcode == 0x8:
                conn.close()
                return
            if opcode != 0x1:
                self.received.append((opcode, payload))
                continue
            message = json.loads(payload)
            self.received.append(message)
            for raw in self.handler(message):
                conn.sendall(raw)


def reply(message, result):
    return frame(0x1, json.dumps({"id": message["id"], "result": result}).encode())


class SessionTests(unittest.TestCase):
    def test_port_comes_from_devtools_active_port_and_a_missing_file_names_the_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "DevToolsActivePort").write_text("9222\n/devtools/browser/abc\n")
            self.assertEqual(CS.devtools_port(folder), 9222)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(CS.BrowserError, "chrome://inspect"):
                CS.devtools_port(folder)

    def test_replies_are_matched_across_events_pings_fragments_and_long_frames(self):
        big = {"blob": "x" * 70000}

        def handler(message):
            if message["method"] == "Browser.getVersion":
                yield frame(0x9, b"ping")
                yield frame(0x1, json.dumps({"method": "Target.targetCreated", "params": {}}).encode())
                text = json.dumps({"id": message["id"], "result": {"product": "Chrome/0"}}).encode()
                yield frame(0x1, text[:10], fin=False)
                yield frame(0x0, text[10:])
            elif message["method"] == "Runtime.evaluate":
                yield reply(message, {"result": {"type": "object", "value": big}})
            else:
                yield reply(message, {"targetInfos": [{"type": "page", "url": "u", "browserContextId": "c"}, {"type": "service_worker"}]})

        stand_in = StandIn(handler)
        chrome = CS.Chrome.connect(5, port=stand_in.port)
        self.assertEqual(chrome.pages(), [{"type": "page", "url": "u", "browserContextId": "c"}])
        tab = CS.Tab(chrome, "t1", "s1")
        self.assertEqual(tab.evaluate("(x) => x", {"a": 1}), big)
        evaluate = [m for m in stand_in.received if isinstance(m, dict) and m.get("method") == "Runtime.evaluate"][0]
        self.assertEqual((evaluate["sessionId"], evaluate["params"]["expression"]), ("s1", '((x) => x)({"a": 1})'))
        self.assertIn((0xA, b"ping"), stand_in.received)
        chrome.close()

    def test_errors_and_silence_become_browser_errors(self):
        def handler(message):
            if message["method"] == "Browser.getVersion":
                yield reply(message, {})
            elif message["method"] == "Target.createTarget":
                yield frame(0x1, json.dumps({"id": message["id"], "error": {"message": "No such context"}}).encode())
            elif message["method"] == "Runtime.evaluate":
                yield reply(message, {"exceptionDetails": {"text": "boom"}})

        chrome = CS.Chrome.connect(5, port=StandIn(handler).port)
        with self.assertRaisesRegex(CS.BrowserError, "No such context"):
            chrome.open_tab("https://example.invalid/", "c")
        with self.assertRaisesRegex(CS.BrowserError, "script failed"):
            CS.Tab(chrome, "t", "s").evaluate("() => 1")
        with self.assertRaisesRegex(CS.BrowserError, "no reply"):
            chrome.call("Page.navigate", {}, timeout=0.3)
        chrome.close()

    def test_without_approval_the_first_command_times_out(self):
        port = StandIn(lambda message: iter(())).port
        with self.assertRaisesRegex(CS.BrowserError, "no reply"):
            CS.Chrome.connect(0.5, port=port)

    def test_a_new_tab_is_created_in_the_background_in_the_chosen_profile_and_attached_alone(self):
        def handler(message):
            result = {"Browser.getVersion": {}, "Target.createTarget": {"targetId": "T"}, "Target.attachToTarget": {"sessionId": "S"}, "Target.closeTarget": {"success": True}}[message["method"]]
            yield reply(message, result)

        stand_in = StandIn(handler)
        chrome = CS.Chrome.connect(5, port=stand_in.port)
        tab = chrome.open_tab("https://example.invalid/x", "ctx")
        tab.close()
        sent = [m for m in stand_in.received if isinstance(m, dict)]
        self.assertEqual([m["method"] for m in sent], ["Browser.getVersion", "Target.createTarget", "Target.attachToTarget", "Target.closeTarget"])
        self.assertEqual(sent[1]["params"], {"url": "https://example.invalid/x", "browserContextId": "ctx", "background": True})
        self.assertEqual(sent[2]["params"], {"targetId": "T", "flatten": True})
        self.assertEqual(sent[3]["params"], {"targetId": "T"})
        chrome.close()


STAND_IN = """#!{python}
import json, os, sys
open(sys.argv[0] + ".args", "w").write(json.dumps(sys.argv[1:]))
if "{mode}" == "busy":
    sys.exit(21)
buffer = b""
while True:
    chunk = os.read(3, 65536)
    if not chunk:
        open(sys.argv[0] + ".quit", "w").write("quit")
        sys.exit(0)
    buffer += chunk
    while b"\\0" in buffer:
        raw, _, buffer = buffer.partition(b"\\0")
        message = json.loads(raw)
        if message["method"] == "Silent.call":
            continue
        event = json.dumps({{"method": "Target.targetCreated"}}).encode() + b"\\0"
        reply = json.dumps({{"id": message["id"], "result": {{"method": message["method"], "params": message["params"], "blob": "x" * 70000}}}}).encode() + b"\\0"
        for part in (event, reply[:10], reply[10:]):
            while part:
                part = part[os.write(4, part):]
"""


class PipeTests(unittest.TestCase):
    """A stand-in program speaking Chrome's pipe protocol on descriptors 3 and 4."""

    def program(self, mode="normal"):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name, "chrome")
        path.write_text(STAND_IN.format(python=sys.executable, mode=mode), encoding="utf-8")
        path.chmod(0o700)
        return path

    def test_chrome_runs_on_its_own_data_directory_and_quits_when_the_pipe_closes(self):
        path = self.program()
        before = len(os.listdir("/dev/fd"))
        chrome = CS.Chrome.launch("/private/example/profile", executable=str(path))
        self.assertEqual(chrome.call("Target.getTargets", {"a": 1})["params"], {"a": 1})
        self.assertEqual(len(chrome.call("Big.reply")["blob"]), 70000)
        with self.assertRaisesRegex(CS.BrowserError, "no reply"):
            chrome.call("Silent.call", timeout=0.3)
        process = chrome.ws.process
        chrome.close()
        chrome.close()
        self.assertEqual(process.returncode, 0)
        self.assertTrue(Path(str(path) + ".quit").exists())
        self.assertLessEqual(len(os.listdir("/dev/fd")), before)
        args = json.loads(Path(str(path) + ".args").read_text())
        self.assertIn("--user-data-dir=/private/example/profile", args)
        for flag in ("--remote-debugging-pipe", "--restore-last-session", "--headless=new"):
            self.assertIn(flag, args)
        self.assertEqual(args[-1], "about:blank")
        self.assertFalse([a for a in args if "remote-debugging-port" in a or "no-sandbox" in a or "password-store" in a or "keychain" in a or "user-agent" in a])

    def test_a_visible_chrome_opens_the_given_page(self):
        path = self.program()
        CS.Chrome.launch("/private/example/profile", "https://example.invalid/", visible=True, executable=str(path)).close()
        args = json.loads(Path(str(path) + ".args").read_text())
        self.assertEqual(args[-1], "https://example.invalid/")
        self.assertNotIn("--headless=new", args)

    def test_only_the_kept_tab_stays(self):
        sent = []

        class Recorder(CS.Chrome):
            def call(self, method, params=None, session=None, timeout=30):
                sent.append((method, params))
                return {"targetInfos": [{"type": "page", "targetId": "A"}, {"type": "page", "targetId": "B"}, {"type": "browser_ui", "targetId": "U"}]}

        Recorder(None).close_pages(keep="B")
        self.assertEqual(sent, [("Target.getTargets", None), ("Target.closeTarget", {"targetId": "A"})])

    def test_a_profile_already_in_use_and_a_missing_program_are_reported(self):
        with self.assertRaisesRegex(CS.BrowserError, "another Chrome"):
            CS.Chrome.launch("/private/example/profile", executable=str(self.program("busy")))
        with self.assertRaisesRegex(CS.BrowserError, "could not be started"):
            CS.Chrome.launch("/private/example/profile", executable="/nonexistent/chrome")


if __name__ == "__main__":
    unittest.main()
