"""Bounded GitHub transport, previews and project-owned recovery for domain skills."""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Callable
from urllib.parse import quote, urlencode, urlsplit
import uuid


class Refusal(Exception):
    def __init__(self, message, outcome="blocked"):
        super().__init__(message)
        self.outcome = outcome


class TransportError(Exception):
    def __init__(self, message, status=None, sent=False):
        super().__init__(message)
        self.status, self.sent = status, sent


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def positive(value):
    if not str(value).isdigit() or int(value) < 1:
        raise Refusal("A positive numeric resource ID is required")
    return int(value)


def oid(value):
    if not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", value or ""):
        raise Refusal("Supply the full expected commit SHA")
    return value.lower()


def body(args, required=False):
    if args.body is not None and args.body_file is not None:
        raise Refusal("Select --body or --body-file, not both")
    if args.body_file:
        with Path(args.body_file).open(encoding="utf-8", newline="") as source:
            value = source.read()
    else:
        value = args.body
    if required and (value is None or not value.strip()):
        raise Refusal("A nonempty --body or UTF-8 --body-file is required")
    return value


def project(value, fields):
    def get(obj, path):
        if not path:
            return obj
        key, *rest = path
        if key.endswith("[]"):
            items = obj.get(key[:-2])
            if not isinstance(items, list):
                raise Refusal("Malformed collection in verification response", "failed")
            return sorted((get(item, rest) for item in items), key=canonical)
        if not isinstance(obj, dict) or key not in obj:
            raise Refusal("Missing field in verification response: " + key, "failed")
        value = obj[key]
        return get("" if key == "body" and value is None else value, rest)
    return {field: get(value, field.split(".")) for field in fields}


class Client:
    """All request paths are selected by the owning domain, never forwarded from CLI input."""
    def __init__(self, host, page_limit=20, item_limit=2000):
        self.host, self.page_limit, self.item_limit = host, page_limit, item_limit
        self.writes_sent = 0

    def request(self, method, path, payload=None):
        if path.startswith(("/", "http:" , "https:")) or ".." in path.split("/"):
            raise Refusal("Invalid internal request path")
        env = dict(os.environ, GH_PROMPT_DISABLED="1", GH_PAGER="cat", PAGER="cat")
        env.pop("GH_DEBUG", None)
        cmd = ["gh", "api", "--hostname", self.host, "--method", method, "--include", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2026-03-10", path]
        if payload is not None:
            cmd += ["--input", "-"]
        sent = method != "GET" and not (path == "graphql" and not str((payload or {}).get("query", "")).lstrip().startswith("mutation"))
        try:
            if sent:
                self.writes_sent += 1
            result = subprocess.run(cmd, input=canonical(payload) if payload is not None else None, text=True, capture_output=True, env=env, timeout=60)
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise TransportError("GitHub transport did not return a response", sent=sent) from exc
        raw = result.stdout.replace("\r\n", "\n")
        match = re.match(r"HTTP/\S+ (\d{3})[^\n]*\n(.*?)\n\n(.*)", raw, re.S)
        if not match:
            raise TransportError("Missing GitHub response envelope", sent=sent)
        status = int(match[1])
        try:
            data = json.loads(match[3]) if match[3].strip() else None
        except json.JSONDecodeError as exc:
            raise TransportError("Malformed GitHub JSON response", status=status, sent=sent) from exc
        if result.returncode or status >= 400:
            raise TransportError("GitHub request refused or failed (HTTP %s)" % status, status, sent)
        if isinstance(data, dict) and data.get("errors") not in (None, []):
            raise TransportError("GitHub GraphQL returned errors; partial data is not success", status=status, sent=sent)
        return data

    def get(self, path):
        return self.request("GET", path)

    def graphql(self, query, **variables):
        data = self.request("POST", "graphql", {"query": query, "variables": variables})
        if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
            raise TransportError("Malformed GraphQL data envelope")
        return data["data"]

    def collection(self, path, key=None):
        items, complete = [], False
        for page in range(1, self.page_limit + 1):
            sep = "&" if "?" in path else "?"
            data = self.get(path + sep + urlencode({"per_page": 100, "page": page}))
            batch = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch):
                raise TransportError("Malformed collection response")
            remaining = self.item_limit - len(items)
            items.extend(batch[:remaining])
            if len(batch) < 100 and len(batch) <= remaining:
                complete = True
                break
            if len(items) >= self.item_limit:
                break
        return items, {"complete": complete, "observed": len(items), "page_limit": self.page_limit, "item_limit": self.item_limit}


