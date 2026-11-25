"""A minimal Chrome DevTools client using only the Python standard library, for one tab of the user's running Chrome or of a Chrome this tool starts with its own profile.

The tool's own Chrome uses a separate data directory and is driven over a private pipe that only this process holds: no network port opens, Chrome asks for no approval, and Chrome quits when the pipe closes. The user signs in to it themself.

Chrome 144+ lets a local program connect to the browser the user is already running once the user turns on remote debugging at chrome://inspect/#remote-debugging; Chrome then asks the user to Allow each connection and shows an automation banner while connected. This client reads the port from Chrome's DevToolsActivePort file, as Playwright's documented channel discovery does, waits for that approval, and then works only in a tab it creates itself and closes afterwards. It never attaches to the user's other tabs.
"""
import base64
import fcntl
import json
import os
import select
import shutil
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path


class BrowserError(Exception):
    pass


def user_data_dir():
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    if sys.platform.startswith("linux"):
        base = os.environ.get("CHROME_CONFIG_HOME") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
        return Path(base) / "google-chrome"
    raise BrowserError("Connecting to the running Chrome is supported on macOS and Linux only")


def devtools_port(directory=None):
    path = Path(directory or user_data_dir()) / "DevToolsActivePort"
    try:
        first = path.read_text(encoding="utf-8").splitlines()[0].strip()
        port = int(first)
    except (OSError, IndexError, ValueError):
        raise BrowserError("Chrome's remote debugging is off; turn it on at chrome://inspect/#remote-debugging")
    if not 0 < port < 65536:
        raise BrowserError("Chrome's DevToolsActivePort file is not valid")
    return port


