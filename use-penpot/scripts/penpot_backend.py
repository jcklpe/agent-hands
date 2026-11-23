"""Shared access to Penpot's backend RPC API for use-penpot's commands.

The access token comes from setup-penpot's configuration (PENPOT_ACCESS_TOKEN) and reaches curl on standard input, never in arguments or output. Requests go through curl because Penpot's hosted front end refuses Python's own HTTP client.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

ZERO = "00000000-0000-0000-0000-000000000000"
DEFAULT_BASE = "https://design.penpot.app"
RESERVED_KEYS = {"PENPOT_ENV_FILE", "PENPOT_CONFIG_DIR", "PENPOT_SETUP_DIR", "PENPOT_PYTHON"}
# curl exit codes that mean the request never reached a server: proxy or host lookup, connection and TLS handshake failures.
NOT_SENT_CURL_CODES = {5, 6, 7, 35}


class BackendError(Exception):
    """A failed backend call. `outcome` says what is known about a write: "refused" when Penpot answered with an error, "not_sent" when no connection was made, "unknown" otherwise."""

    def __init__(self, message, outcome="refused"):
        super().__init__(message)
        self.outcome = outcome


def env_path():
    setup_dir = Path(os.environ.get("PENPOT_SETUP_DIR") or Path(__file__).resolve().parents[2] / "setup-penpot")
    config_dir = Path(os.environ.get("PENPOT_CONFIG_DIR") or setup_dir)
    selected = os.environ.get("PENPOT_ENV_FILE")
    if selected:
        path = Path(selected) if os.path.isabs(selected) else config_dir / selected
        if not path.is_file():
            raise BackendError("The selected PENPOT_ENV_FILE does not exist")
        return path
    path = config_dir / ".env"
    return path if path.is_file() else None


def access_token():
    # Exported values take precedence, as in setup-penpot's loader; the file is parsed as data, never executed.
    token = os.environ.get("PENPOT_ACCESS_TOKEN", "").strip()
    path = None if token else env_path()
    if path:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:]
            if "=" not in line:
                raise BackendError("Invalid Penpot env assignment")
            key, value = (part.strip() for part in line.split("=", 1))
            if key in RESERVED_KEYS or not key.startswith("PENPOT_") or not key.replace("_", "").isalnum():
                raise BackendError("Invalid Penpot env key")
            if value and value[0] in "\"'":
                if len(value) < 2 or value[-1] != value[0]:
                    raise BackendError("Unclosed quote in Penpot env file")
                value = value[1:-1]
            if key == "PENPOT_ACCESS_TOKEN":
                token = value
    if not token or any(c.isspace() or c == '"' for c in token):
        raise BackendError("PENPOT_ACCESS_TOKEN is not configured; see the setup-penpot skill")
    return token


def curl_rpc(base, token):
    def call(method, params):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as body:
            json.dump(params, body)
        try:
            config = f'header = "Authorization: Token {token}"\nheader = "Content-Type: application/json"\nheader = "Accept: application/json"\n'
            result = subprocess.run(["curl", "-sS", "--max-time", "120", "-K", "-", "-X", "POST", "--data-binary", f"@{body.name}", "-w", "\n%{http_code}", f"{base}/api/main/methods/{method}"], input=config, capture_output=True, text=True)
        finally:
            os.unlink(body.name)
        if result.returncode != 0:
            raise BackendError(f"{method}: curl failed ({result.returncode})", "not_sent" if result.returncode in NOT_SENT_CURL_CODES else "unknown")
        text, _, status = result.stdout.rpartition("\n")
        if status != "200":
            # Penpot runs each update-file in one database transaction, so a structured Penpot error means nothing was committed; anything else, such as a gateway timeout page, leaves the outcome unknown.
            try:
                detail = json.loads(text)
                detail = {k: detail[k] for k in ("type", "code", "hint") if k in detail}
                outcome = "refused" if detail.get("type") else "unknown"
            except (ValueError, AttributeError, TypeError):
                detail, outcome = text[:200], "unknown"
            raise BackendError(f"{method}: HTTP {status} {detail}", outcome)
        return json.loads(text) if text.strip() else None
    return call


def page_names(file_data):
    index = (file_data.get("data") or {}).get("pagesIndex") or {}
    return {pid: (page or {}).get("name") for pid, page in index.items()}


def page_order(file_data):
    return list((file_data.get("data") or {}).get("pages") or [])
