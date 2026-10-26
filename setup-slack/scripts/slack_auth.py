#!/usr/bin/env python3
"""Slack account configuration, transport, identity, and shared message helpers."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://slack.com/api"

HINTS = {
    "not_authed": "no token was sent; check the alias's token_env in the selected provider .env",
    "invalid_auth": "the token is invalid; reinstall the app and paste the new User OAuth Token",
    "token_revoked": "the token was revoked; reinstall the app and paste the new User OAuth Token",
    "token_expired": "the token expired; refresh through the app’s configured OAuth flow or reinstall; do not disable token rotation",
    "account_inactive": "the Slack account behind this token is deactivated",
    "missing_scope": "the app lacks a scope; add it under OAuth & Permissions > User Token Scopes and reinstall",
    "channel_not_found": "no such channel, or this user cannot see it",
    "not_in_channel": "this user is not a member of that channel",
    "user_not_found": "no such user in this workspace",
    "ratelimited": "Slack rate-limited the request; wait and retry",
    "list_not_found": "no such List, or this user cannot see it",
    "team_access_not_granted": "the app is not approved for this workspace; ask a workspace admin",
}

class SlackError(Exception):
    pass


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def config_dir():
    selected = os.environ.get("SLACK_ENV_FILE")
    if selected:
        return Path(selected).expanduser().resolve().parent
    source = Path(__file__).resolve().parents[1]
    previous = source.parent / "authorize-slack"
    if (previous / ".env").is_file() or (previous / "slack-accounts.json").is_file():
        return previous
    return source


def load_env():
    """Read literal provider values, never shell code; exported values win."""
    selected = os.environ.get("SLACK_ENV_FILE")
    path = Path(selected).expanduser() if selected else config_dir() / ".env"
    if not path.is_file():
        if selected:
            raise SlackError("Selected SLACK_ENV_FILE does not exist")
        return
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r"SLACK_[A-Z0-9_]+", key) or key in {"SLACK_ENV_FILE", "SLACK_API_BASE"}:
            raise SlackError(f"Invalid Slack configuration key on line {number}")
        if value.startswith(("'", '\"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise SlackError(f"Unclosed configuration quote on line {number}")
            value = value[1:-1]
        os.environ.setdefault(key, value)


def accounts_path():
    path = os.environ.get("SLACK_ACCOUNTS_PATH", "").strip()
    if path:
        return str(Path(path) if Path(path).is_absolute() else config_dir() / path)
    return str(config_dir() / "slack-accounts.json")


def load_accounts():
    path = accounts_path()
    if not os.path.isfile(path):
        raise SlackError(f"Slack account config does not exist: {path}\nNEXT: cp {str(Path(__file__).resolve().parents[1] / 'slack-accounts.example.json')} {path}")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        raise SlackError("Slack account configuration is unreadable or invalid JSON")
    accounts = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(accounts, list):
        raise SlackError("Slack account config must contain an accounts array")
    aliases = set()
    for item in accounts:
        if not isinstance(item, dict) or not isinstance(item.get("alias"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", item["alias"]):
            raise SlackError("Each Slack account needs a simple alias (letters, numbers, underscore, hyphen)")
        if item["alias"] in aliases:
            raise SlackError("Duplicate Slack account alias")
        aliases.add(item["alias"])
    return accounts


def account(alias):
    for item in load_accounts():
        if item.get("alias") == alias:
            for field in ("team_id", "user_id", "token_env"):
                if not item.get(field):
                    raise SlackError(f"Slack alias '{alias}' needs {field}")
            return item
    raise SlackError(f"Unknown Slack account alias: {alias}")


def token_for(acct):
    env = acct["token_env"]
    if not re.fullmatch(r"[A-Za-z0-9_]+", env):
        raise SlackError(f"Invalid token_env for alias '{acct['alias']}'")
    value = os.environ.get(env, "").strip()
    if not value:
        raise SlackError(f"{env} is not set (expected in the selected provider .env or exported environment)")
    return value


def call(acct, method, params=None, json_body=False):
    """One Web API call. Reads are form-encoded; writes with structured arguments send JSON."""
    token = token_for(acct)
    url = f"{API_BASE}/{method}"
    headers = {"Authorization": f"Bearer {token}"}
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if json_body:
        data = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    else:
        data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in params.items()}).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise SlackError(f"{method}: rate limited (retry after {exc.headers.get('Retry-After', '?')}s)")
        raise SlackError(f"{method}: HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError):
        raise SlackError(f"{method}: network request failed; for writes, check the destination before retrying")
    if not body.get("ok"):
        error = body.get("error", "unknown_error")
        detail = f" (needed: {body['needed']})" if body.get("needed") else ""
        hint = HINTS.get(error)
        raise SlackError(f"{method}: {error}{detail}" + (f"\nHINT: {hint}" if hint else ""))
    return body


def paged(acct, method, params, key, limit=None, max_pages=20):
    """Follow response_metadata.next_cursor. Fails loudly rather than returning a silently truncated result."""
    results = []
    cursor = None
    for _ in range(max_pages):
        page = call(acct, method, dict(params, cursor=cursor))
        results.extend(page.get(key) or [])
        if limit and len(results) >= limit:
            return results[:limit]
        cursor = ((page.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            if page.get("has_more"):
                raise SlackError(f"{method}: more results reported without a cursor; refusing a partial result")
            return results
    raise SlackError(f"{method}: more than {max_pages} pages; narrow the request")


def verify_identity(acct):
    who = call(acct, "auth.test")
    if who.get("team_id") != acct["team_id"] or who.get("user_id") != acct["user_id"]:
        raise SlackError(
            f"Token identity mismatch for alias '{acct['alias']}': token is team {who.get('team_id')} user {who.get('user_id')}, "
            f"config expects team {acct['team_id']} user {acct['user_id']}. Refusing to act."
        )
    if who.get("bot_id"):
        raise SlackError(f"Alias '{acct['alias']}' holds a bot token; a User OAuth Token (xoxp-) is required so actions appear as the user")
    return who


def read_text(args):
    if getattr(args, "text", None) is not None and getattr(args, "text_file", None):
        raise SlackError("Use only one of --text or --text-file")
    if getattr(args, "text_file", None):
        with open(args.text_file, "r", encoding="utf-8") as handle:
            text = handle.read()
    else:
        text = args.text or ""
    if not text.strip():
        raise SlackError("Message text must not be empty")
    return text.rstrip("\n")


def parse_message_url(value):
    """https://x.slack.com/archives/C123/p1726700000000100?thread_ts=... -> (channel, thread ts)."""
    parsed = urllib.parse.urlparse(value)
    match = re.search(r"/archives/([A-Z0-9]+)/p(\d{16})", parsed.path)
    if not match:
        raise SlackError(f"Not a Slack message URL: {value}")
    channel, digits = match.groups()
    query = urllib.parse.parse_qs(parsed.query)
    thread_ts = (query.get("thread_ts") or [None])[0]
    return channel, thread_ts or f"{digits[:10]}.{digits[10:]}"


