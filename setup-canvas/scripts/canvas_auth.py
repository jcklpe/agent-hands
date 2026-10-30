#!/usr/bin/env python3
"""Canvas account configuration, bounded API transport, pagination and identity checks."""
import argparse
import datetime
import http.client
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zoneinfo
from dataclasses import dataclass
from pathlib import Path

SETUP_DIR = Path(__file__).resolve().parents[1]
ACCOUNTS_FILE = "canvas-accounts.json"
API_PREFIX = "/api/v1/"
ACCEPT = "application/json+canvas-string-ids"
USER_AGENT = "agent-hands-canvas/0.1"
TIMEOUT_SECONDS = 60
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PAGES = 200
PER_PAGE = "100"
READ_RETRIES = 3
MAX_RETRY_DELAY_SECONDS = 60
EXPIRY_WARNING_DAYS = 14
RESERVED_KEYS = {"CANVAS_ENV_FILE", "CANVAS_CONFIG_DIR", "CANVAS_BASE_URL", "CANVAS_API_URL"}
ACCOUNT_KEYS = {"alias", "base_url", "user_id", "token_env", "token_expires", "courses"}
INVALID_TOKEN_MARKERS = ("invalid access token", "invalid_token", "expired", "revoked")
NOT_AUTHORIZED_MARKERS = ("not authorized", "unauthorized")

HINTS = {
    "config_missing": "Create it from this setup folder's example; see references/account-access.md.",
    "config_invalid": "Fix the named field or line; values are never echoed.",
    "config_insecure": "Restrict the env file to its owner, for example: chmod 600 setup-canvas/.env",
    "base_url_invalid": "Use the https://host origin from the browser's address bar, with nothing after the host.",
    "token_missing": "Paste the token into the named variable in the ignored .env with your editor; never in chat or a command argument.",
    "token_expired_local": "Create or regenerate a token in your Canvas profile settings, then update the .env value and token_expires.",
    "token_rejected": "Canvas refused the token (expired, revoked or regenerated). Create or regenerate one in your Canvas profile settings and replace the .env value.",
    "identity_mismatch": "Check that the alias and its token belong to the same Canvas user. Nothing was done.",
    "identity_unconfirmed": "Run whoami, confirm the account is yours, and record the printed ID as user_id.",
    "network_error": "Check connectivity and the instance address. A write may still have landed; inspect it before retrying.",
    "throttled": "Wait and try again later.",
    "tz_data_missing": "Install time-zone data for this platform (the tzdata package on Windows).",
    "python_unsupported": "Use Python 3.11 or later, for example through uv run --project setup-canvas.",
}


class CanvasError(Exception):
    """A failure with a stable kind. Messages never contain credentials."""

    def __init__(self, kind, message, status=None, pages_read=None):
        super().__init__(message)
        self.kind = kind
        self.status = status
        self.pages_read = pages_read

    def __str__(self):
        return f"[{self.kind}] {self.args[0]}"


def fail(error):
    print(f"ERROR {error}", file=sys.stderr)
    hint = HINTS.get(error.kind)
    if hint:
        print(f"NEXT: {hint}", file=sys.stderr)
    return 1


# Configuration ----------------------------------------------------------------

_file_settings = {}


def config_dir():
    selected = os.environ.get("CANVAS_ENV_FILE")
    if selected:
        return Path(selected).expanduser().resolve().parent
    directory = os.environ.get("CANVAS_CONFIG_DIR")
    if directory:
        path = Path(directory).expanduser().resolve()
        if not path.is_dir():
            raise CanvasError("config_missing", "The selected CANVAS_CONFIG_DIR is not a directory")
        return path
    return SETUP_DIR


def env_path():
    selected = os.environ.get("CANVAS_ENV_FILE")
    if selected:
        path = Path(selected).expanduser()
        if not path.is_file():
            raise CanvasError("config_missing", "The selected CANVAS_ENV_FILE does not exist")
        return path
    return config_dir() / ".env"


