"""Opt-in successor-token renewal with durable credential recovery; no deletion or in-place regeneration."""
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

import canvas_auth as auth

UTC = dt.timezone.utc


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def instant(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC)
    except (AttributeError, TypeError, ValueError):
        raise auth.CanvasError("malformed", "Canvas token metadata needs an absolute expiration timestamp") from None


def scopes(record):
    values = record.get("scopes")
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise auth.CanvasError("malformed", "Token scopes could not be established; renewal cannot preserve access")
    return sorted(values)


def private_read(path):
    try:
        if path.is_symlink():
            raise auth.CanvasError("config_insecure", "Renewal refuses symlinked configuration files")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
                raise auth.CanvasError("config_insecure", "Renewal requires regular owner-only configuration files without additional hard links")
            return stream.read()
    except OSError:
        raise auth.CanvasError("config_missing", "A private renewal input could not be read") from None


def atomic(path, value):
    fd, name = tempfile.mkstemp(prefix=".env.canvas-tmp-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise auth.CanvasError("config_insecure", "A renewal output became a symlink")
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def state_path(acct, suffix="pending.json"):
    return auth.config_dir() / f".env.canvas-renew-{acct.alias}.{suffix}"


@contextlib.contextmanager
def locked(acct):
    if os.name != "posix":
        raise auth.CanvasError("renewal_platform_unverified", "Automatic token renewal currently requires a POSIX filesystem lock")
    import fcntl
    path = state_path(acct, "lock")
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise auth.CanvasError("config_insecure", "The renewal lock is not an owner-only regular file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise auth.CanvasError("renewal_busy", "Another process is renewing this account's token") from None
        yield
    finally:
        os.close(fd)


def local_inputs(acct):
    if acct.token_env in os.environ:
        raise auth.CanvasError("config_invalid", "Renewal cannot persist a token overridden by an exported environment variable")
    if sum(a.token_env == acct.token_env for a in auth.load_accounts()) != 1:
        raise auth.CanvasError("config_invalid", "Renewal requires a token variable used by exactly one account")
    env, config = private_read(auth.env_path()), private_read(auth.accounts_path())
    matches = re.findall(rb"(?m)^\s*(?:export\s+)?" + re.escape(acct.token_env.encode()) + rb"\s*=.*$", env)
    if len(matches) != 1:
        raise auth.CanvasError("config_invalid", "Renewal needs exactly one token assignment in the private env file")
    return env, config


def replace_token(env, key, token):
    if not isinstance(token, str) or len(token) < 20 or not token.isascii() or any(c.isspace() or c in "\"'" for c in token) or token.endswith("..."):
        raise auth.CanvasError("malformed", "Canvas did not return a complete replacement credential")
    pattern = rb"(?m)^(\s*(?:export\s+)?" + re.escape(key.encode()) + rb"\s*=).*$"
    return re.sub(pattern, lambda m: m[1] + token.encode(), env)


def updated_config(raw, acct, expires, policy):
    data = json.loads(raw)
    entry = next(e for e in data["accounts"] if e["alias"] == acct.alias)
    entry["token_expires"] = instant(expires).date().isoformat()
    if policy is not None:
        entry["token_renewal"] = policy
    return encoded(data)


def make_plan(client, lifetime=90, before=14, enable=False, now=None):
    now = now or dt.datetime.now(UTC)
    if type(lifetime) is not int or type(before) is not int or not 2 <= lifetime <= 90 or not 1 <= before < lifetime:
        raise auth.CanvasError("config_invalid", "Renewal needs a 2–90 day lifetime and a positive shorter renewal window")
    acct = client.account
    env, config = local_inputs(acct)
    assignment = re.search(rb"(?m)^\s*(?:export\s+)?" + re.escape(acct.token_env.encode()) + rb"\s*=(.*)$", env)[1].strip().decode("utf-8")
    if assignment[:1] in ("'", '"') and assignment[-1:] == assignment[:1]:
        assignment = assignment[1:-1]
    if not assignment.isascii() or not hmac.compare_digest(assignment, client._token):
        raise auth.CanvasError("preview_changed", "The token assignment changed after the client loaded its credential")
    current = auth.current_token_record(client)
    if current.get("workflow_state") != "active" or current.get("can_manually_regenerate") is not True:
        raise auth.CanvasError("denied", "Canvas does not report an active regenerable manual token")
    old_expiry = instant(current.get("expires_at"))
    current_scopes = scopes(current)
    requested = dt.datetime.combine(now.date() + dt.timedelta(days=lifetime), dt.time(), UTC)
    purpose = f"Agent Hands renewal of token {auth.id_string(current.get('id'))} through {requested.date().isoformat()}"
    policy = {"enabled": True, "lifetime_days": lifetime, "before_days": before} if enable else acct.token_renewal
    plan = {"mode": "preview", "account": acct.alias, "origin": acct.base_url, "user_id": acct.user_id,
            "current_token_id": auth.id_string(current.get("id")), "current_expires_at": old_expiry.isoformat(),
            "replacement_purpose": purpose, "requested_expires_at": requested.isoformat(), "scopes_preserved": current_scopes,
            "automatic_renewal": policy, "old_token": "retained until its existing expiry", "password_manager": "not updated",
            "writes_sent": 0}
    fingerprint = {**plan, "env_digest": digest(env), "config_digest": digest(config)}
    plan["preview_hash"] = digest(encoded(fingerprint))
    return plan, env, config


def recover(client, before=14, now=None):
    now = now or dt.datetime.now(UTC)
    acct = client.account
    pending = state_path(acct)
    saved = json.loads(private_read(pending))
    if saved.get("alias") != acct.alias or saved.get("origin") != acct.base_url or saved.get("user_id") != acct.user_id:
        raise auth.CanvasError("identity_mismatch", "The pending renewal belongs to another account")
    if not saved.get("replacement_token"):
        raise auth.CanvasError("renewal_uncertain", "A creation may have landed without a saved response; inspect the recorded purpose in Canvas before further renewal")
    candidate = auth.Client(acct, client.transport, sleep=client.sleep)
    candidate._token = saved["replacement_token"]
    record = auth.current_token_record(candidate)
    expiry = instant(record.get("expires_at"))
    if auth.id_string(record.get("id")) != saved["replacement_id"] or record.get("workflow_state") != "active" or scopes(record) != saved["scopes"] or expiry <= now + dt.timedelta(days=before + 1):
        raise auth.CanvasError("renewal_uncertain", "The replacement credential did not pass identity, scope, state and expiration checks")
    if expiry > instant(saved["requested_expires_at"]) + dt.timedelta(seconds=1):
        raise auth.CanvasError("renewal_uncertain", "Canvas returned a longer expiration than requested")
    env, config = local_inputs(acct)
    if digest(env) not in {saved["env_before"], saved.get("env_after")} or digest(config) not in {saved["config_before"], saved.get("config_after")}:
        raise auth.CanvasError("renewal_uncertain", "Local configuration changed during renewal; the replacement is preserved in the private pending file")
    next_env = replace_token(env, acct.token_env, saved["replacement_token"])
    next_config = updated_config(config, acct, record["expires_at"], saved["policy"])
    saved.update(env_after=digest(next_env), config_after=digest(next_config))
    atomic(pending, encoded(saved))
    atomic(auth.env_path(), next_env)
    atomic(auth.accounts_path(), next_config)
    auth.load_env()
    client.account = auth.account(acct.alias)
    client._token = auth.token_for(client.account)
    result = {"mode": "executed", "account": acct.alias, "previous_token_id": saved["old_id"], "token_id": saved["replacement_id"],
              "expires_at": record["expires_at"], "old_token": "retained until its existing expiry", "writes_sent": 1, "verified": True}
    atomic(state_path(acct, "last.json"), encoded(result))
    pending.unlink()
    return result


def execute(client, expected, lifetime=90, before=14, enable=False, now=None):
    with locked(client.account):
        pending = state_path(client.account)
        if pending.exists() or pending.is_symlink():
            raise auth.CanvasError("renewal_uncertain", "A pending renewal requires inspection or token-renew --recover")
        plan, env, config = make_plan(client, lifetime, before, enable, now)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or not hmac.compare_digest(expected, plan["preview_hash"]):
            raise auth.CanvasError("preview_changed", "Token renewal requires the current reviewed preview hash")
        saved = {"alias": client.account.alias, "origin": client.origin, "user_id": client.account.user_id,
                 "old_id": plan["current_token_id"], "purpose": plan["replacement_purpose"], "requested_expires_at": plan["requested_expires_at"],
                 "scopes": plan["scopes_preserved"], "policy": plan["automatic_renewal"], "env_before": digest(env), "config_before": digest(config)}
        atomic(pending, encoded(saved))
        data = {"token[purpose]": saved["purpose"], "token[expires_at]": saved["requested_expires_at"]}
        if saved["scopes"]:
            data["token[scopes][]"] = saved["scopes"]
        try:
            response = client.request("POST", "/api/v1/users/self/tokens", data=data)
            if 400 <= response.status < 500 and response.status not in {408, 429}:
                pending.unlink()
                raise auth.CanvasError("denied", "Canvas refused creation of a successor token; the current token remains unchanged", status=response.status)
            record = auth.parse_json(response)
            if not isinstance(record, dict) or auth.id_string(record.get("user_id")) != client.account.user_id:
                raise auth.CanvasError("malformed", "Canvas returned an unexpected replacement credential record")
            token = record.get("visible_token") or record.get("token")
            replace_token(env, client.account.token_env, token)
            if hmac.compare_digest(token, client._token):
                raise auth.CanvasError("malformed", "Canvas did not issue a distinct successor token")
            saved.update(replacement_token=token, replacement_id=auth.id_string(record.get("id")))
            atomic(pending, encoded(saved))
            return recover(client, before, now)
        except (auth.CanvasError, OSError, ValueError, KeyError, TypeError):
            if pending.exists():
                raise auth.CanvasError("renewal_uncertain", "Renewal stopped with a private pending record; the current token was not revoked. Inspect before retrying") from None
            raise


def maintain(client, now=None):
    policy = client.account.token_renewal
    if not policy or not policy["enabled"]:
        return None
    if state_path(client.account).exists():
        raise auth.CanvasError("renewal_uncertain", "A previous token renewal needs inspection before automatic use")
    now = now or dt.datetime.now(UTC)
    expiry = client.account.token_expires
    if expiry is None:
        raise auth.CanvasError("config_invalid", "Automatic renewal requires a recorded token expiration")
    if (expiry - now.date()).days > policy["before_days"]:
        return None
    plan, _, _ = make_plan(client, policy["lifetime_days"], policy["before_days"], True, now)
    return execute(client, plan["preview_hash"], policy["lifetime_days"], policy["before_days"], True, now)


def run(args, transport=None):
    try:
        auth.check_runtime()
        auth.check_env_permissions()
        acct = auth.account(args.alias)
        if not args.recover:
            auth.check_expiry(acct, dt.datetime.now(UTC).date())
        client = auth.Client(acct, transport)
        if args.recover:
            if not args.execute:
                raise auth.CanvasError("config_invalid", "Recovery requires --execute and inspects the saved replacement without creating another token")
            with locked(acct):
                result = recover(client, args.before_days)
        elif args.execute:
            result = execute(client, args.expect, args.lifetime_days, args.before_days, args.enable_auto)
        else:
            result, _, _ = make_plan(client, args.lifetime_days, args.before_days, args.enable_auto)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except auth.CanvasError as error:
        auth.fail(error)
        return 3 if error.kind == "renewal_uncertain" else 1
    except (OSError, ValueError, KeyError, TypeError):
        print("ERROR: Renewal could not process private local state; inspect any pending record before retrying.", file=sys.stderr)
        return 3
