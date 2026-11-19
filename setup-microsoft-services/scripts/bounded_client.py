"""Internal support for bounded capability commands; deliberately no request CLI."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid
from urllib.parse import urlsplit, parse_qsl

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 2048 or any(ord(c) < 33 for c in value) or any(c in value for c in "/\\?#") or value in (".", ".."):
        raise ValueError("Use an exact nonempty identifier from a bounded service read")
    return value


class ProviderError(RuntimeError):
    pass


class Client:
    def __init__(self, alias, service):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", alias) or service not in ("files", "mail"):
            raise ValueError("Invalid account alias or capability")
        self.alias, self.service = alias, service

    def _call(self, request):
        # Only this fixed script invokes the existing authenticated transport. Private payloads arrive on stdin, never in shell source or argv.
        script = '''set -eu
set +ax
source "$1"
_m365_load_env
_m365_require_enabled "$2" "$3"
input="$(cat)"
if [ "$(printf '%s' "$input" | jq -r .kind)" = config ]; then
  _m365_account_value "$2" '{write: (.files.write_enabled // false), mail_write: (.mail.write_enabled // false)}'
  exit
fi
method="$(printf '%s' "$input" | jq -r .method)"
url="$(printf '%s' "$input" | jq -r .url)"
body="$(printf '%s' "$input" | jq -r '.body // empty')"
args=()
while IFS= read -r header; do args+=( -H "$header" ); done < <(printf '%s' "$input" | jq -r '.headers | to_entries[] | .key + ": " + .value')
if [ "$(printf '%s' "$input" | jq -r '.output // empty')" != "" ]; then
  _m365_http "$method" "$2" "$url" "$body" --output-file "$(printf '%s' "$input" | jq -r .output)" ${args[@]+"${args[@]}"}
else
  _m365_http "$method" "$2" "$url" "$body" ${args[@]+"${args[@]}"}
fi
'''
        result = subprocess.run(["bash", "-c", script, "bounded-client", str(HERE / "client.sh"), self.alias, self.service], input=canonical(request), text=True, capture_output=True, timeout=180)
        if result.returncode:
            # Provider diagnostics can contain mail content, signed URLs or identities. The public command reports a bounded failure, never their raw output.
            raise ProviderError("Microsoft request failed or its outcome is unknown. Check account access; inspect the receipt before retrying a write.")
        try:
            return json.loads(result.stdout or "{}")
        except ValueError as exc:
            raise ProviderError("Invalid provider response; reconcile any dispatched operation") from exc

    def require_write(self):
        cfg = self._call({"kind": "config"})
        if cfg.get("write" if self.service == "files" else "mail_write") is not True:
            raise ValueError(f"{self.service}.write_enabled is required. Use approved Microsoft setup; no opt-in or scope was changed.")

    def request(self, method, path, body=None, headers=None, output=None):
        if method not in ("GET", "POST", "PATCH", "DELETE") or not path.startswith("/") or any(c in path for c in "\r\n#"):
            raise ValueError("Invalid internal request")
        # Restrict the internal transport too: notably no send, permanentDelete, permissions mutation or arbitrary Graph resource.
        parsed = urlsplit(path); segment = r"[A-Za-z0-9_.~%+-]+"
        if parsed.netloc or any(k.lower() not in ("$select", "$top", "$skiptoken", "$skip", "$orderby", "@microsoft.graph.conflictbehavior") for k, _ in parse_qsl(parsed.query)):
            raise ValueError("Request is outside the selected capability")
        profile = path == "/me?$select=id,mail,userPrincipalName" and method == "GET"
        if self.service == "files":
            resource = re.fullmatch(r"/drives/" + segment + r"/items/" + segment, parsed.path)
            readable = re.fullmatch(r"/drives/" + segment + r"(?:(?:/items/" + segment + r"|/root)(?:/(?:children|permissions|versions|content))?)?", parsed.path)
            allowed = method == "GET" and readable or method == "PATCH" and resource and parsed.query == "@microsoft.graph.conflictBehavior=fail" or method == "DELETE" and resource and not parsed.query
            if method == "PATCH" and (not isinstance(body, dict) or not set(body) <= {"name", "parentReference"} or not body.get("name") or "parentReference" in body and set(body["parentReference"]) != {"id"}):
                raise ValueError("Only conflict-refusing file name/parent updates are supported")
            if method == "DELETE" and body is not None: raise ValueError("Recycle does not accept a body")
        else:
            resource = re.fullmatch(r"/me/messages/" + segment, parsed.path)
            attachment_metadata = re.fullmatch(r"/me/messages/" + segment + r"/attachments", parsed.path) and parsed.query == "$select=id,name,contentType,size,isInline&$top=100"
            allowed = method == "GET" and (resource or attachment_metadata) or method == "PATCH" and resource and not parsed.query or method == "POST" and re.fullmatch(r"/me/messages/" + segment + r"/createReply(?:All)?", parsed.path) and not parsed.query
            if method == "POST" and body != {}: raise ValueError("Reply creation starts from the provider-generated draft")
            if method == "PATCH" and (not isinstance(body, dict) or set(body) != {"body"} or set(body["body"]) != {"contentType", "content"} or body["body"]["contentType"] != "HTML"):
                raise ValueError("Only a guarded draft-body update is supported")
        if not profile and not allowed: raise ValueError("Request is outside the selected capability")
        headers = headers or {}
        if any(k not in ("If-Match", "Prefer") or not isinstance(v, str) or any(c in v for c in "\r\n") for k, v in headers.items()):
            raise ValueError("Invalid internal header")
        if method in ("PATCH", "DELETE") and not headers.get("If-Match"): raise ValueError("A mutation requires If-Match")
        if "Prefer" in headers and (self.service != "mail" or headers["Prefer"] != 'IdType="ImmutableId", outlook.body-content-type="html"'):
            raise ValueError("Only bounded immutable-ID/HTML preferences are supported")
        if output and (self.service != "files" or method != "GET" or not parsed.path.endswith("/content")):
            raise ValueError("Only file content can be downloaded")
        return self._call({"kind": "request", "method": method, "url": "https://graph.microsoft.com/v1.0" + path, "body": canonical(body) if body is not None else "", "headers": headers, **({"output": str(output)} if output else {})})

    def identity(self):
        value = self.request("GET", "/me?$select=id,mail,userPrincipalName")
        if not value.get("id") or not (value.get("mail") or value.get("userPrincipalName")):
            raise ValueError("Authenticated mailbox identity is unavailable")
        return {k: value.get(k) for k in ("id", "mail", "userPrincipalName")}


class Store:
    """Owner-only plans and exclusive durable receipts. Existing paths are never silently adopted."""
    def __init__(self, root, alias):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", alias):
            raise ValueError("Invalid account alias")
        self.root = Path(root)
        for directory in (self.root, self.root / alias):
            if not directory.exists() and not directory.is_symlink():
                directory.mkdir(mode=0o700)
            st = directory.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise ValueError("Unsafe private state directory; require an owner-only real directory")
        self.root /= alias

    def path(self, operation, suffix):
        if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", operation):
            raise ValueError("Use the operation ID returned by preview")
        return self.root / (operation + suffix)

    def write(self, path, value):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(canonical(value) + "\n"); out.flush(); os.fsync(out.fileno())
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def read(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as source:
            st = os.fstat(source.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_size > 4_000_000:
                raise ValueError("Unsafe private operation file")
            return json.load(source)

    def plan(self, value):
        value = {**value, "operation": str(uuid.uuid4())}
        value["hash"] = digest(value)
        self.write(self.path(value["operation"], ".plan.json"), value)
        return value

    def load(self, operation, expected_hash=None):
        value = self.read(self.path(operation, ".plan.json"))
        content = {k: v for k, v in value.items() if k != "hash"}
        if value.get("operation") != operation or digest(content) != value.get("hash") or expected_hash is not None and value["hash"] != expected_hash:
            raise ValueError("Preview hash mismatch; no write was sent")
        return value

    def dispatched(self, operation):
        return self.path(operation, ".dispatch.json").exists()

    def dispatch(self, operation, value):
        self.write(self.path(operation, ".dispatch.json"), value)

    def receipt(self, operation, value, suffix=".result.json"):
        self.write(self.path(operation, suffix), value)

    def status(self, operation):
        result = {"operation": operation, "dispatched": self.dispatched(operation), "replayAllowed": False}
        for suffix, key in [(".dispatch.json", "dispatch"), (".created.json", "created"), (".result.json", "result")]:
            p = self.path(operation, suffix)
            if p.exists():
                result[key] = self.read(p)
        return result