class WebSocket:
    """Client side of RFC 6455 for a loopback connection: masked text frames out, fragmented and control frames in."""

    def __init__(self, host, port, path, timeout):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        self.sock.sendall(request.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise BrowserError("Chrome closed the connection during the handshake")
            head += chunk
        status, _, self.buffer = head.partition(b"\r\n\r\n")
        if not status.startswith(b"HTTP/1.1 101"):
            raise BrowserError("Chrome refused the DevTools connection")

    def _read(self, count):
        while len(self.buffer) < count:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise BrowserError("Chrome closed the DevTools connection")
            self.buffer += chunk
        data, self.buffer = self.buffer[:count], self.buffer[count:]
        return data

    def _frame(self, opcode, payload):
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        mask = os.urandom(4)
        self.sock.sendall(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, text):
        self._frame(0x1, text.encode())

    def receive(self, timeout):
        self.sock.settimeout(timeout)
        message, opcode = b"", None
        while True:
            first, second = self._read(2)
            fin, code, length = first & 0x80, first & 0x0F, second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if second & 0x80 else None
            payload = self._read(length)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if code == 0x9:
                self._frame(0xA, payload)
                continue
            if code == 0xA:
                continue
            if code == 0x8:
                raise BrowserError("Chrome closed the DevTools connection")
            if code in (0x1, 0x2):
                message, opcode = payload, code
            elif code == 0x0 and opcode is not None:
                message += payload
            else:
                raise BrowserError("Unexpected DevTools frame")
            if fin:
                return message.decode()

    def close(self):
        try:
            self._frame(0x8, b"")
        except OSError:
            pass
        self.sock.close()


def chrome_executable():
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            path = base / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome"
            if path.is_file():
                return str(path)
    elif sys.platform.startswith("linux"):
        for name in ("google-chrome", "google-chrome-stable"):
            if shutil.which(name):
                return shutil.which(name)
    raise BrowserError("Google Chrome was not found")


class Pipe:
    """A Chrome started with its own data directory and driven over --remote-debugging-pipe: NUL-terminated messages on descriptors 3 and 4."""

    def __init__(self, data_dir, url="about:blank", visible=False, executable=None):
        command = [executable or chrome_executable(), f"--user-data-dir={data_dir}", "--remote-debugging-pipe", "--no-first-run", "--no-default-browser-check", "--window-size=1400,1000"]
        # Chrome keeps sign-ins that are meant to end with the browser only when it restores its last session, as its "continue where you left off" setting does.
        command += ["--restore-last-session", *([] if visible else ["--headless=new"]), url]
        child_in, self.out = os.pipe()
        self.into, child_out = os.pipe()
        # Python's own child-error pipe must not land on 3 or 4, so both are kept open here while Chrome starts; the copies passed on sit well above them.
        held = [os.open(os.devnull, os.O_RDONLY)]
        while held[-1] < 5:
            held.append(os.open(os.devnull, os.O_RDONLY))
        reader, writer = (fcntl.fcntl(fd, fcntl.F_DUPFD, 16) for fd in (child_in, child_out))

        def place():
            os.dup2(reader, 3)
            os.dup2(writer, 4)

        try:
            self.process = subprocess.Popen(command, pass_fds=(3, 4), preexec_fn=place, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except OSError:
            os.close(self.out)
            os.close(self.into)
            raise BrowserError("Chrome could not be started")
        finally:
            for fd in [child_in, child_out, reader, writer, *held]:
                os.close(fd)
        self.buffer, self.closed = b"", False

    def send(self, text):
        data = text.encode() + b"\0"
        try:
            while data:
                data = data[os.write(self.out, data):]
        except OSError:
            raise BrowserError("Chrome closed the DevTools connection")

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\0" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.into], [], [], remaining)[0]:
                raise socket.timeout()
            chunk = os.read(self.into, 1 << 20)
            if not chunk:
                raise BrowserError("Chrome closed the DevTools connection")
            self.buffer += chunk
        message, _, self.buffer = self.buffer.partition(b"\0")
        return message.decode()

    def close(self):
        """Close the pipe, which makes Chrome quit and write its profile; only a Chrome that does not quit is ended."""
        if self.closed:
            return
        self.closed = True
        os.close(self.out)
        os.close(self.into)
        try:
            self.process.wait(20)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()


class Chrome:
    def __init__(self, socket_):
        self.ws, self.next_id = socket_, 1

    @classmethod
    def launch(cls, data_dir, url="about:blank", visible=False, executable=None):
        """Start Chrome with the tool's own data directory. A Chrome already using that directory makes the new one exit at once."""
        browser = cls(Pipe(data_dir, url, visible, executable))
        try:
            browser.call("Browser.getVersion")
        except BrowserError:
            browser.ws.close()
            raise BrowserError("Chrome did not start with Workday's own profile; another Chrome may be using it")
        return browser

    @classmethod
    def connect(cls, approval_timeout, port=None):
        port = port or devtools_port()
        try:
            browser = cls(WebSocket("localhost", port, "/devtools/browser", timeout=approval_timeout))
        except OSError:
            raise BrowserError("Chrome is not accepting DevTools connections; keep Chrome open with remote debugging on")
        # Chrome answers the first command only after the user clicks Allow.
        browser.call("Browser.getVersion", timeout=approval_timeout)
        return browser

    def call(self, method, params=None, session=None, timeout=30):
        ident = self.next_id
        self.next_id += 1
        message = {"id": ident, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.ws.send(json.dumps(message))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BrowserError(f"{method} got no reply")
            try:
                reply = json.loads(self.ws.receive(remaining))
            except socket.timeout:
                raise BrowserError(f"{method} got no reply")
            if reply.get("id") != ident:
                continue
            if "error" in reply:
                raise BrowserError(f"{method} failed: {reply['error'].get('message', 'error')}")
            return reply.get("result") or {}

    def pages(self):
        return [t for t in self.call("Target.getTargets").get("targetInfos", []) if t.get("type") == "page"]

    def open_tab(self, url, context_id=None):
        profile = {"browserContextId": context_id} if context_id else {}
        target = self.call("Target.createTarget", {"url": url, "background": True, **profile})["targetId"]
        session = self.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        return Tab(self, target, session)

    def close_pages(self, keep=None):
        """Close every tab but one, in a Chrome that is the tool's own."""
        for page in self.pages():
            if page["targetId"] != keep:
                self.call("Target.closeTarget", {"targetId": page["targetId"]})

    def close(self):
        self.ws.close()


class Tab:
    def __init__(self, chrome, target, session):
        self.chrome, self.target, self.session = chrome, target, session

    def evaluate(self, script, arg=None, timeout=30):
        expression = f"({script})({json.dumps(arg)})" if arg is not None else f"({script})()"
        result = self.chrome.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True}, self.session, timeout)
        if "exceptionDetails" in result:
            raise BrowserError("A page script failed")
        return (result.get("result") or {}).get("value")

    def wait_for(self, script, arg=None, timeout=30, interval=0.25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.evaluate(script, arg):
                    return True
            except BrowserError:
                pass  # The page may be between documents during navigation.
            time.sleep(interval)
        raise BrowserError("The page did not reach the expected state in time")

    def navigate(self, url):
        self.chrome.call("Page.navigate", {"url": url}, self.session)

    def insert_text(self, text):
        """Type text into the focused element as keyboard input would."""
        self.chrome.call("Input.insertText", {"text": text}, self.session)

    def url(self):
        return self.evaluate("() => location.href")

    def close(self):
        self.chrome.call("Target.closeTarget", {"targetId": self.target})
