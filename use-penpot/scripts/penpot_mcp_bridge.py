#!/usr/bin/env python3
"""Relay MCP messages between a stdio client and a Penpot Streamable HTTP MCP server.

The server URL embeds the user's MCP key, so it is read from the environment only and every write to stderr is redacted.
"""

import logging
import os
import sys
import urllib.parse

import anyio

REDACTED = "[redacted]"
URL_VARIABLE = "PENPOT_MCP_SERVER_URL"


class RedactingStream:
    """Line-buffered text stream wrapper that replaces secret strings before they reach the wrapped stream."""

    def __init__(self, stream, secrets):
        self._stream = stream
        self._secrets = sorted({secret for secret in secrets if secret}, key=len, reverse=True)
        self._buffer = ""

    def _redact(self, text):
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def write(self, text):
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._stream.write(self._redact(line) + "\n")
        return len(text)

    def flush(self):
        if self._buffer:
            self._stream.write(self._redact(self._buffer))
            self._buffer = ""
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def secret_forms(url):
    """Return the URL and its userToken in the spellings an error message might contain."""
    forms = {url, urllib.parse.unquote(url)}
    query = urllib.parse.urlsplit(url).query
    for part in query.split("&"):
        key, _, raw = part.partition("=")
        if key == "userToken" and raw:
            value = urllib.parse.unquote_plus(raw)
            forms.update({raw, value, urllib.parse.quote(value, safe=""), urllib.parse.quote_plus(value)})
    return forms


def leaf_errors(error):
    """Flatten exception groups into their leaf exceptions."""
    if isinstance(error, BaseExceptionGroup):
        for inner in error.exceptions:
            yield from leaf_errors(inner)
    else:
        yield error


async def forward(source, sink, label, scope):
    """Copy messages from one side to the other; either side ending stops the relay."""
    try:
        async for item in source:
            if isinstance(item, Exception):
                print(f"penpot-mcp: dropped an unreadable message from the {label}: {type(item).__name__}", file=sys.stderr)
                continue
            await sink.send(item)
    finally:
        scope.cancel()


async def relay(url):
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.stdio import stdio_server

    # Closing both write streams on the way out lets each transport's writer task finish instead of waiting forever.
    async with stdio_server() as (client_read, client_write), client_write:
        async with streamable_http_client(url) as (server_read, server_write), server_write:
            async with anyio.create_task_group() as group:
                group.start_soon(forward, client_read, server_write, "client", group.cancel_scope)
                group.start_soon(forward, server_read, client_write, "server", group.cancel_scope)


async def list_tools(url):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
    host = urllib.parse.urlsplit(url).hostname or "the configured server"
    names = [tool.name for tool in result.tools]
    print(f"Penpot MCP tools from {host} ({len(names)}): {', '.join(names)}")


def main(argv):
    mode = argv[1] if len(argv) > 1 else "relay"
    if mode not in ("relay", "--list-tools"):
        print("penpot-mcp: unknown option; run penpot-mcp --help", file=sys.stderr)
        return 2
    url = os.environ.pop(URL_VARIABLE, "")
    if not url:
        print(f"penpot-mcp: {URL_VARIABLE} is not set; run the setup-penpot check", file=sys.stderr)
        return 2
    sys.stderr = RedactingStream(sys.__stderr__, secret_forms(url))
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr, format="penpot-mcp: %(levelname)s %(name)s: %(message)s")
    try:
        anyio.run(list_tools if mode == "--list-tools" else relay, url)
    except KeyboardInterrupt:
        return 130
    except BaseException as error:  # noqa: BLE001 - report every failure in redacted form instead of a raw traceback
        details = "; ".join(f"{type(leaf).__name__}: {leaf}" for leaf in leaf_errors(error))
        print(f"penpot-mcp: the connection ended with an error: {details}", file=sys.stderr)
        return 1
    finally:
        sys.stderr.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
