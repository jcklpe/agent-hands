#!/usr/bin/env python3
"""Exact issue reads and individually previewed collaboration operations."""
import argparse
from pathlib import Path
import re
import sys
from urllib.parse import quote

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-github" / "scripts"))
from collaboration import Context, Refusal, Step, add_body, add_common, body, execute, positive, project, recover, rest_recovery, run


def metadata(ctx, args, current=None):
    changes, baseline = {}, {}
    for name, singular in (("labels", "label"), ("assignees", "assignee")):
        add = getattr(args, "add_" + singular, [])
        remove = getattr(args, "remove_" + singular, [])
        if args.command == "create-issue":
            add = getattr(args, singular, [])
        if singular == "assignee" and getattr(args, "assign_me", False):
            add = [*add, ctx.actor["login"]]
        if not add and not remove:
            continue
        if set(add) & set(remove):
            raise Refusal("Cannot add and remove the same metadata value")
        key = "name" if name == "labels" else "login"
        values = {item[key] for item in (current or {}).get(name, [])}
        if current is not None:
            baseline[name + "[]." + key] = sorted(values)
        for value in add:
            if name == "labels":
                found = ctx.client.get(ctx.prefix + "/labels/" + quote(value, safe=""))
                resolved = found.get("name")
            else:
                if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                    raise Refusal("Invalid assignee login")
                found = ctx.client.get("users/" + value)
                resolved = found.get("login")
            if not resolved:
                raise Refusal("Cannot resolve metadata value")
            values.add(resolved)
        values = {value for value in values if value.lower() not in {r.lower() for r in remove}}
        changes[name] = sorted(values)
    return changes, baseline


def prepare(ctx):
    args, steps = ctx.args, []
    if args.command == "create-issue":
        if not args.title.strip():
            raise Refusal("A nonempty title is required")
        payload = {"title": args.title, "body": body(args) or ""}
        extra, _ = metadata(ctx, args)
        payload.update(extra)
        existing, coverage = ctx.client.collection(ctx.prefix + "/issues?state=all&creator=" + quote(ctx.actor["login"], safe="") + "&sort=created&direction=desc")
        if not coverage["complete"]:
            raise Refusal("Issue-create reconciliation baseline is incomplete; raise the explicit read limits")
        duplicate = [item["number"] for item in existing if not item.get("pull_request") and item.get("title") == payload["title"] and (item.get("body") or "") == payload["body"]]
        if duplicate and not args.allow_duplicate:
            raise Refusal("An identical issue already exists; inspect it or select --allow-duplicate for an intentional new issue")
        expected = {"title": payload["title"], "body": payload["body"], "user.id": ctx.actor["id"]}
        expected.update({key + "[]." + ("name" if key == "labels" else "login"): value for key, value in extra.items()})
        spec = rest_recovery(ctx.prefix + "/issues?state=all&creator=" + quote(ctx.actor["login"], safe=""), expected, True, [item["id"] for item in existing], ctx.prefix + "/issues/{number}")
        def verify(response):
            return ctx.proof(ctx.prefix + "/issues/" + str(positive(response["number"])), expected)
        steps.append(Step("create issue", "POST", ctx.prefix + "/issues", payload, spec, verify))
        baseline = {"known_issue_ids": sorted(item["id"] for item in existing), "intentional_duplicate": duplicate}
    else:
        issue = ctx.item(args.issue)
        path = ctx.prefix + "/issues/" + str(args.issue)
        baseline = {"id": issue["id"]}
        if args.command == "comment-issue":
            text = body(args, required=True)
            comments, coverage = ctx.client.collection(path + "/comments")
            if not coverage["complete"]:
                raise Refusal("Comment reconciliation baseline is incomplete; raise the read limits")
            expected = {"body": text, "user.id": ctx.actor["id"], "issue_url": issue["url"]}
            spec = rest_recovery(path + "/comments", expected, True, [c["id"] for c in comments], ctx.prefix + "/issues/comments/{id}")
            def verify(response):
                return ctx.proof(ctx.prefix + "/issues/comments/" + str(positive(response["id"])), expected)
            steps.append(Step("add issue comment", "POST", path + "/comments", {"body": text}, spec, verify))
            baseline["comment_ids"] = sorted(c["id"] for c in comments)
        else:
            payload = {}
            if args.command == "edit-issue":
                text = body(args)
                for key, value in (("title", args.title), ("body", text)):
                    if value is not None:
                        if key == "title" and not value.strip():
                            raise Refusal("Title cannot be empty")
                        payload[key] = value
                        baseline[key] = issue[key]
                extra, old = metadata(ctx, args, issue)
                payload.update(extra)
                baseline.update(old)
                if not payload:
                    raise Refusal("Select at least one field change")
            else:
                payload["state"] = "closed" if args.command == "close-issue" else "open"
                baseline["state"] = issue["state"]
                if args.command == "close-issue":
                    payload["state_reason"] = args.reason
                    baseline["state_reason"] = issue.get("state_reason")
            expected = {key + "[]." + ("name" if key == "labels" else "login") if key in ("labels", "assignees") else key: value for key, value in payload.items()}
            if project(issue, expected) != expected:
                steps.append(Step("update issue", "PATCH", path, payload, rest_recovery(path, expected), lambda response: ctx.proof(path, expected)))
    return ctx.plan(baseline, steps, ["Subscribers and mentioned people may be notified"]), steps


def handler(args):
    ctx = Context(args)
    if args.command == "recover":
        return recover(ctx)
    if args.command == "read-issue":
        if args.execute:
            raise Refusal("read-issue does not execute writes")
        issue = ctx.item(args.issue)
        fields = set((args.fields or "issue,comments,coverage").split(","))
        if not fields <= {"issue", "comments", "coverage"}:
            raise Refusal("Fields must select issue,comments,coverage")
        data = {"coverage": {}}
        if "issue" in fields:
            data["issue"] = issue
        if "comments" in fields:
            comments, coverage = ctx.client.collection(ctx.prefix + "/issues/" + str(args.issue) + "/comments")
            data.update(comments=comments, coverage={"comments": coverage})
        return {"schema_version": 1, "outcome": "success", "host": ctx.host, "actor": ctx.actor, **data}
    plan, steps = prepare(ctx)
    return execute(ctx, plan, steps, prepare)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("read-issue", "create-issue", "edit-issue", "comment-issue", "close-issue", "reopen-issue", "recover"):
        p = sub.add_parser(command)
        add_common(p)
        if command == "recover":
            p.add_argument("--result-id", type=int, help="Explicitly inspected result ID, or issue number for issue creation")
        if command not in ("create-issue", "recover"):
            p.add_argument("--issue", type=int, required=True)
        if command == "read-issue":
            p.add_argument("--fields", help="Comma-separated issue,comments,coverage")
        if command in ("create-issue", "edit-issue", "comment-issue"):
            add_body(p)
        if command in ("create-issue", "edit-issue"):
            p.add_argument("--title", required=command == "create-issue")
            for name in ("label", "assignee"):
                if command == "create-issue":
                    p.add_argument("--" + name, action="append", default=[])
                else:
                    p.add_argument("--add-" + name, action="append", default=[])
                    p.add_argument("--remove-" + name, action="append", default=[])
            p.add_argument("--assign-me", action="store_true")
        if command == "create-issue":
            p.add_argument("--allow-duplicate", action="store_true")
        if command == "close-issue":
            p.add_argument("--reason", choices=("completed", "not_planned"), default="completed")
    return run(parser, handler)


if __name__ == "__main__":
    sys.exit(main())