def target(repo_arg, host=None):
    selected_host = host or os.environ.get("GH_HOST", "github.com")
    if "/" not in repo_arg:
        config = Path(os.environ.get("GITHUB_CONFIG_DIR", str(Path(__file__).parents[1])))
        aliases = Path(os.environ.get("GITHUB_REPOS_PATH", "github-repos.json"))
        data = json.loads((aliases if aliases.is_absolute() else config / aliases).read_text())
        matches = [item for item in data.get("repos", []) if item.get("alias") == repo_arg]
        if len(matches) != 1:
            raise Refusal("Repository alias is missing or ambiguous")
        repo_arg = matches[0]["owner"] + "/" + matches[0]["repo"]
    parts = repo_arg.split("/")
    if len(parts) == 3:
        if host and host.lower() != parts[0].lower():
            raise Refusal("Repository host conflicts with --host")
        selected_host, parts = parts[0], parts[1:]
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", selected_host):
        raise Refusal("Invalid GitHub host")
    if len(parts) != 2 or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[0]) or not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[1]) or parts[1] in (".", ".."):
        raise Refusal("Expected [HOST/]OWNER/REPO")
    return selected_host.lower(), "/".join(parts)


@dataclasses.dataclass
class Step:
    name: str
    method: str
    path: str
    payload: dict | None
    recovery: dict
    verify: Callable[[dict], dict]
    result_ids: Callable[[dict], dict] | None = None


class Context:
    def __init__(self, args):
        self.args = args
        self.host, self.repo = target(args.repo, args.host)
        self.client = Client(self.host, args.page_limit, args.item_limit)
        self.prefix = "repos/" + self.repo
        self.actor = self.identity()
        self.expected_actor = args.actor or os.environ.get("GITHUB_EXPECTED_ACTOR")
        if self.expected_actor and self.actor["login"].lower() != self.expected_actor.lower():
            raise Refusal("Effective GitHub identity does not match the expected actor")
        self.repository = self.client.get(self.prefix)
        if not isinstance(self.repository, dict) or str(self.repository.get("full_name", "")).lower() != self.repo.lower() or not isinstance(self.repository.get("id"), int):
            raise Refusal("Repository identity does not match the requested target")
        self.repo = self.repository["full_name"]
        self.prefix = "repos/" + self.repo

    def identity(self):
        user = self.client.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("id"), int) or not user.get("login"):
            raise Refusal("Cannot establish the effective authenticated actor")
        return {"id": user["id"], "login": user["login"]}

    def item(self, number, kind="issues"):
        item = self.client.get(f"{self.prefix}/{kind}/{positive(number)}")
        if not isinstance(item, dict) or item.get("number") != int(number) or not item.get("id"):
            raise Refusal("Resource identity does not match the requested item")
        if kind == "issues" and item.get("pull_request"):
            raise Refusal("Selected item is a pull request, not an issue")
        expected = f"https://{self.host}/{self.repo}/"
        if not str(item.get("html_url", "")).lower().startswith(expected.lower()):
            raise Refusal("Resource repository/host mismatch")
        return item

    def plan(self, baseline, steps, effects=None):
        plan = {"schema_version": 1, "command": self.args.command, "host": self.host, "repository": {"id": self.repository["id"], "name": self.repo}, "actor": self.actor, "baseline": baseline, "changes": [{"step": s.name, "method": s.method, "path": s.path, "body": s.payload} for s in steps], "effects": effects or [], "atomic": False}
        plan["fingerprint"] = digest(plan)
        return plan

    def proof(self, path, expected):
        actual = self.client.get(path)
        self.validate_readback(path, actual)
        if project(actual, expected) != expected:
            raise Refusal("Independent readback did not match the intended result", "uncertain")
        return {"kind": "rest", "path": path, "fields": list(expected), "digest": digest(expected), "id": actual.get("id"), "url": actual.get("html_url")}

    def validate_readback(self, path, actual):
        if not isinstance(actual, dict):
            raise Refusal("Independent readback is not a resource object", "uncertain")
        item = re.fullmatch(re.escape(self.prefix) + r"/(issues|pulls)/(\d+)", path)
        child = re.fullmatch(re.escape(self.prefix) + r"/(?:issues/comments|pulls/comments|pulls/\d+/reviews)/(\d+)", path)
        if item or child:
            if type(actual.get("id")) is not int or actual["id"] < 1:
                raise Refusal("Independent readback lacks a stable resource ID", "uncertain")
            if item and actual.get("number") != int(item[2]) or child and actual["id"] != int(child[1]):
                raise Refusal("Independent readback resource identity differs", "uncertain")
            if not str(actual.get("html_url", "")).lower().startswith(f"https://{self.host}/{self.repo}/".lower()):
                raise Refusal("Independent readback repository/host differs", "uncertain")