def load_env():
    """Read literal CANVAS_* assignments as data, never as shell code; exported values win."""
    _file_settings.clear()
    path = env_path()
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise CanvasError("config_invalid", "The Canvas env file is unreadable or not UTF-8 text") from None
    for number, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"CANVAS_[A-Z0-9_]+", key):
            raise CanvasError("config_invalid", f"Line {number} of the Canvas env file is not a CANVAS_* assignment")
        if key in RESERVED_KEYS:
            where = f"the instance address belongs in {ACCOUNTS_FILE}" if key.endswith("_URL") else "the file cannot choose its own location"
            raise CanvasError("config_invalid", f"{key} cannot be set in the env file (line {number}); {where}")
        if value[:1] in ("'", '"'):
            if len(value) < 2 or value[-1] != value[0]:
                raise CanvasError("config_invalid", f"Unclosed quote on line {number} of the Canvas env file")
            value = value[1:-1]
        _file_settings[key] = value


def setting(name):
    """An exported variable, else the env file's literal value; empty counts as unset."""
    value = os.environ.get(name)
    if value is None:
        value = _file_settings.get(name)
    value = (value or "").strip()
    return value or None


def normalize_origin(value):
    """Return the instance origin as https://host[:port], or raise base_url_invalid."""
    if not isinstance(value, str) or not value or value != value.strip() or any(c.isspace() for c in value) or "\\" in value:
        raise CanvasError("base_url_invalid", "The instance address must be a single https://host value with no spaces")
    parts = urllib.parse.urlsplit(value)
    if parts.scheme.lower() != "https":
        raise CanvasError("base_url_invalid", "The instance address must use https")
    if "@" in parts.netloc:
        raise CanvasError("base_url_invalid", "The instance address must not contain user information")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise CanvasError("base_url_invalid", "The instance address must be the origin only, with no path, query or fragment")
    host = parts.hostname or ""
    if not host.isascii() or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*", host):
        raise CanvasError("base_url_invalid", "The instance address needs an ASCII host name (use the punycode form for international names)")
    try:
        port = parts.port
    except ValueError:
        port = 0
    if port == 0:
        raise CanvasError("base_url_invalid", "The instance address has an invalid port")
    return f"https://{host}" if port in (None, 443) else f"https://{host}:{port}"


@dataclass(frozen=True)
class Account:
    alias: str
    base_url: str
    user_id: str
    token_env: str
    token_expires: datetime.date | None
    courses: tuple


def accounts_path():
    return config_dir() / ACCOUNTS_FILE


def _parse_account(entry, position):
    if not isinstance(entry, dict):
        raise CanvasError("config_invalid", f"Account {position} must be an object")
    alias = entry.get("alias")
    if not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", alias):
        raise CanvasError("config_invalid", f"Account {position} needs a simple alias (letters, numbers, underscore, hyphen)")
    unknown = sorted(set(entry) - ACCOUNT_KEYS)
    if unknown:
        raise CanvasError("config_invalid", f"Alias '{alias}' has unknown field(s): {', '.join(unknown)}")
    try:
        base_url = normalize_origin(entry.get("base_url"))
    except CanvasError as exc:
        raise CanvasError("base_url_invalid", f"Alias '{alias}': {exc.args[0]}") from None
    user_id = entry.get("user_id", "")
    if isinstance(user_id, int) and not isinstance(user_id, bool):
        user_id = str(user_id)
    if not isinstance(user_id, str) or not re.fullmatch(r"\d*", user_id):
        raise CanvasError("config_invalid", f"Alias '{alias}': user_id must be empty or a Canvas user ID")
    token_env = entry.get("token_env")
    if not isinstance(token_env, str) or not re.fullmatch(r"CANVAS_[A-Z0-9_]+", token_env) or token_env in RESERVED_KEYS:
        raise CanvasError("config_invalid", f"Alias '{alias}': token_env must name a CANVAS_* variable")
    expires = entry.get("token_expires")
    if expires in (None, ""):
        expires = None
    else:
        try:
            if not isinstance(expires, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expires):
                raise ValueError
            expires = datetime.date.fromisoformat(expires)
        except ValueError:
            raise CanvasError("config_invalid", f"Alias '{alias}': token_expires must be a real date written YYYY-MM-DD") from None
    courses = entry.get("courses", [])
    if not isinstance(courses, list):
        raise CanvasError("config_invalid", f"Alias '{alias}': courses must be a list of course IDs")
    selected = []
    for course in courses:
        try:
            course = id_string(course)
        except CanvasError:
            raise CanvasError("config_invalid", f"Alias '{alias}': each course must be a numeric Canvas course ID") from None
        if course in selected:
            raise CanvasError("config_invalid", f"Alias '{alias}': course {course} is listed twice")
        selected.append(course)
    return Account(alias, base_url, user_id, token_env, expires, tuple(selected))


