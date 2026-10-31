#!/usr/bin/env python3
"""Revision-aware PR inspection, preparation, review and deliberate integration."""
import argparse
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urlsplit

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-github" / "scripts"))
from collaboration import Context, Refusal, Step, TransportError, add_body, add_common, body, digest, execute, oid, positive, project, recover, rest_recovery, run

PR_INFO = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){id number headRefOid baseRefOid baseRef{name target{oid}} mergeable mergeStateStatus reviewDecision autoMergeRequest{enabledAt} mergeQueueEntry{id} stack{id} closingIssuesReferences(first:100){pageInfo{hasNextPage} nodes{number repository{nameWithOwner}}}}}}"""
MERGE_RESULT = """query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){id number merged headRefOid mergeCommit{oid}}}}"""
THREADS = """query($owner:String!,$name:String!,$number:Int!,$after:String){repository(owner:$owner,name:$name){pullRequest(number:$number){id number reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor} nodes{id isResolved isOutdated path line diffSide viewerCanResolve viewerCanUnresolve comments(first:100){pageInfo{hasNextPage endCursor} nodes{id databaseId body url author{login} commit{oid} originalCommit{oid}}}}}}}}"""
THREAD = """query($id:ID!,$after:String){node(id:$id){... on PullRequestReviewThread{id isResolved isOutdated path line diffSide viewerCanResolve viewerCanUnresolve pullRequest{number repository{nameWithOwner}} comments(first:100,after:$after){pageInfo{hasNextPage endCursor} nodes{id databaseId body url author{login} commit{oid} originalCommit{oid}}}}}}"""


def info(ctx, number):
    owner, name = ctx.repo.split("/")
    data = ctx.client.graphql(PR_INFO, owner=owner, name=name, number=number)
    value = (data.get("repository") or {}).get("pullRequest")
    if not value or value.get("number") != number or not value.get("id"):
        raise Refusal("PR rule/review metadata is unavailable", "unsupported")
    required = {"headRefOid", "baseRefOid", "baseRef", "mergeable", "mergeStateStatus", "reviewDecision", "autoMergeRequest", "mergeQueueEntry", "stack", "closingIssuesReferences"}
    if not required <= value.keys():
        raise Refusal("PR integration metadata is incomplete", "unsupported")
    return value


def thread(ctx, thread_id):
    if not re.fullmatch(r"[A-Za-z0-9_=-]+", thread_id or ""):
        raise Refusal("Invalid review-thread node ID")
    collected, after, value, complete = [], None, None, False
    for _ in range(ctx.args.page_limit):
        data = ctx.client.graphql(THREAD, id=thread_id, after=after)
        node = data.get("node")
        if not node or node.get("id") != thread_id or node.get("pullRequest", {}).get("number") != ctx.args.pr or node["pullRequest"].get("repository", {}).get("nameWithOwner", "").lower() != ctx.repo.lower():
            raise Refusal("Review thread does not belong to the selected repository/PR")
        value = node
        connection = node.get("comments") or {}
        batch = connection.get("nodes")
        if not isinstance(batch, list):
            raise Refusal("Malformed thread comments", "failed")
        remaining = ctx.args.item_limit - len(collected)
        collected.extend(batch[:remaining])
        page = connection.get("pageInfo") or {}
        if page.get("hasNextPage") is False and len(batch) <= remaining:
            complete = True
            break
        after = page.get("endCursor")
        if not after or len(collected) >= ctx.args.item_limit:
            break
    value["comments"] = collected
    return value, {"complete": complete, "observed": len(collected)}


def threads(ctx, number):
    owner, name = ctx.repo.split("/")
    collected, after, complete = [], None, False
    for _ in range(ctx.args.page_limit):
        data = ctx.client.graphql(THREADS, owner=owner, name=name, number=number, after=after)
        pr = (data.get("repository") or {}).get("pullRequest")
        if not pr or pr.get("number") != number:
            raise Refusal("Cannot verify review-thread parent", "failed")
        connection = pr.get("reviewThreads") or {}
        nodes = connection.get("nodes")
        if not isinstance(nodes, list):
            raise Refusal("Malformed review-thread connection", "failed")
        remaining = ctx.args.item_limit - len(collected)
        for node in nodes[:remaining]:
            value, coverage = thread(ctx, node["id"])
            value["coverage"] = coverage
            collected.append(value)
        page = connection.get("pageInfo") or {}
        if page.get("hasNextPage") is False and len(nodes) <= remaining:
            complete = True
            break
        after = page.get("endCursor")
        if not after or len(collected) >= ctx.args.item_limit:
            break
    return collected, {"complete": complete and all(v["coverage"]["complete"] for v in collected), "observed": len(collected)}


def inspect(ctx):
    args = ctx.args
    pr = ctx.item(args.pr, "pulls")
    head = oid(pr["head"]["sha"])
    output = {"pr": pr, "revision": {"head": head, "base": oid(pr["base"]["sha"])}, "coverage": {}}
    selected = set((args.fields or "pr,commits,files,comments,reviews,review_comments,threads,checks,statuses").split(","))
    allowed = {"pr", "commits", "files", "comments", "reviews", "review_comments", "threads", "checks", "statuses"}
    if not selected <= allowed:
        raise Refusal("Unknown inspection field")
    routes = {"commits": (f"{ctx.prefix}/pulls/{args.pr}/commits", None), "files": (f"{ctx.prefix}/pulls/{args.pr}/files", None), "comments": (f"{ctx.prefix}/issues/{args.pr}/comments", None), "reviews": (f"{ctx.prefix}/pulls/{args.pr}/reviews", None), "review_comments": (f"{ctx.prefix}/pulls/{args.pr}/comments", None), "checks": (f"{ctx.prefix}/commits/{head}/check-runs?filter=latest", "check_runs"), "statuses": (f"{ctx.prefix}/commits/{head}/statuses", None)}
    for name in selected - {"pr", "threads"}:
        try:
            values, coverage = ctx.client.collection(*routes[name])
            if name == "files":
                used, omitted = 0, []
                for value in values:
                    patch = value.get("patch")
                    size = len(patch.encode()) if isinstance(patch, str) else 0
                    if patch is None or used + size > args.diff_bytes:
                        value.pop("patch", None)
                        value["patch_coverage"] = "unavailable_or_binary" if patch is None else "byte_limit"
                        omitted.append(value.get("filename"))
                    else:
                        used += size
                        value["patch_coverage"] = "returned_by_github"
                coverage.update(patch_bytes=used, patch_limit=args.diff_bytes, patches_omitted=omitted, full_diff_guaranteed=False)
                if len(values) != pr.get("changed_files"):
                    coverage["complete"] = False
            if name == "commits" and len(values) != pr.get("commits"):
                coverage["complete"] = False
            output[name], output["coverage"][name] = values, coverage
        except TransportError as exc:
            output[name] = []
            output["coverage"][name] = {"complete": False, "reason": str(exc)}
    if "threads" in selected:
        try:
            output["threads"], output["coverage"]["threads"] = threads(ctx, args.pr)
        except (TransportError, Refusal) as exc:
            output["threads"] = []
            output["coverage"]["threads"] = {"complete": False, "reason": str(exc)}
    final = ctx.item(args.pr, "pulls")
    output["coverage"]["revision_stable"] = final["head"]["sha"] == head and final["base"]["sha"] == pr["base"]["sha"]
    if "pr" not in selected:
        output.pop("pr")
    return {"schema_version": 1, "outcome": "success", "host": ctx.host, "actor": ctx.actor, **output}


def existing_comments(ctx, path):
    values, coverage = ctx.client.collection(path)
    if not coverage["complete"]:
        raise Refusal("Append/review reconciliation baseline is incomplete; raise the explicit read limits")
    return values


def metadata(ctx, args, pr, creating=False):
    steps, baseline = [], {}
    number = "{created}" if creating else str(args.pr)
    issue_path = ctx.prefix + "/issues/" + number
    for plural, singular, key in (("labels", "label", "name"), ("assignees", "assignee", "login")):
        add = getattr(args, singular if creating else "add_" + singular, [])
        remove = [] if creating else getattr(args, "remove_" + singular, [])
        if set(add) & set(remove):
            raise Refusal("Cannot add and remove the same metadata value")
        if not add and not remove:
            continue
        values = {item[key] for item in pr.get(plural, [])}
        baseline[plural + "[]." + key] = sorted(values)
        for value in add:
            if plural == "labels":
                resolved = ctx.client.get(ctx.prefix + "/labels/" + quote(value, safe="")).get("name")
            else:
                if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                    raise Refusal("Invalid assignee")
                resolved = ctx.client.get("users/" + value).get("login")
            if not resolved:
                raise Refusal("Cannot resolve metadata")
            values.add(resolved)
        values = sorted(v for v in values if v.lower() not in {r.lower() for r in remove})
        if values == baseline[plural + "[]." + key]:
            continue
        expected = {plural + "[]." + key: values}
        payload = {plural: values}
        path = issue_path + ("/labels" if plural == "labels" else "")
        method = "PUT" if plural == "labels" else "PATCH"
        def verify(response, expected=expected):
            return ctx.proof(ctx.prefix + "/issues/" + str(ctx.created_number if creating else args.pr), expected)
        steps.append(Step("set PR " + plural, method, path, payload, rest_recovery(issue_path, expected), verify))
    return steps, baseline


def reviewers(ctx, args, pr, creating=False):
    add = getattr(args, "reviewer", []) if creating else getattr(args, "add_reviewer", [])
    remove = [] if creating else getattr(args, "remove_reviewer", [])
    add_teams = getattr(args, "team_reviewer", []) if creating else getattr(args, "add_team_reviewer", [])
    remove_teams = [] if creating else getattr(args, "remove_team_reviewer", [])
    if not any((add, remove, add_teams, remove_teams)):
        return [], {}
    if set(add) & set(remove) or set(add_teams) & set(remove_teams):
        raise Refusal("Cannot add and remove the same reviewer")
    users = sorted(item["login"] for item in pr.get("requested_reviewers", []))
    teams = sorted(item["slug"] for item in pr.get("requested_teams", []))
    baseline = {"requested_reviewers": users, "requested_teams": teams}
    canonical_add = []
    for value in add:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise Refusal("Cannot resolve reviewer")
        resolved = ctx.client.get("users/" + value)
        if not resolved.get("id") or not resolved.get("login"):
            raise Refusal("Cannot resolve reviewer")
        canonical_add.append(resolved["login"])
    add = canonical_add
    remove = [value for value in users if value.lower() in {r.lower() for r in remove}]
    remove_teams = [value for value in teams if value.lower() in {r.lower() for r in remove_teams}]
    for value in add_teams:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value) or not ctx.client.get("orgs/" + ctx.repo.split("/")[0] + "/teams/" + value).get("id"):
            raise Refusal("Cannot resolve reviewer team")
    path = ctx.prefix + "/pulls/" + ("{created}" if creating else str(args.pr)) + "/requested_reviewers"
    steps = []
    for method, selected_users, selected_teams in (("POST", add, add_teams), ("DELETE", remove, remove_teams)):
        if not selected_users and not selected_teams:
            continue
        before = (users, teams)
        if method == "POST":
            users, teams = sorted(set(users) | set(selected_users)), sorted(set(teams) | set(selected_teams))
        else:
            users, teams = sorted(set(users) - set(selected_users)), sorted(set(teams) - set(selected_teams))
        if (users, teams) == before:
            continue
        expected = {"users[].login": users, "teams[].slug": teams}
        def verify(response, expected=expected):
            return ctx.proof(ctx.prefix + "/pulls/" + str(ctx.created_number if creating else args.pr) + "/requested_reviewers", expected)
        steps.append(Step("request reviewers" if method == "POST" else "remove reviewer requests", method, path, {"reviewers": selected_users, "team_reviewers": selected_teams}, rest_recovery(path, expected), verify))
    return steps, baseline


def merge_evidence(ctx, pr):
    args = ctx.args
    metadata = info(ctx, args.pr)
    head, snapshot_base = oid(pr["head"]["sha"]), oid(pr["base"]["sha"])
    if metadata.get("headRefOid") != head or metadata.get("baseRefOid") != snapshot_base:
        raise Refusal("PR refs changed while obtaining merge evidence")
    base_ref = metadata.get("baseRef")
    if not isinstance(base_ref, dict) or base_ref.get("name") != pr["base"]["ref"] or not isinstance(base_ref.get("target"), dict) or not base_ref["target"].get("oid"):
        raise Refusal("Current base reference evidence is incomplete or mismatched", "unsupported")
    base = oid(base_ref["target"]["oid"])
    branch = ctx.client.get(ctx.prefix + "/branches/" + quote(pr["base"]["ref"], safe=""))
    if branch.get("name") != pr["base"]["ref"] or (branch.get("commit") or {}).get("sha") != base:
        raise Refusal("Base branch moved while assessing integration")
    rules, coverage = ctx.client.collection(ctx.prefix + "/rules/branches/" + quote(pr["base"]["ref"], safe=""))
    if not coverage["complete"]:
        raise Refusal("Effective repository-rule evidence is incomplete", "unsupported")
    protection = None
    if branch.get("protected"):
        protection = ctx.client.get(ctx.prefix + "/branches/" + quote(pr["base"]["ref"], safe="") + "/protection")
    checks, check_coverage = ctx.client.collection(ctx.prefix + "/commits/" + head + "/check-runs?filter=latest", "check_runs")
    statuses, status_coverage = ctx.client.collection(ctx.prefix + "/commits/" + head + "/statuses")
    commits, commit_coverage = ctx.client.collection(ctx.prefix + f"/pulls/{args.pr}/commits")
    if not all(c["complete"] for c in (check_coverage, status_coverage, commit_coverage)) or len(commits) != pr.get("commits"):
        raise Refusal("Merge check/status/commit coverage is incomplete", "unsupported")
    blockers = []
    if ctx.repository.get("delete_branch_on_merge"):
        blockers.append("Repository automatic branch deletion is enabled; this operation does not authorize deletion")
    if metadata.get("stack"):
        blockers.append("Stack integration can affect additional PRs and needs a separately scoped operation")
    closing = metadata.get("closingIssuesReferences")
    if not isinstance(closing, dict) or (closing.get("pageInfo") or {}).get("hasNextPage") is not False or not isinstance(closing.get("nodes"), list):
        blockers.append("Linked issue-closure coverage is incomplete")
    if pr.get("state") != "open" or pr.get("draft") or pr.get("merged"):
        blockers.append("PR must be open, ready and unmerged")
    if metadata.get("mergeable") != "MERGEABLE" or metadata.get("mergeStateStatus") != "CLEAN":
        blockers.append("GitHub does not report a clean, mergeable contribution")
    if metadata.get("autoMergeRequest") or metadata.get("mergeQueueEntry") or any(rule.get("type") == "merge_queue" for rule in rules):
        blockers.append("Queue/auto-merge workflows require a separately supported route")
    if any(c.get("status") != "completed" or c.get("conclusion") not in ("success", "neutral", "skipped") for c in checks):
        blockers.append("A current check has not passed")
    latest = {}
    for status in statuses:
        latest.setdefault(status.get("context"), status)
    if any(s.get("state") != "success" for s in latest.values()):
        blockers.append("A current commit status has not passed")
    required_contexts = set()
    required_apps = []
    required_reviews = bool((protection or {}).get("required_pull_request_reviews"))
    conversations_required = bool((protection or {}).get("required_conversation_resolution", {}).get("enabled"))
    supported_rules = {"pull_request", "required_status_checks", "merge_queue", "non_fast_forward", "required_linear_history"}
    for rule in rules:
        if rule.get("type") not in supported_rules:
            blockers.append("Unsupported rule evidence: " + str(rule.get("type")))
        if rule.get("type") == "required_status_checks":
            required = rule.get("parameters", {}).get("required_status_checks", [])
            required_contexts.update(c["context"] for c in required)
            required_apps.extend((c["context"], c.get("integration_id")) for c in required if c.get("integration_id") not in (None, -1))
        if rule.get("type") == "pull_request":
            required_reviews = rule.get("parameters", {}).get("required_approving_review_count", 0) > 0 or required_reviews
            conversations_required = conversations_required or rule.get("parameters", {}).get("required_review_thread_resolution", False)
    protection_checks = (protection or {}).get("required_status_checks") or {}
    required_contexts.update(protection_checks.get("contexts", []))
    required_contexts.update(v["context"] for v in protection_checks.get("checks", []))
    required_apps.extend((c["context"], c.get("app_id")) for c in protection_checks.get("checks", []) if c.get("app_id") not in (None, -1))
    observed = {c.get("name") for c in checks} | set(latest)
    if required_contexts - observed:
        blockers.append("Required checks are absent from the observed head")
    if required_reviews and metadata.get("reviewDecision") != "APPROVED":
        blockers.append("Required review approval is not established")
    if any(not any(c.get("name") == name and (c.get("app") or {}).get("id") == app for c in checks) for name, app in required_apps):
        blockers.append("Required check application's identity is not established")
    if conversations_required:
        values, thread_coverage = threads(ctx, args.pr)
        if not thread_coverage["complete"] or any(not value.get("isResolved") for value in values):
            blockers.append("Required review-thread resolution is incomplete")
    return {"head": head, "base": base, "pr_base_snapshot": snapshot_base, "base_branch_sha": (branch.get("commit") or {}).get("sha"), "metadata": metadata, "rules": rules, "protection": protection, "checks": checks, "statuses": statuses, "commits": [c["sha"] for c in commits], "blockers": blockers}


def prepare(ctx):
    args, steps = ctx.args, []
    effects = ["Subscribers, mentioned people and requested reviewers may be notified"]
    if args.command == "create-pr":
        expected_head = oid(args.expected_head)
        head_repo = args.head_repo or ctx.repo
        if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", head_repo):
            raise Refusal("Head repository must be explicit OWNER/REPO on the selected host")
        head_repository = ctx.client.get("repos/" + head_repo)
        if head_repository.get("full_name", "").lower() != head_repo.lower() or not head_repository.get("id"):
            raise Refusal("Published head repository identity does not match")
        head_repo = head_repository["full_name"]
        head = ctx.client.get("repos/" + head_repo + "/branches/" + quote(args.head, safe=""))
        base = ctx.client.get(ctx.prefix + "/branches/" + quote(args.base, safe=""))
        if (head.get("commit") or {}).get("sha") != expected_head:
            raise Refusal("Published head does not match --expected-head")
        if not args.title.strip():
            raise Refusal("A nonempty title is required")
        text = body(args) or ""
        payload = {"title": args.title, "body": text, "head": head_repo.split("/")[0] + ":" + args.head, "head_repo": head_repo.split("/")[1], "base": args.base, "draft": not args.ready, "maintainer_can_modify": args.maintainer_edit}
        existing = existing_comments(ctx, ctx.prefix + "/pulls?state=all&head=" + quote(payload["head"], safe="") + "&base=" + quote(args.base, safe=""))
        if any(item.get("state") == "open" for item in existing):
            raise Refusal("An open PR already exists for the selected head/base")
        expected = {"title": args.title, "body": text, "draft": payload["draft"], "head.sha": expected_head, "head.ref": args.head, "head.repo.full_name": head_repo, "base.ref": args.base, "base.repo.full_name": ctx.repo, "user.id": ctx.actor["id"]}
        spec = rest_recovery(ctx.prefix + "/pulls?state=all&head=" + quote(payload["head"], safe="") + "&base=" + quote(args.base, safe=""), expected, True, [item["id"] for item in existing], ctx.prefix + "/pulls/{number}")
        def verify(response):
            ctx.created_number = positive(response["number"])
            return ctx.proof(ctx.prefix + "/pulls/" + str(ctx.created_number), expected)
        steps.append(Step("create PR from published refs", "POST", ctx.prefix + "/pulls", payload, spec, verify))
        metadata_steps, _ = metadata(ctx, args, {}, True)
        reviewer_steps, _ = reviewers(ctx, args, {}, True)
        steps += metadata_steps + reviewer_steps
        baseline = {"head": expected_head, "head_repository_id": head_repository["id"], "base": oid(base["commit"]["sha"]), "known_pr_ids": sorted(item["id"] for item in existing)}
        if re.search(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:[\w.-]+/[\w.-]+)?#\d+", text, re.I):
            effects.append("Body contains issue-closing references which may close issues on integration")
        return ctx.plan(baseline, steps, effects), steps

    pr = ctx.item(args.pr, "pulls")
    path = ctx.prefix + "/pulls/" + str(args.pr)
    head = oid(pr["head"]["sha"])
    if getattr(args, "expected_head", None) and oid(args.expected_head) != head:
        raise Refusal("PR head differs from the inspected --expected-head")
    baseline = {"id": pr["id"], "head": head, "base": pr["base"]["sha"]}
    if args.command in ("close-pr", "reopen-pr", "edit-pr"):
        if args.command == "reopen-pr" and pr.get("merged"):
            raise Refusal("A merged pull request cannot be reopened")
        payload = {}
        if args.command == "edit-pr":
            for key, value in (("title", args.title), ("body", body(args))):
                if value is not None:
                    if key == "title" and not value.strip():
                        raise Refusal("Title cannot be empty")
                    payload[key], baseline[key] = value, pr[key]
                    if key == "body" and re.search(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:[\w.-]+/[\w.-]+)?#\d+", value, re.I):
                        effects.append("Replacement body contains issue-closing references which may close issues on integration")
            if args.base is not None:
                base = ctx.client.get(ctx.prefix + "/branches/" + quote(args.base, safe=""))
                payload["base"] = args.base
                baseline["new_base_sha"] = base["commit"]["sha"]
                effects.append("Retargeting changes the reviewed diff and may invalidate reviews")
        else:
            payload["state"] = "closed" if args.command == "close-pr" else "open"
            baseline["state"] = pr["state"]
        if payload:
            expected = {"base.ref" if key == "base" else key: value for key, value in payload.items()}
            if project(pr, expected) != expected:
                steps.append(Step("update PR fields", "PATCH", path, payload, rest_recovery(path, expected), lambda response, expected=expected: ctx.proof(path, expected)))
        if args.command == "edit-pr":
            metadata_steps, old = metadata(ctx, args, pr)
            baseline.update(old)
            reviewer_steps, old = reviewers(ctx, args, pr)
            baseline.update(old)
            steps += metadata_steps + reviewer_steps
            if args.ready or args.draft:
                desired = not args.ready
                baseline["draft"] = pr["draft"]
                if desired != pr["draft"]:
                    mutation = "convertPullRequestToDraft" if desired else "markPullRequestReadyForReview"
                    query = "mutation($id:ID!){" + mutation + "(input:{pullRequestId:$id}){pullRequest{id isDraft}}}"
                    expected = {"draft": desired}
                    steps.append(Step("change PR readiness", "POST", "graphql", {"query": query, "variables": {"id": pr["node_id"]}}, rest_recovery(path, expected), lambda response: ctx.proof(path, expected)))
            selected_metadata = any(getattr(args, action + "_" + name, []) for action in ("add", "remove") for name in ("label", "assignee", "reviewer", "team_reviewer"))
            if not steps and not (payload or args.ready or args.draft or selected_metadata):
                raise Refusal("Select at least one PR field or metadata change")
    elif args.command in ("comment-pr", "review-pr", "inline-comment", "reply-review-comment"):
        text = (body(args) or "") if args.command == "review-pr" and args.event == "APPROVE" else body(args, required=True)
        if args.command == "comment-pr":
            collection, read_path = ctx.prefix + f"/issues/{args.pr}/comments", ctx.prefix + "/issues/comments/{id}"
            payload, expected = {"body": text}, {"body": text, "user.id": ctx.actor["id"], "issue_url": pr["issue_url"]}
        elif args.command == "review-pr":
            collection, read_path = path + "/reviews", path + "/reviews/{id}"
            payload = {"body": text, "event": args.event, "commit_id": head}
            expected = {"body": text, "state": {"APPROVE": "APPROVED", "COMMENT": "COMMENTED", "REQUEST_CHANGES": "CHANGES_REQUESTED"}[args.event], "commit_id": head, "user.id": ctx.actor["id"], "pull_request_url": pr["url"]}
        elif args.command == "reply-review-comment":
            parent = ctx.client.get(ctx.prefix + "/pulls/comments/" + str(positive(args.comment)))
            parent_url = urlsplit(parent.get("pull_request_url", ""))
            if parent_url.hostname not in (ctx.host, "api." + ctx.host) or not parent_url.path.rstrip("/").endswith("/" + path):
                raise Refusal("Review comment parent does not match the selected PR")
            if parent.get("in_reply_to_id"):
                raise Refusal("Reply to the original top-level review comment")
            collection, read_path = path + "/comments", ctx.prefix + "/pulls/comments/{id}"
            payload, expected = {"body": text}, {"body": text, "in_reply_to_id": args.comment, "user.id": ctx.actor["id"], "pull_request_url": pr["url"]}
        else:
            files, coverage = ctx.client.collection(path + "/files")
            if not coverage["complete"] or len(files) != pr.get("changed_files"):
                raise Refusal("Cannot verify inline anchor with incomplete file coverage")
            file = next((v for v in files if v.get("filename") == args.path), None)
            if not file or not anchor_in_patch(file.get("patch"), args.line, args.side, args.start_line):
                raise Refusal("Inline line/range is not present in the inspected diff")
            collection, read_path = path + "/comments", ctx.prefix + "/pulls/comments/{id}"
            payload = {"body": text, "commit_id": head, "path": args.path, "line": args.line, "side": args.side}
            if args.start_line:
                payload.update(start_line=args.start_line, start_side=args.side)
            expected = {**payload, "user.id": ctx.actor["id"], "pull_request_url": pr["url"]}
        existing = existing_comments(ctx, collection)
        baseline["existing_ids"] = sorted(item["id"] for item in existing)
        spec = rest_recovery(collection, expected, True, baseline["existing_ids"], read_path)
        if args.command != "comment-pr":
            spec.update(pr_head=head, pr=args.pr)
        send_path = path + f"/comments/{args.comment}/replies" if args.command == "reply-review-comment" else collection
        def verify(response):
            proof = ctx.proof(read_path.format(id=positive(response["id"])), expected)
            if ctx.item(args.pr, "pulls")["head"]["sha"] != head:
                raise Refusal("Feedback was submitted but the PR head changed; inspect the recorded commit", "uncertain")
            return {**proof, "pr_head": head, "pr": args.pr} if args.command != "comment-pr" else proof
        steps.append(Step(args.command, "POST", send_path, payload, spec, verify))
    elif args.command in ("resolve-thread", "unresolve-thread"):
        current, coverage = thread(ctx, args.thread_id)
        desired = args.command == "resolve-thread"
        baseline["thread"] = {"id": args.thread_id, "isResolved": current["isResolved"], "comments": [v["id"] for v in current["comments"]], "context_digest": digest(current["comments"])}
        if not coverage["complete"] or current.get("isOutdated"):
            raise Refusal("Thread context is incomplete or outdated")
        if current["isResolved"] != desired:
            if not current.get("viewerCanResolve" if desired else "viewerCanUnresolve"):
                raise Refusal("Effective actor cannot change this thread's resolution")
            mutation = "resolveReviewThread" if desired else "unresolveReviewThread"
            query = "mutation($id:ID!){" + mutation + "(input:{threadId:$id}){thread{id isResolved}}}"
            spec = {"kind": "thread", "thread_id": args.thread_id, "pr": args.pr, "isResolved": desired, "head": head}
            steps.append(Step(args.command, "POST", "graphql", {"query": query, "variables": {"id": args.thread_id}}, spec, lambda response: verify_special(ctx, spec)))
    elif args.command == "merge-pr":
        if not args.integration_discussed:
            raise Refusal("Merge requires a separate human/agent integration discussion and --integration-discussed")
        evidence = merge_evidence(ctx, pr)
        baseline["base"] = evidence["base"]
        baseline["integration"] = evidence
        if evidence["blockers"]:
            raise Refusal("Merge blocked: " + "; ".join(evidence["blockers"]))
        if args.preserve_history and args.method != "merge":
            raise Refusal("Preserving original commits requires the merge method")
        linear = any(rule.get("type") == "required_linear_history" for rule in evidence["rules"]) or bool((evidence["protection"] or {}).get("required_linear_history", {}).get("enabled"))
        if linear and args.method == "merge":
            raise Refusal("Repository requires linear history; the requested merge commit is incompatible")
        method_setting = {"merge": "allow_merge_commit", "squash": "allow_squash_merge", "rebase": "allow_rebase_merge"}[args.method]
        if not ctx.repository.get(method_setting, False):
            raise Refusal("Requested merge method is not enabled")
        for required_path in args.require_path:
            if required_path.startswith("/") or ".." in required_path.split("/") or not required_path:
                raise Refusal("Required document path must stay inside the repository")
            content = ctx.client.get(ctx.prefix + "/contents/" + quote(required_path, safe="/") + "?ref=" + head)
            if not isinstance(content, dict) or content.get("path") != required_path or content.get("type") != "file":
                raise Refusal("Required tracked document is absent from the contribution")
        spec = {"kind": "merge", "pr": args.pr, "head": head, "base": evidence["base"], "head_repo": pr["head"]["repo"]["full_name"], "head_ref": pr["head"]["ref"], "commits": evidence["commits"] if args.preserve_history else [], "require_paths": args.require_path, "method": args.method, "acknowledged": False}
        def verify_merge(response):
            result = response
            accepted_id = result.get("uuid") or (result.get("details") or {}).get("uuid")
            if result.get("status") == "pending" and re.fullmatch(r"[A-Za-z0-9_-]+", accepted_id or ""):
                spec["acknowledged"] = True
            for _ in range(5):
                if result.get("status") == "merged":
                    return verify_special(ctx, spec)
                if result.get("status") != "pending":
                    raise Refusal("Merge returned an unexpected non-merged outcome; inspect before any further action", "uncertain")
                request_id = result.get("uuid") or (result.get("details") or {}).get("uuid")
                if not re.fullmatch(r"[A-Za-z0-9_-]+", request_id or ""):
                    raise Refusal("Merge is pending without a verifiable request ID", "uncertain")
                time.sleep(1)
                result = ctx.client.get(path + "/merge-async/" + request_id)
            raise Refusal("Merge remains pending; use recover for fresh readback without resending", "uncertain")
        steps.append(Step("integrate reviewed contribution", "PUT", path + "/merge-async", {"sha": head, "merge_method": args.method, "merge_action": "direct_merge", "bypass_rules": False}, spec, verify_merge))
        effects += ["Integrates this exact reviewed head into the base branch", "Linked issues may close; repository automations may run", "Base movement between final read and server merge cannot be atomically excluded"]
    else:
        raise Refusal("Unsupported PR operation", "unsupported")
    return ctx.plan(baseline, steps, effects), steps


def anchor_in_patch(patch, line, side, start=None):
    if not isinstance(patch, str) or line < 1 or (start is not None and not 1 <= start < line):
        return False
    observed, old, new = set(), None, None
    for value in patch.splitlines():
        match = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", value)
        if match:
            old, new = int(match[1]), int(match[2])
        elif old is not None and value and value[0] in " +-":
            if value[0] in " -":
                if side == "LEFT":
                    observed.add(old)
                old += 1
            if value[0] in " +":
                if side == "RIGHT":
                    observed.add(new)
                new += 1
    return all(n in observed for n in range(start or line, line + 1))


def verify_special(ctx, spec):
    ctx.args.pr = positive(spec["pr"])
    pr = ctx.item(ctx.args.pr, "pulls")
    if pr["head"]["sha"] != spec["head"]:
        raise Refusal("PR head changed during recovery/readback", "uncertain")
    if spec["kind"] == "thread":
        value, _ = thread(ctx, spec["thread_id"])
        if value["isResolved"] != spec["isResolved"]:
            raise Refusal("Thread resolution was not independently verified", "uncertain")
        return spec
    if spec["kind"] != "merge":
        raise Refusal("Unknown PR recovery evidence", "unsupported")
    owner, name = ctx.repo.split("/")
    data = ctx.client.graphql(MERGE_RESULT, owner=owner, name=name, number=spec["pr"])
    merged = (data.get("repository") or {}).get("pullRequest") or {}
    merge_sha = (merged.get("mergeCommit") or {}).get("oid")
    if not pr.get("merged") or merged.get("id") != pr.get("node_id") or merged.get("number") != spec["pr"] or not merged.get("merged") or merged.get("headRefOid") != spec["head"] or not merge_sha:
        raise Refusal("PR is not independently verified as merged", "uncertain")
    merge_sha = oid(merge_sha)
    if spec["method"] == "merge":
        commit = ctx.client.get(ctx.prefix + "/git/commits/" + oid(merge_sha))
        parents = [parent.get("sha") for parent in commit.get("parents", [])]
        if parents != [spec["base"], spec["head"]]:
            raise Refusal("Integrated parents differ from the discussed base/head; inspect the resulting integration", "uncertain")
    elif not spec.get("acknowledged"):
        raise Refusal("Integration is present but the requested squash/rebase method lacks acknowledged request evidence", "uncertain")
    head_branch = ctx.client.get("repos/" + spec["head_repo"] + "/branches/" + quote(spec["head_ref"], safe=""))
    if (head_branch.get("commit") or {}).get("sha") != spec["head"]:
        raise Refusal("The source branch changed or disappeared during integration", "uncertain")
    for commit in spec["commits"]:
        comparison = ctx.client.get(ctx.prefix + "/compare/" + oid(commit) + "..." + oid(merge_sha))
        if comparison.get("status") not in ("ahead", "identical") or comparison.get("merge_base_commit", {}).get("sha") != commit:
            raise Refusal("An original contribution commit is not reachable after integration", "uncertain")
    for path in spec["require_paths"]:
        if path.startswith("/") or ".." in path.split("/"):
            raise Refusal("Required document path must stay inside the repository")
        value = ctx.client.get(ctx.prefix + "/contents/" + quote(path, safe="/") + "?ref=" + oid(merge_sha))
        if not isinstance(value, dict) or value.get("path") != path or value.get("type") != "file":
            raise Refusal("Required tracked document is absent after integration", "uncertain")
    return {**spec, "merge_commit_sha": merge_sha, "url": pr["html_url"]}


def handler(args):
    ctx = Context(args)
    if args.command == "recover":
        return recover(ctx, lambda spec: verify_special(ctx, spec))
    if args.command == "read-pr":
        if args.execute:
            raise Refusal("read-pr does not execute writes")
        return inspect(ctx)
    if args.command == "read-thread":
        if args.execute:
            raise Refusal("read-thread does not execute writes")
        value, coverage = thread(ctx, args.thread_id)
        return {"schema_version": 1, "outcome": "success", "thread": value, "coverage": coverage}
    if args.command == "assess-merge":
        if args.execute:
            raise Refusal("assess-merge does not execute writes")
        value = merge_evidence(ctx, ctx.item(args.pr, "pulls"))
        return {"schema_version": 1, "outcome": "success", "assessment": value, "writes_sent": 0, "merge_authorized": False}
    plan, steps = prepare(ctx)
    return execute(ctx, plan, steps, prepare)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    commands = ("read-pr", "read-thread", "create-pr", "edit-pr", "close-pr", "reopen-pr", "comment-pr", "review-pr", "inline-comment", "reply-review-comment", "resolve-thread", "unresolve-thread", "assess-merge", "merge-pr", "recover")
    for command in commands:
        p = sub.add_parser(command)
        add_common(p)
        if command == "recover":
            p.add_argument("--result-id", type=int, help="Explicitly inspected result ID, or PR number for PR creation")
        if command not in ("create-pr", "recover"):
            p.add_argument("--pr", type=int, required=True)
        if command in ("create-pr", "edit-pr", "comment-pr", "review-pr", "inline-comment", "reply-review-comment"):
            add_body(p)
        if command in ("create-pr", "edit-pr"):
            p.add_argument("--title", required=command == "create-pr")
            p.add_argument("--base", required=command == "create-pr")
            group = p.add_mutually_exclusive_group()
            group.add_argument("--ready", action="store_true")
            group.add_argument("--draft", action="store_true")
            for name in ("label", "assignee", "reviewer", "team-reviewer"):
                if command == "create-pr":
                    p.add_argument("--" + name, action="append", default=[])
                else:
                    p.add_argument("--add-" + name, action="append", default=[])
                    p.add_argument("--remove-" + name, action="append", default=[])
        if command == "create-pr":
            p.add_argument("--head", required=True)
            p.add_argument("--head-repo")
            p.add_argument("--expected-head", required=True)
            p.add_argument("--maintainer-edit", action="store_true")
        if command in ("review-pr", "inline-comment", "reply-review-comment", "resolve-thread", "unresolve-thread", "merge-pr"):
            p.add_argument("--expected-head", required=True)
        if command == "review-pr":
            p.add_argument("--event", choices=("COMMENT", "APPROVE", "REQUEST_CHANGES"), required=True)
        if command == "inline-comment":
            p.add_argument("--path", required=True)
            p.add_argument("--line", type=int, required=True)
            p.add_argument("--start-line", type=int)
            p.add_argument("--side", choices=("LEFT", "RIGHT"), default="RIGHT")
        if command == "reply-review-comment":
            p.add_argument("--comment", type=int, required=True)
        if command in ("resolve-thread", "unresolve-thread", "read-thread"):
            p.add_argument("--thread-id", required=True)
        if command == "read-pr":
            p.add_argument("--fields")
            p.add_argument("--diff-bytes", type=int, default=2_000_000)
        if command == "merge-pr":
            p.add_argument("--method", choices=("merge", "squash", "rebase"), required=True)
            p.add_argument("--integration-discussed", action="store_true")
            p.add_argument("--preserve-history", action="store_true")
            p.add_argument("--require-path", action="append", default=[])
    return run(parser, handler)


if __name__ == "__main__":
    sys.exit(main())