def channel_label(acct, channel_id):
    try:
        info = call(acct, "conversations.info", {"channel": channel_id}).get("channel") or {}
    except SlackError:
        return channel_id
    if info.get("is_im"):
        return f"DM ({channel_id})"
    return f"#{info.get('name', '?')} ({channel_id})"


def user_label(acct, user_id):
    try:
        user = call(acct, "users.info", {"user": user_id}).get("user") or {}
    except SlackError:
        return user_id
    profile = user.get("profile") or {}
    name = profile.get("real_name") or profile.get("display_name") or user.get("name") or "?"
    return f"{name} ({user_id})"


def print_message_plan(action, acct, target, thread_ts, text):
    print(f"Slack {action} plan:")
    print(f"Account: {acct['alias']} (team {acct['team_id']}, acting as user {acct['user_id']})")
    print(f"Target: {target}" + (f", in thread {thread_ts}" if thread_ts else ""))
    print("--- message ---")
    print(text)
    print("--- end ---")


def cmd_accounts(args):
    for item in load_accounts():
        print(f"- {item.get('alias')} | team: {item.get('team_id')} | user: {item.get('user_id')} | token env: {item.get('token_env')}")
    return 0


def cmd_whoami(args):
    acct = account(args.alias)
    who = verify_identity(acct)
    print(f"Account: {acct['alias']}")
    print(f"Workspace: {who.get('team')} ({who.get('team_id')}) {who.get('url', '')}".rstrip())
    print(f"User: {who.get('user')} ({who.get('user_id')})")
    print("Identity matches the configured team and user; token is a user token.")
    return 0


def positive_limit(value):
    value = int(value)
    if not 1 <= value <= 100:
        raise argparse.ArgumentTypeError("must be between 1 and 100")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accounts").set_defaults(func=cmd_accounts)
    for command in ("check", "whoami"):
        p = sub.add_parser(command)
        p.add_argument("alias")
    args = parser.parse_args(argv)
    try:
        load_env()
        if args.command == "check":
            token_for(account(args.alias))
            print("Local configuration is present; no network request made.")
            return 0
        return cmd_whoami(args) if args.command == "whoami" else cmd_accounts(args)
    except (SlackError, OSError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