def load_accounts():
    path = accounts_path()
    if not path.is_file():
        raise CanvasError("config_missing", f"Canvas account config does not exist: {path} (copy canvas-accounts.example.json from {SETUP_DIR})")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CanvasError("config_invalid", "Canvas account config is unreadable or not valid JSON") from None
    entries = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise CanvasError("config_invalid", "Canvas account config must contain an accounts array")
    accounts, aliases = [], set()
    for position, entry in enumerate(entries, 1):
        parsed = _parse_account(entry, position)
        if parsed.alias in aliases:
            raise CanvasError("config_invalid", f"Duplicate Canvas account alias: {parsed.alias}")
        aliases.add(parsed.alias)
        accounts.append(parsed)
    return accounts


def account(alias):
    for item in load_accounts():
        if item.alias == alias:
            return item
    raise CanvasError("config_invalid", f"Unknown Canvas account alias: {alias}")


def token_for(acct):
    value = setting(acct.token_env)
    if not value:
        raise CanvasError("token_missing", f"{acct.token_env} is not set (expected in the selected Canvas .env or the environment)")
    return value


def id_string(value):
    """A Canvas ID as an exact string. Integers convert without loss; anything else is refused."""
    if isinstance(value, bool) or value is None:
        raise CanvasError("malformed", "Canvas returned a missing or non-numeric ID")
    if isinstance(value, int) and value >= 0:
        return str(value)
    if isinstance(value, str) and re.fullmatch(r"\d+", value):
        return value
    raise CanvasError("malformed", "Canvas returned an ID that is not a whole number")


# Transport --------------------------------------------------------------------

@dataclass
class Response:
    status: int
    headers: dict
    body: bytes

    def header(self, name):
        return self.headers.get(name.lower())


def _header_map(message):
    names = {name.lower() for name in message.keys()}
    return {name: ", ".join(message.get_all(name) or []) for name in names}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibTransport:
    """Sends exactly one request and never follows a redirect, so the token cannot travel with one."""

    def __init__(self, max_bytes=MAX_JSON_BYTES, timeout=TIMEOUT_SECONDS):
        self.max_bytes = max_bytes
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect())

    def _read(self, stream):
        data = stream.read(self.max_bytes + 1)
        if len(data) > self.max_bytes:
            raise CanvasError("too_large", f"Canvas sent more than {self.max_bytes} bytes for one API response; it was refused")
        return data

    def send(self, method, url, headers, body=None, token=None):
        request = urllib.request.Request(url, data=body, method=method)
        for name, value in headers.items():
            request.add_header(name, value)
        if token is not None:
            # Unredirected headers are never copied onto a follow-up request.
            request.add_unredirected_header("Authorization", f"Bearer {token}")
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                return Response(response.status, _header_map(response.headers), self._read(response))
        except urllib.error.HTTPError as exc:
            try:
                return Response(exc.code, _header_map(exc.headers), self._read(exc))
            finally:
                exc.close()
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            raise CanvasError("network_error", "The request to Canvas failed before a complete response arrived") from None


def parse_link_header(value):
    """Map each relation in a Link header to its URL, treating the URLs as opaque."""
    links = {}
    for match in re.finditer(r"<([^>]*)>((?:\s*;\s*[^;,]+)*)", value or ""):
        url, params = match.group(1).strip(), match.group(2)
        for param in params.split(";"):
            key, _, raw = param.strip().partition("=")
            if key.strip().lower() == "rel":
                for rel in raw.strip().strip('"').split():
                    links.setdefault(rel.lower(), url)
    return links


