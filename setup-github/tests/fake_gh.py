#!/usr/bin/env python3
"""Stateful offline GitHub transport; accepts only explicitly modeled requests."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import parse_qs, unquote, urlsplit


def main():
    args = sys.argv[1:]
    if not args or args[0] != "api":
        raise RuntimeError("Only fixture API calls are allowed")
    method, path, host = "GET", None, None
    i = 1
    while i < len(args):
        if args[i] in ("--method", "--hostname", "-H", "--input"):
            key, value = args[i:i + 2]
            if key == "--method":
                method = value
            elif key == "--hostname":
                host = value
            i += 2
        elif args[i] == "--include":
            i += 1
        else:
            path = args[i]
            i += 1
    payload = json.load(sys.stdin) if "--input" in args else None
    file = Path(os.environ["FAKE_GITHUB_STATE"])
    state = json.loads(file.read_text())
    call = {"method": method, "path": path, "host": host, "payload": payload}
    state.setdefault("calls", []).append(call)
    query = (payload or {}).get("query", "")
    mutation = method != "GET" and not (path == "graphql" and not query.startswith("mutation"))
    if mutation:
        state.setdefault("mutations", []).append(call)
    fault = state.get("fault") or {}
    fail = fault and fault.get("method", method) == method and fault.get("path", "") in path

    def save():
        file.write_text(json.dumps(state))

    def respond(value, status=200):
        if mutation and state.get("head_changes_after_send"):
            state["prs"]["2"]["head"]["sha"] = "e" * 40
        save()
        if fail and fault.get("mode") == "after" and mutation:
            sys.exit(1)
        if fail and fault.get("mode") == "malformed":
            print("HTTP/2.0 200 OK\nContent-Type: application/json\n\n{broken")
            sys.exit(0)
        if fail and fault.get("mode") == "wrong-parent" and isinstance(value, dict):
            value = {**value, "issue_url": "https://api.github.com/repos/example-owner/example-project/issues/999"}
        print("HTTP/2.0 %s Fixture\nContent-Type: application/json\n\n%s" % (status, json.dumps(value)))
        sys.exit(0 if status < 400 else 1)

    if fail and fault.get("mode") == "refuse":
        respond({"message": "Synthetic refusal"}, 403)
    if path == "user":
        if state.get("actor_change_at") and len(state["calls"]) >= state["actor_change_at"]:
            respond({"id": 999, "login": "other-user"})
        respond(state["actor"])
    prefix = "repos/example-owner/example-project"
    parsed = urlsplit(path)
    route, params = unquote(parsed.path), parse_qs(parsed.query)
    actor = state["actor"]
    race = state.get("race") or {}
    if method == "GET" and path == race.get("path") and sum(c["path"] == path and c["method"] == "GET" for c in state["calls"]) == race.get("occurrence"):
        state["issues"]["1"]["body"] = "Concurrent change under lock"

    def page(values):
        start = (int(params.get("page", ["1"])[0]) - 1) * 100
        return values[start:start + 100]

    def issue_record(value):
        value = dict(value)
        if value.get("head"):
            value["pull_request"] = {"url": value["html_url"]}
        return value

    if route == prefix:
        respond(state["repository"])
    if route == "repos/fork-owner/example-project":
        respond({"id": 20, "full_name": "fork-owner/example-project"})
    if route.startswith("repos/fork-owner/example-project/branches/"):
        respond({"name": route.rsplit("/", 1)[1], "commit": {"sha": state["head"]}})
    if route.startswith("users/"):
        respond({"id": 200, "login": route.split("/")[-1]})
    if route.startswith("orgs/") and "/teams/" in route:
        respond({"id": 300, "slug": route.split("/")[-1]})
    if route.startswith(prefix + "/labels/"):
        respond({"id": 400, "name": route.split("/")[-1]})
    if route == "graphql":
        variables = payload["variables"]
        pr = state["prs"][str(variables.get("number", state.get("thread_pr", 2)))]
        if fault.get("mode") == "graphql-errors":
            respond({"data": {"partial": True}, "errors": [{"message": "Synthetic error"}]})
        if query.startswith("mutation"):
            if "convertPullRequestToDraft" in query or "markPullRequestReadyForReview" in query:
                pr["draft"] = "convertPullRequestToDraft" in query
            elif "resolveReviewThread" in query or "unresolveReviewThread" in query:
                state["thread"]["isResolved"] = "unresolveReviewThread" not in query
            else:
                raise RuntimeError("Unmodeled mutation")
            respond({"data": {"result": {"id": "RESULT"}}})
        if "reviewThreads" in query:
            respond({"data": {"repository": {"pullRequest": {"id": pr["node_id"], "number": pr["number"], "reviewThreads": {"nodes": [state["thread"]], "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}})
        if "node(id:" in query:
            value = dict(state["thread"])
            if variables["id"] != value["id"]:
                respond({"data": {"node": None}})
            respond({"data": {"node": value}})
        value = {"id": pr["node_id"], "number": pr["number"], "headRefOid": pr["head"]["sha"], "baseRefOid": pr["base"]["sha"], "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN", "reviewDecision": "APPROVED", "autoMergeRequest": None, "mergeQueueEntry": None, "stack": None, "closingIssuesReferences": {"nodes": [], "pageInfo": {"hasNextPage": False}}}
        value.update(state.get("merge_metadata", {}))
        respond({"data": {"repository": {"pullRequest": value}}})
    if route == prefix + "/issues" and method == "GET":
        respond(page(list(state["issues"].values())))
    if route == prefix + "/pulls" and method == "GET":
        values = list(state["prs"].values())
        if "head" in params:
            owner, ref = params["head"][0].split(":", 1)
            values = [v for v in values if v["head"]["ref"] == ref and v["head"]["repo"]["full_name"].split("/")[0] == owner and v["base"]["ref"] == params["base"][0]]
        respond(page(values))
    if route in (prefix + "/issues", prefix + "/pulls") and method == "POST":
        is_pr = route.endswith("pulls")
        key = "prs" if is_pr else "issues"
        number = max([int(n) for n in [*state["prs"], *state["issues"]]], default=0) + 1
        value = {"id": 1000 + number, "node_id": "NODE_" + str(number), "number": number, "html_url": "https://github.com/example-owner/example-project/" + ("pull/" if is_pr else "issues/") + str(number), "title": payload["title"], "body": payload["body"], "state": "open", "state_reason": None, "labels": [{"name": n} for n in payload.get("labels", [])], "assignees": [{"login": n} for n in payload.get("assignees", [])], "user": actor}
        value["url"] = "https://api.github.com/" + prefix + ("/pulls/" if is_pr else "/issues/") + str(number)
        if is_pr:
            value["issue_url"] = "https://api.github.com/" + prefix + "/issues/" + str(number)
            value.update(draft=payload["draft"], head={"sha": state["head"], "ref": payload["head"].split(":", 1)[1], "repo": {"full_name": "example-owner/example-project"}}, base={"sha": state["base"], "ref": payload["base"], "repo": {"full_name": "example-owner/example-project"}}, merged=False, merge_commit_sha=None, requested_reviewers=[], requested_teams=[], commits=2, changed_files=1)
            value["head"]["repo"]["full_name"] = payload["head"].split(":", 1)[0] + "/" + payload["head_repo"]
        state[key][str(number)] = value
        respond(value, 201)
    for kind, records in (("issues", state["issues"]), ("pulls", state["prs"])):
        part = route.removeprefix(prefix + "/" + kind + "/")
        if route.startswith(prefix + "/" + kind + "/") and part.isdigit():
            value = records.get(part) or (state["prs"].get(part) if kind == "issues" else None)
            if value is None:
                respond({"message": "Not found"}, 404)
            if method == "PATCH":
                for field, item in payload.items():
                    if field in ("labels", "assignees"):
                        value[field] = [{"name" if field == "labels" else "login": n} for n in item]
                    elif field == "base":
                        value["base"]["ref"] = item
                    else:
                        value[field] = item
            respond(issue_record(value) if kind == "issues" else value)
    for kind, values, read_kind in (("issues", state["issue_comments"], "issues"), ("pulls", state["review_comments"], "pulls")):
        if route.startswith(prefix + "/" + kind + "/comments/"):
            value = next((v for v in values if str(v["id"]) == route.split("/")[-1]), None)
            respond(value or {"message": "Not found"}, 200 if value else 404)
        pieces = route.removeprefix(prefix + "/" + kind + "/").split("/")
        if route.startswith(prefix + "/" + kind + "/") and len(pieces) >= 2 and pieces[0].isdigit() and pieces[1] == "comments":
            number = int(pieces[0])
            if method == "GET":
                respond(page([v for v in values if v["_number"] == number]))
            value = {"id": 5000 + len(values), "body": payload["body"], "user": actor, "_number": number, "html_url": "https://github.com/example-owner/example-project/pull/" + str(number) + "#comment", "pull_request_url": "https://api.github.com/" + prefix + "/pulls/" + str(number)}
            value["issue_url"] = "https://api.github.com/" + prefix + "/issues/" + str(number)
            if len(pieces) == 4 and pieces[-1] == "replies":
                value["in_reply_to_id"] = int(pieces[2])
            else:
                value.update(payload)
            values.append(value)
            respond(value, 201)
    pieces = route.removeprefix(prefix + "/pulls/").split("/")
    if route.startswith(prefix + "/pulls/") and pieces[0].isdigit() and len(pieces) > 1:
        number, resource = int(pieces[0]), pieces[1]
        pr = state["prs"][str(number)]
        if resource == "reviews":
            if method == "GET":
                values = [v for v in state["reviews"] if v["_number"] == number]
                if len(pieces) == 3:
                    respond(next(v for v in values if v["id"] == int(pieces[2])))
                respond(page(values))
            value = {"id": 6000 + len(state["reviews"]), "body": payload["body"], "state": {"COMMENT": "COMMENTED", "APPROVE": "APPROVED", "REQUEST_CHANGES": "CHANGES_REQUESTED"}[payload["event"]], "commit_id": payload["commit_id"], "user": actor, "_number": number, "html_url": pr["html_url"] + "#review"}
            value["pull_request_url"] = "https://api.github.com/" + prefix + "/pulls/" + str(number)
            state["reviews"].append(value)
            respond(value)
        if resource == "files":
            respond(page(state["files"]))
        if resource == "commits":
            respond(page([{"sha": value} for value in state["commits"]]))
        if resource == "requested_reviewers":
            if method != "GET":
                for key, field, name in (("requested_reviewers", "reviewers", "login"), ("requested_teams", "team_reviewers", "slug")):
                    existing = {v[name] for v in pr[key]}
                    updated = existing | set(payload[field]) if method == "POST" else existing - set(payload[field])
                    pr[key] = [{name: n} for n in sorted(updated)]
            respond({"users": pr["requested_reviewers"], "teams": pr["requested_teams"]})
        if resource == "merge-async":
            if method == "GET":
                if state.get("async_still_pending"):
                    respond({"status": "pending", "details": {"uuid": "merge-request-1"}})
                pr.update(merged=True, state="closed", merge_commit_sha=state["merge_sha"])
                respond({"status": "merged", "details": {"sha": state["merge_sha"]}})
            if payload["sha"] != pr["head"]["sha"]:
                respond({"message": "Head moved"}, 409)
            if state.get("async_pending"):
                respond({"status": "pending", "details": {"uuid": "merge-request-1"}}, 202)
            pr.update(merged=True, state="closed", merge_commit_sha=state["merge_sha"])
            respond({"status": "merged", "details": {"sha": state["merge_sha"]}})
    if route.startswith(prefix + "/issues/") and route.endswith("/labels") and method == "PUT":
        number = route.split("/")[-2]
        value = state["prs"].get(number) or state["issues"][number]
        value["labels"] = [{"name": n} for n in payload["labels"]]
        respond(value["labels"])
    if route.startswith(prefix + "/branches/"):
        if route.endswith("/protection"):
            respond(state.get("protection", {}))
        name = route.split("/branches/", 1)[1]
        respond({"name": name, "protected": state.get("protected", False), "commit": {"sha": state["base"] if name in ("main", "release") else state["head"]}})
    if route.startswith(prefix + "/git/commits/"):
        respond({"sha": state["merge_sha"], "parents": [{"sha": state.get("integrated_base", state["base"])}, {"sha": state["head"]}]})
    if route.startswith(prefix + "/rules/branches/"):
        respond(state.get("rules", []))
    if route.startswith(prefix + "/commits/"):
        if route.endswith("/check-runs"):
            respond({"check_runs": page(state["checks"]), "total_count": len(state["checks"])})
        if route.endswith("/statuses"):
            respond(page(state["statuses"]))
        respond({"sha": state["base"] if route.endswith("/main") else state["head"]})
    if route.startswith(prefix + "/compare/"):
        if state.get("comparisons"):
            respond(state["comparisons"][route.split("/")[-1]])
        original = route.split("/")[-1].split("...")[0]
        respond({"status": "diverged" if state.get("missing_commit") == original else "ahead", "merge_base_commit": {"sha": original}})
    if route.startswith(prefix + "/contents/"):
        path = route.split("/contents/", 1)[1]
        if state.get("tracked_files") is not None and path not in state["tracked_files"]:
            respond({"message": "Not found"}, 404)
        respond({"type": "file", "path": path})
    raise RuntimeError("Unmodeled fixture request: " + method + " " + route)


if __name__ == "__main__":
    main()
