#!/usr/bin/env python3
"""Loopback Streamable HTTP MCP stand-in for connector tests: answers initialize and tools/list, records every request.

Usage: stand_in_server.py PORT_FILE REQUEST_LOG [json|sse]. It binds a free loopback port and writes the port number to PORT_FILE.
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT_FILE, REQUEST_LOG = sys.argv[1], sys.argv[2]
STREAMING = (sys.argv[3] if len(sys.argv) > 3 else "sse") == "sse"
SESSION = "stand-in-session"


class Handler(BaseHTTPRequestHandler):
    def _record(self, body):
        with open(REQUEST_LOG, "a") as log:
            log.write(json.dumps({"method": self.command, "session": self.headers.get("mcp-session-id"), "body": body}) + "\n")

    def _reply(self, status, payload=None, session=True):
        if payload is None:
            data, content_type = b"", None
        elif STREAMING:
            data, content_type = f"event: message\ndata: {json.dumps(payload)}\n\n".encode(), "text/event-stream"
        else:
            data, content_type = json.dumps(payload).encode(), "application/json"
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        if session:
            self.send_header("mcp-session-id", SESSION)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        self._record(raw)
        message = json.loads(raw)
        request_id = message.get("id")
        if request_id is None:
            return self._reply(202)
        if message.get("method") == "initialize":
            result = {"protocolVersion": message["params"]["protocolVersion"], "capabilities": {"tools": {}}, "serverInfo": {"name": "stand-in", "version": "0"}}
        elif message.get("method") == "tools/list":
            result = {"tools": [{"name": "execute_code", "inputSchema": {"type": "object"}}]}
        else:
            return self._reply(200, {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}})
        self._reply(200, {"jsonrpc": "2.0", "id": request_id, "result": result})

    def do_GET(self):
        self._record(None)
        self._reply(405, session=False)

    def do_DELETE(self):
        self._record(None)
        self._reply(200)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
with open(PORT_FILE, "w") as port_file:
    port_file.write(str(server.server_address[1]))
server.serve_forever()