def canvas_message(response):
    """Canvas's own error text, compacted and bounded. Remote text is data, not instructions."""
    try:
        data = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ""
    found = []

    def collect(item):
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            for key in ("message", "error"):
                if isinstance(item.get(key), str):
                    found.append(item[key])
            if "errors" in item:
                collect(item["errors"])
            for value in item.values():
                if isinstance(value, list):
                    collect(value)
        elif isinstance(item, list):
            for value in item:
                collect(value)

    collect(data)
    text = " ".join(" ".join(dict.fromkeys(found)).split())
    return text[:200]


def is_throttled(response):
    if response.status == 429:
        return True
    return response.status == 403 and b"rate limit exceeded" in response.body.lower()


def retry_delay(response, attempt):
    value = (response.header("retry-after") or "").strip()
    if value.isdigit():
        return min(int(value), MAX_RETRY_DELAY_SECONDS)
    return 2 ** (attempt + 1)


def raise_for_status(response):
    status = response.status
    if 200 <= status < 300:
        return
    message = canvas_message(response)
    detail = f": {message}" if message else ""
    lowered = message.lower()
    if status == 401:
        try:
            unauthorized = json.loads(response.body.decode("utf-8")).get("status") == "unauthorized"
        except (UnicodeDecodeError, ValueError, AttributeError):
            unauthorized = False
        if any(marker in lowered for marker in INVALID_TOKEN_MARKERS):
            raise CanvasError("token_rejected", f"Canvas rejected the token{detail}", status=status)
        if unauthorized or any(marker in lowered for marker in NOT_AUTHORIZED_MARKERS):
            raise CanvasError("denied", f"Canvas refused this for the user{detail}", status=status)
        if response.header("www-authenticate"):
            raise CanvasError("token_rejected", f"Canvas rejected the token{detail}", status=status)
        raise CanvasError("denied", f"Canvas refused this for the user{detail}", status=status)
    if is_throttled(response):
        raise CanvasError("throttled", "Canvas rate-limited the request", status=status)
    if status == 403:
        raise CanvasError("denied", f"Canvas refused this for the user{detail}", status=status)
    if status == 404:
        raise CanvasError("not_found", f"Canvas reports no such resource for this user{detail}", status=status)
    if status >= 500:
        raise CanvasError("server_error", f"Canvas returned a server error ({status})", status=status)
    if 400 <= status < 500:
        raise CanvasError("request_rejected", f"Canvas rejected the request ({status}){detail}", status=status)
    raise CanvasError("http_error", f"Canvas returned an unexpected status ({status})", status=status)


def parse_json(response):
    """Check the status, then decode a JSON body. An empty successful body returns None."""
    raise_for_status(response)
    if response.status == 204 or not response.body.strip():
        return None
    if "json" not in (response.header("content-type") or "").lower():
        raise CanvasError("malformed", "Canvas returned a response that is not JSON", status=response.status)
    try:
        text = response.body.decode("utf-8")
        if text.startswith("while(1);"):
            text = text[len("while(1);"):]
        return json.loads(text)
    except (UnicodeDecodeError, ValueError):
        raise CanvasError("malformed", "Canvas returned invalid JSON", status=response.status) from None


def _encode(pairs):
    if pairs is None:
        return []
    if isinstance(pairs, dict):
        pairs = list(pairs.items())
    encoded = []
    for key, value in pairs:
        for item in value if isinstance(value, (list, tuple)) else [value]:
            if item is not None:
                encoded.append((key, str(item).lower() if isinstance(item, bool) else str(item)))
    return encoded


@dataclass
class Paged:
    items: list
    pages: int