def rest_recovery(path, expected, collection=False, before_ids=None, read_path=None):
    return {"kind": "collection" if collection else "rest", "path": path, "fields": list(expected), "digest": digest(expected), "before_ids": before_ids or [], "read_path": read_path}


def git(cwd, *args, required=True):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(cwd), *args], text=True, capture_output=True)
    if result.returncode and required:
        raise Refusal("Cannot resolve the selected Git checkout/state location")
    return result.stdout.strip() if not result.returncode else None


def remote_identity(value):
    if re.match(r"^[^/@]+@[^:]+:", value):
        host, path = value.split("@", 1)[1].split(":", 1)
    else:
        parsed = urlsplit(value)
        if parsed.scheme not in ("https", "ssh", "http", "git") or not parsed.hostname:
            return None
        host, path = parsed.hostname, parsed.path.lstrip("/")
    return host.lower(), path.removesuffix(".git").strip("/").lower()


def state_location(ctx):
    args = ctx.args
    root = Path(args.project or os.getcwd()).absolute()
    top = git(root, "rev-parse", "--show-toplevel", required=False)
    if top and (args.project or not args.state_dir):
        remotes = git(root, "config", "--get-regexp", r"^remote\..*\.url$", required=False) or ""
        identities = [remote_identity(line.split(None, 1)[1]) for line in remotes.splitlines() if len(line.split(None, 1)) == 2]
        if (ctx.host, ctx.repo.lower()) not in identities:
            raise Refusal("Selected checkout has no remote matching the operated repository; select --project or an explicit --state-dir outside this checkout")
    if args.state_dir:
        location = Path(args.state_dir).absolute()
    elif top:
        common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        current = Path(git(root, "rev-parse", "--path-format=absolute", "--git-dir"))
        if current == common:
            primary = Path(top)
        else:
            configured = git(root, "--git-dir", str(common), "config", "--get", "core.worktree", required=False)
            if configured:
                primary = (common / configured).resolve() if not Path(configured).is_absolute() else Path(configured)
            else:
                worktrees = git(root, "worktree", "list", "--porcelain")
                first = next((line.removeprefix("worktree ") for line in worktrees.splitlines() if line.startswith("worktree ")), None)
                if not first:
                    raise Refusal("Cannot resolve the primary worktree; supply --state-dir")
                primary = Path(first)
        if git(primary, "rev-parse", "--show-toplevel", required=False) != str(primary):
            raise Refusal("Cannot resolve a shared primary worktree; supply --state-dir")
        legacy = primary / ".agent-hands" / "github"
        if legacy.exists() or legacy.is_symlink():
            raise Refusal("Previous default journal exists at .agent-hands/github; select it with --state-dir or coordinate migration of the complete journal before using the new default")
        location = primary / ".github" / "project-collaboration"
    else:
        raise Refusal("No local checkout: supply an explicit private --state-dir")
    for candidate in (location, *location.parents):
        if candidate.is_symlink():
            raise Refusal("Recovery directory must not traverse a symlink")
    parent = location
    while not parent.exists():
        parent = parent.parent
    containing = git(parent, "rev-parse", "--show-toplevel", required=False)
    if containing:
        relative = str(location.relative_to(Path(containing))) + "/"
        if git(containing, "check-ignore", "--no-index", relative, required=False) is None:
            raise Refusal("Project recovery directory must be explicitly gitignored before writes")
        if git(containing, "ls-files", "--", relative):
            raise Refusal("Recovery directory contains tracked files")
    return location / (ctx.host + "_" + ctx.repo.replace("/", "_"))


