#!/usr/bin/env python3
"""Drive the penpot-mcp stdio relay like an MCP client: initialize, list tools, then close stdin."""

import json
import queue
import subprocess
import sys
import threading

TIMEOUT_SECONDS = 60


def main(command):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()

    def send(message):
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()

    def response(request_id):
        waited = 0
        while waited < TIMEOUT_SECONDS:
            try:
                message = json.loads(lines.get(timeout=1))
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError(f"the relay exited with status {process.returncode} before answering request {request_id}")
                waited += 1
                continue
            if message.get("id") == request_id:
                return message
        raise TimeoutError(f"no answer to request {request_id} within {TIMEOUT_SECONDS} seconds")

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "relay-probe", "version": "0"}}})
        initialized = response(1)
        assert "result" in initialized, initialized
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = response(2)
        names = [tool["name"] for tool in listed["result"]["tools"]]
        assert "execute_code" in names, names
    except BaseException:
        process.kill()
        print(process.stderr.read(), file=sys.stderr)
        raise
    finally:
        if not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            raise
    stderr = process.stderr.read()
    print(json.dumps({"tools": names, "exit": process.returncode, "stderr": stderr}))
    return 0 if process.returncode == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