class Client:
    """Canvas API access for one account. Only the account's own origin ever receives its token."""

    def __init__(self, acct, transport=None, sleep=time.sleep):
        self.account = acct
        self.origin = acct.base_url
        self._token = token_for(acct)
        self.transport = transport or UrllibTransport()
        self.sleep = sleep
        self.requests_sent = 0

    def __repr__(self):
        return f"Client(alias={self.account.alias!r}, origin={self.origin!r})"

    def check_api_url(self, url):
        """Refuse anything that is not this instance's API, including dot segments that leave it."""
        parts = urllib.parse.urlsplit(url)
        try:
            same_origin = parts.scheme.lower() == "https" and "@" not in parts.netloc and normalize_origin(f"https://{parts.netloc}") == self.origin
        except CanvasError:
            same_origin = False
        segments = urllib.parse.unquote(parts.path).split("/")
        if not same_origin or not parts.path.startswith(API_PREFIX) or "." in segments or ".." in segments or parts.fragment:
            raise CanvasError("url_refused", "A URL outside this instance's API was not requested")
        return url

    def url_for(self, target, params=None):
        url = self.origin + target if target.startswith("/") else target
        self.check_api_url(url)
        query = urllib.parse.urlencode(_encode(params))
        if query:
            url += ("&" if urllib.parse.urlsplit(url).query else "?") + query
        return url

    def request(self, method, target, params=None, data=None):
        """Send one API request. Reads retry throttling a bounded number of times; writes are never retried or redirected."""
        method = method.upper()
        url = self.url_for(target, params)
        body = urllib.parse.urlencode(_encode(data)).encode("utf-8") if data is not None else None
        headers = {"Accept": ACCEPT, "User-Agent": USER_AGENT}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        redirected, attempt = False, 0
        while True:
            response = self.transport.send(method, url, headers, body, self._token)
            self.requests_sent += 1
            if 300 <= response.status < 400:
                location = response.header("location")
                if method != "GET" or redirected or not location:
                    raise CanvasError("redirect_refused", f"Canvas answered {response.status} with a redirect that was not followed", status=response.status)
                url = self.check_api_url(urllib.parse.urljoin(url, location))
                redirected = True
                continue
            if is_throttled(response):
                if method == "GET" and attempt < READ_RETRIES:
                    self.sleep(retry_delay(response, attempt))
                    attempt += 1
                    continue
                note = "" if method == "GET" else "; the write was not retried"
                raise CanvasError("throttled", f"Canvas rate-limited the request{note}", status=response.status)
            return response

    def get(self, target, params=None):
        return parse_json(self.request("GET", target, params))

    def paginate(self, target, params=None, max_pages=MAX_PAGES):
        """Follow rel="next" links to the end. Any refusal, cycle or cap raises rather than returning a partial list."""
        pairs = _encode(params)
        if not any(key == "per_page" for key, _ in pairs):
            pairs.append(("per_page", PER_PAGE))
        items, seen, pages = [], set(), 0
        url = self.url_for(target, pairs)
        while url:
            if pages >= max_pages:
                raise CanvasError("page_cap", f"The listing has more than {max_pages} pages and was not completed", pages_read=pages)
            seen.add(url)
            try:
                response = self.request("GET", url)
                page = parse_json(response)
            except CanvasError as exc:
                exc.pages_read = pages
                raise
            if not isinstance(page, list):
                raise CanvasError("malformed", "A listing page was not a JSON array", pages_read=pages)
            items.extend(page)
            pages += 1
            following = parse_link_header(response.header("link")).get("next")
            if following:
                following = self.check_api_url(urllib.parse.urljoin(url, following))
                if following in seen:
                    raise CanvasError("pagination_cycle", "The listing's next link repeated an earlier page", pages_read=pages)
            url = following
        return Paged(items, pages)


# Identity ---------------------------------------------------------------------

def whoami(client):
    """The token's Canvas user: ID, display name and time zone only."""
    user = client.get("/api/v1/users/self")
    profile = client.get("/api/v1/users/self/profile")
    if not isinstance(user, dict) or not isinstance(profile, dict):
        raise CanvasError("malformed", "Canvas returned an unexpected user record")
    return {"id": id_string(user.get("id")), "name": str(user.get("name") or ""), "time_zone": profile.get("time_zone") or None}