class Journal:
    def __init__(self, ctx):
        self.directory = state_location(ctx)
        self.ctx = ctx

    @contextlib.contextmanager
    def locked(self):
        try:
            import fcntl
        except ImportError as exc:
            raise Refusal("This runtime needs POSIX file locking; use supported Bash/Python on macOS, Linux or WSL", "unsupported") from exc
        missing = []
        p = self.directory
        while not p.exists():
            missing.append(p)
            p = p.parent
        for p in reversed(missing):
            p.mkdir(mode=0o700, exist_ok=True)
        for p in (self.directory, self.directory.parent):
            if p.is_symlink() or stat.S_IMODE(p.stat().st_mode) & 0o077 or p.stat().st_uid != os.getuid():
                raise Refusal("Recovery directories must be owned by the current user with mode 0700")
        fd = os.open(self.directory / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(fd)
            raise Refusal("Another operation holds the project GitHub journal lock") from exc
        try:
            yield self
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def path(self, operation):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{7,79}", operation or ""):
            raise Refusal("Operation ID must be 8–80 simple letters, digits, underscores or hyphens")
        return self.directory / (operation + ".json")

    def read(self, operation):
        path = self.path(operation)
        if path.is_symlink():
            raise Refusal("Refusing a symlinked recovery record")
        if not path.exists():
            return None
        if stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise Refusal("Recovery record must have mode 0600")
        data = json.loads(path.read_text())
        if data.get("host") != self.ctx.host or data.get("repo_id") != self.ctx.repository["id"] or data.get("actor") != self.ctx.actor:
            raise Refusal("Recovery record actor/host/repository mismatch")
        return data

    def unresolved(self, intent):
        for path in self.directory.glob("*.json"):
            if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise Refusal("Unsafe recovery record in project journal")
            record = json.loads(path.read_text())
            if record.get("intent") == intent and record.get("outcome") in ("started", "uncertain"):
                return record["operation_id"]
        return None

    def write(self, record):
        path = self.path(record["operation_id"])
        if path.is_symlink():
            raise Refusal("Refusing a symlinked recovery record")
        fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(canonical(record) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(self.directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def execute(ctx, plan, steps, rebuild=None):
    args = ctx.args
    operation = args.operation_id or uuid.uuid4().hex
    result = {"schema_version": 1, "outcome": "preview", "operation_id": operation, "plan": plan, "writes_sent": 0}
    if not args.execute:
        return result
    if not ctx.expected_actor:
        raise Refusal("Execution requires --actor or configured GITHUB_EXPECTED_ACTOR")
    if not args.operation_id or args.expect != plan["fingerprint"]:
        raise Refusal("Execution requires the preview's --operation-id and matching --expect fingerprint")
    journal = Journal(ctx)
    with journal.locked():
        previous = journal.read(operation)
        if previous:
            raise Refusal("Operation ID already exists; inspect with recover instead of resending", "uncertain" if previous.get("outcome") != "success" else "blocked")
        intent = digest({"actor": ctx.actor, "changes": plan["changes"]})
        unresolved = journal.unresolved(intent)
        if unresolved:
            raise Refusal("Matching intent has an unresolved operation; recover " + unresolved + " before another attempt", "uncertain")
        if ctx.identity() != ctx.actor:
            raise Refusal("Effective actor changed before execution")
        repository = ctx.client.get(ctx.prefix)
        if repository.get("id") != ctx.repository["id"]:
            raise Refusal("Repository identity changed before execution")
        ctx.repository = repository
        if rebuild:
            fresh_plan, fresh_steps = rebuild(ctx)
            if fresh_plan["fingerprint"] != plan["fingerprint"]:
                raise Refusal("Relevant target state changed after preview; prepare a fresh plan")
            plan, steps = fresh_plan, fresh_steps
        if not steps:
            result.update(outcome="success", applied=False, already_satisfied=True, steps=[], writes_sent=0)
            return result
        record = {"schema_version": 1, "operation_id": operation, "host": ctx.host, "repo": ctx.repo, "repo_id": ctx.repository["id"], "actor": ctx.actor, "fingerprint": plan["fingerprint"], "intent": intent, "command": args.command, "started_at": now(), "outcome": "started", "steps": [], "total_steps": len(steps)}
        journal.write(record)
        for step in steps:
            def created_path(path):
                return path.replace("{created}", str(getattr(ctx, "created_number", "UNRESOLVED")))
            spec = {key: created_path(value) if key in ("path", "read_path") and isinstance(value, str) else value for key, value in step.recovery.items()}
            path = created_path(step.path)
            if "UNRESOLVED" in path:
                raise Refusal("Missing verified parent for a compound step", "uncertain")
            entry = {"name": step.name, "status": "uncertain", "recovery": spec, "sent_at": now()}
            record["steps"].append(entry)
            try:
                journal.write(record)
            except OSError:
                entry["status"] = "not_sent"
                result.update(outcome="failed", message="Could not durably record the next request; that step was not sent", steps=record["steps"], partial=any(s["status"] == "verified" for s in record["steps"]), remaining_steps=len(steps) - len(record["steps"]) + 1, writes_sent=ctx.client.writes_sent)
                return result
            writes_before = ctx.client.writes_sent
            try:
                if ctx.identity() != ctx.actor:
                    entry["status"] = "not_sent"
                    record["outcome"] = "failed" if len(record["steps"]) == 1 else "uncertain"
                    journal.write(record)
                    raise Refusal("Effective actor changed immediately before transmission", "blocked" if len(record["steps"]) == 1 else "uncertain")
                response = ctx.client.request(step.method, path, step.payload)
                if isinstance(response, dict):
                    entry["returned"] = {k: response[k] for k in ("id", "number", "node_id", "sha", "html_url", "uuid", "status") if k in response}
                    if step.result_ids:
                        identifiers = step.result_ids(response)
                        if not isinstance(identifiers, dict) or not set(identifiers) <= {"id", "number", "node_id"} or any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in identifiers.values()):
                            raise Refusal("Invalid mutation result identifiers", "uncertain")
                        entry["returned"].update(identifiers)
                    if isinstance(response.get("details"), dict) and response["details"].get("uuid"):
                        entry["returned"]["uuid"] = response["details"]["uuid"]
                    journal.write(record)
                proof = step.verify(response)
                entry.update(status="verified", proof=proof)
                journal.write(record)
            except (TransportError, Refusal, OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
                not_sent = entry["status"] == "not_sent" or ctx.client.writes_sent == writes_before
                known_refused = isinstance(exc, TransportError) and exc.sent and exc.status is not None and 400 <= exc.status < 500
                entry["status"] = "not_sent" if not_sent else "refused" if known_refused else "uncertain"
                record["outcome"] = "failed" if known_refused or not_sent else "uncertain"
                try:
                    journal.write(record)
                except OSError:
                    record["outcome"] = "uncertain"
                message = str(exc) if isinstance(exc, (TransportError, Refusal)) else "Local verification/recovery failed after transmission; inspect the durable intent record"
                result.update(outcome="blocked" if not_sent and ctx.client.writes_sent == 0 else record["outcome"], message=message, steps=record["steps"], partial=any(s["status"] == "verified" for s in record["steps"]), remaining_steps=len(steps) - len(record["steps"]), writes_sent=ctx.client.writes_sent)
                return result
        record["outcome"] = "success"
        try:
            journal.write(record)
        except OSError:
            result.update(outcome="uncertain", message="Readback succeeded but final recovery recording failed", steps=record["steps"], writes_sent=ctx.client.writes_sent)
            return result
        result.update(outcome="success", applied=bool(steps), already_satisfied=not steps, steps=record["steps"], writes_sent=ctx.client.writes_sent)
        return result


def recover(ctx, read_special=None):
    if not ctx.args.operation_id:
        raise Refusal("recover requires --operation-id")
    if ctx.args.execute:
        raise Refusal("recover is a read/reconciliation operation, not mutation execution")
    journal = Journal(ctx)
    with journal.locked():
        record = journal.read(ctx.args.operation_id)
        if not record:
            raise Refusal("No recovery record exists for this operation")
        for entry in record["steps"]:
            if entry["status"] in ("refused", "not_sent"):
                continue
            spec = entry.get("proof") or entry["recovery"]
            if spec["kind"] == "merge" and (entry.get("returned") or {}).get("status") == "pending" and (entry.get("returned") or {}).get("uuid"):
                spec = {**spec, "acknowledged": True}
            if spec["kind"] not in ("rest", "collection"):
                proof = read_special(spec) if read_special else None
            else:
                path = spec["path"]
                if not re.fullmatch(re.escape(ctx.prefix) + r"/(?:issues|pulls)(?:/[0-9]+)?(?:/(?:comments|reviews|requested_reviewers)(?:/[0-9]+)?)?(?:\?[^\s]*)?", path):
                    raise Refusal("Recovery record contains an unsupported resource path")
                proof = None
                if spec["kind"] == "collection":
                    if getattr(ctx.args, "result_id", None):
                        selected = positive(ctx.args.result_id)
                        read_path = spec["read_path"].format(id=selected, number=selected)
                        actual = ctx.client.get(read_path)
                        ctx.validate_readback(read_path, actual)
                        if actual.get("id") in spec["before_ids"] or digest(project(actual, spec["fields"])) != spec["digest"]:
                            raise Refusal("Selected recovery result does not match the recorded new action", "uncertain")
                        proof = {"kind": "rest", "path": read_path, "fields": spec["fields"], "digest": spec["digest"], "id": actual["id"], "url": actual.get("html_url")}
                        if spec.get("pr_head"):
                            if ctx.item(positive(spec["pr"]), "pulls")["head"]["sha"] != spec["pr_head"]:
                                entry["status"] = "uncertain"
                                continue
                            proof.update(pr_head=spec["pr_head"], pr=spec["pr"])
                        entry.update(status="verified", proof=proof)
                        continue
                    candidates, coverage = ctx.client.collection(path)
                    if not coverage["complete"]:
                        raise Refusal("Recovery candidate coverage is incomplete", "uncertain")
                    matches = [item for item in candidates if item.get("id") not in spec["before_ids"] and digest(project(item, spec["fields"])) == spec["digest"]]
                    if len(matches) == 1:
                        item = matches[0]
                        read_path = spec["read_path"].format(id=positive(item["id"]), number=positive(item.get("number", item["id"])))
                        actual = ctx.client.get(read_path)
                        ctx.validate_readback(read_path, actual)
                        if digest(project(actual, spec["fields"])) == spec["digest"]:
                            proof = {"kind": "rest", "path": read_path, "fields": spec["fields"], "digest": spec["digest"], "id": actual["id"], "url": actual.get("html_url")}
                else:
                    actual = ctx.client.get(path)
                    ctx.validate_readback(path, actual)
                    if digest(project(actual, spec["fields"])) == spec["digest"]:
                        proof = spec
            if proof:
                if spec.get("pr_head"):
                    current_pr = ctx.item(positive(spec["pr"]), "pulls")
                    if current_pr["head"]["sha"] != spec["pr_head"]:
                        entry["status"] = "uncertain"
                        continue
                    proof.update(pr_head=spec["pr_head"], pr=spec["pr"])
                entry.update(status="verified", proof=proof)
            else:
                entry["status"] = "uncertain"
        all_verified = len(record["steps"]) == record["total_steps"] and all(step["status"] == "verified" for step in record["steps"])
        record["outcome"] = "success" if all_verified else "failed" if all(s["status"] in ("verified", "refused", "not_sent") for s in record["steps"]) else "uncertain"
        record["reconciled_at"] = now()
        journal.write(record)
        return {"schema_version": 1, "outcome": record["outcome"], "operation_id": record["operation_id"], "steps": record["steps"], "partial": not all_verified and any(s["status"] == "verified" for s in record["steps"]), "remaining_steps": record["total_steps"] - len(record["steps"]), "writes_sent": 0, "message": "Fresh readback reconciled recorded intent; no mutation was retried" if all_verified else "Unresolved or unsent steps remain; no mutation was retried"}


def add_common(parser):
    parser.add_argument("--repo", required=True, help="[HOST/]OWNER/REPO or configured alias")
    parser.add_argument("--host")
    parser.add_argument("--actor", help="Expected effective GitHub login; required for execution")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--page-limit", type=int, default=20)
    parser.add_argument("--item-limit", type=int, default=2000)
    parser.add_argument("--project", help="Local operated checkout; defaults to cwd")
    parser.add_argument("--state-dir", help="Override the project's .github/project-collaboration recovery directory")
    parser.add_argument("--operation-id")
    parser.add_argument("--expect", help="Exact preview fingerprint")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--dry-run", action="store_true")


def add_body(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--body")
    group.add_argument("--body-file")


def emit(result, as_json):
    if as_json:
        print(canonical(result))
    else:
        print(result.get("outcome", "result").upper())
        print(json.dumps(result, indent=2, ensure_ascii=False))


def run(parser, handler):
    args = parser.parse_args()
    try:
        if not 1 <= args.page_limit <= 1000 or not 1 <= args.item_limit <= 100000:
            raise Refusal("Select page limit 1–1000 and item limit 1–100000")
        result = handler(args)
    except Refusal as exc:
        result = {"schema_version": 1, "outcome": exc.outcome, "message": str(exc)}
    except TransportError as exc:
        result = {"schema_version": 1, "outcome": "uncertain" if exc.sent else "failed", "message": str(exc)}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        result = {"schema_version": 1, "outcome": "failed", "message": "Invalid input, response or inaccessible local resource: " + type(exc).__name__}
    emit(result, args.json)
    return 3 if result.get("partial") else {"success": 0, "preview": 0, "blocked": 2, "unsupported": 4, "uncertain": 3, "failed": 1}.get(result["outcome"], 1)