def verify_identity(client):
    """Refuse to continue unless the token belongs to the account's recorded user."""
    acct = client.account
    if not acct.user_id:
        raise CanvasError("identity_unconfirmed", f"Alias '{acct.alias}' has no recorded user_id")
    user = client.get("/api/v1/users/self")
    actual = id_string(user.get("id")) if isinstance(user, dict) else None
    if actual != acct.user_id:
        raise CanvasError("identity_mismatch", f"The token for alias '{acct.alias}' belongs to Canvas user {actual}, not the recorded user {acct.user_id}. Refusing to act.")
    return user


# Local checks -----------------------------------------------------------------

def check_runtime():
    if sys.version_info < (3, 11):
        raise CanvasError("python_unsupported", "Python 3.11 or later is required")
    try:
        zoneinfo.ZoneInfo("America/New_York")
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
        raise CanvasError("tz_data_missing", "The time-zone database is unavailable") from None


def check_env_permissions():
    path = env_path()
    if os.name == "nt" or not path.is_file():
        return
    if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise CanvasError("config_insecure", "The Canvas env file is readable or writable by other users")


def check_expiry(acct, today):
    if acct.token_expires is None:
        return None
    if acct.token_expires < today:
        raise CanvasError("token_expired_local", f"The token for alias '{acct.alias}' expired on {acct.token_expires.isoformat()}")
    remaining = (acct.token_expires - today).days
    if remaining <= EXPIRY_WARNING_DAYS:
        return f"The token for alias '{acct.alias}' expires on {acct.token_expires.isoformat()} ({remaining} day(s) left)."
    return None


# Commands ---------------------------------------------------------------------

def cmd_accounts():
    for item in load_accounts():
        user = item.user_id or "(not yet confirmed)"
        expires = item.token_expires.isoformat() if item.token_expires else "(not recorded)"
        print(f"- {item.alias} | {item.base_url} | user: {user} | token env: {item.token_env} | token expires: {expires} | courses: {len(item.courses)}")
    return 0


def cmd_check(alias, today):
    check_runtime()
    acct = account(alias)
    check_env_permissions()
    token_for(acct)
    warning = check_expiry(acct, today)
    user = acct.user_id or "not yet recorded; run whoami"
    print(f"Local configuration for '{acct.alias}' is present: {acct.base_url}, {len(acct.courses)} selected course(s), user ID {user}.")
    if warning:
        print(f"WARNING: {warning}")
    print("No network request was made; remote access is not verified.")
    return 0


def cmd_whoami(alias, transport, today):
    acct = account(alias)
    token_for(acct)
    check_expiry(acct, today)
    who = whoami(Client(acct, transport))
    print(f"Account: {acct.alias} ({acct.base_url})")
    print(f"Canvas user: {who['name']} (ID {who['id']})")
    print(f"Time zone: {who['time_zone'] or 'not set'}")
    if not acct.user_id:
        print(f"No user_id is recorded for this alias. If this is your account, record \"user_id\": \"{who['id']}\" in {ACCOUNTS_FILE}.")
    elif acct.user_id == who["id"]:
        print("Identity matches the recorded user_id.")
    else:
        raise CanvasError("identity_mismatch", f"The token belongs to Canvas user {who['id']}, not the recorded user {acct.user_id}.")
    return 0


def main(argv=None, transport=None, today=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accounts", help="list configured aliases without token values or network access")
    for name, text in (("check", "check local configuration without network access"), ("whoami", "read the token's Canvas user (one authorized read)")):
        command = sub.add_parser(name, help=text)
        command.add_argument("alias")
    args = parser.parse_args(argv)
    today = today or datetime.date.today()
    try:
        load_env()
        if args.command == "accounts":
            return cmd_accounts()
        if args.command == "check":
            return cmd_check(args.alias, today)
        return cmd_whoami(args.alias, transport, today)
    except CanvasError as exc:
        return fail(exc)


if __name__ == "__main__":
    raise SystemExit(main())
