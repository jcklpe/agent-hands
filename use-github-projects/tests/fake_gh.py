"""Stateful fixed-route GraphQL double for Projects CLI tests."""
import copy
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlsplit

path = Path(os.environ["PROJECT_TEST_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
method = args[args.index("--method") + 1]
route = next(v for v in args if v in ("user", "graphql") or v.startswith(("repos/", "users/")))
payload = json.load(sys.stdin) if "--input" in args else None
state["calls"].append({"method": method, "route": route, "payload": payload})


def respond(value, status=200, malformed=False):
    path.write_text(json.dumps(state))
    print("HTTP/2 " + str(status) + "\ncontent-type: application/json\n\n" + ('{"incomplete":' if malformed else json.dumps(value)))
    raise SystemExit(0 if status < 400 else 1)


if route == "user":
    respond(state["actor"])
if route.startswith("users/"):
    respond(state["owners"].get(route.split("/")[-1], {"message": "not found"}))
if route == "repos/example-owner/example-project":
    respond(state["repository"])
if "/issues/" in route or "/pulls/" in route:
    if state.get("issue_denied"):
        respond({"message": "denied"}, 403)
    number = int(route.split("/")[-1])
    is_pr = "/pulls/" in route
    item = {"number": number, "id": 100 + number, "node_id": state.get("issue_node", "PR_" if is_pr else "ISSUE_") + str(number) if "issue_node" not in state else state["issue_node"], "html_url": "https://github.com/example-owner/example-project/" + ("pull/" if is_pr else "issues/") + str(number)}
    if is_pr:
        item["head"] = {"sha": "a" * 40}
    respond(item)
assert route == "graphql", route
query, variables = payload["query"], payload.get("variables", {})
shape = re.sub(r'"(?:[^"\\]|\\.)*"', '""', query)
assert shape.count("{") == shape.count("}"), query
is_mutation = query.startswith("mutation")
if state.get("graphql_errors"):
    respond({"data": {}, "errors": state["graphql_errors"]})
if state.get("malformed_errors"):
    respond({"data": {}, "errors": False})
if state.get("deny_readback") and state["mutations"] and not is_mutation:
    respond({"message": "readback denied"}, 403)


def connection(values, family):
    if state.get("malformed_family") == family:
        return {"nodes": None, "pageInfo": {"hasNextPage": False, "endCursor": None}}
    size = state.get("page_size", 100)
    offset = int(variables.get("after") or 0)
    selected = copy.deepcopy(values[offset:offset + size])
    more = offset + size < len(values) or state.get("incomplete_family") == family
    cursor = str(offset + size) if more else None
    if state.get("repeated_cursor"):
        more, cursor = True, "0"
    return {"nodes": selected, "pageInfo": {"hasNextPage": more, "endCursor": cursor}}


if not is_mutation:
    if "projectsV2(first:" in query:
        login = variables["owner"]
        selected_owner = state["owners"][login]
        projects = [v["meta"] for v in state["projects"].values() if v["meta"]["owner"]["id"] == selected_owner["node_id"]]
        kind = "organization" if selected_owner["type"] == "Organization" else "user"
        respond({"data": {kind: {"id": selected_owner["node_id"], "projectsV2": connection(projects, "projects")}}})
    if "projectV2(number:" in query:
        owner_record = state["owners"][variables["owner"]]
        kind = "organization" if owner_record["type"] == "Organization" else "user"
        matches = [v["meta"] for v in state["projects"].values() if v["meta"]["number"] == variables["number"] and v["meta"]["owner"]["id"] == owner_record["node_id"]]
        respond({"data": {kind: {"projectV2": matches[0] if len(matches) == 1 else None}}})
    if "configuration{visibleFields" in query:
        if state.get("visible_error"):
            respond({"message": "synthetic unsupported configuration"}, 500)
        matches = [(p, v) for p in state["projects"].values() for v in p["views"] if v["id"] == variables["id"]]
        p, view = matches[0]
        visible = [next(f for f in p["fields"] if f["id"] == identifier) for identifier in view["visible"]]
        respond({"data": {"node": {"id": view["id"], "project": view["project"], "configuration": {"visibleFields": connection(visible, "visible")}}}})
    p = state["projects"].get(variables["id"])
    if not p:
        respond({"data": {"node": None}})
    family = next((f for f in ("fields", "views", "workflows", "repositories", "items") if f + "(first:" in query), None)
    if family:
        identifier = state.get("collection_parent", p["meta"]["id"])
        respond({"data": {"node": {"id": identifier, family: connection(p[family], family)}}})
    state["project_reads"] = state.get("project_reads", 0) + 1
    if state.get("race_at_read") == state["project_reads"]:
        p["meta"]["updatedAt"] = "concurrent-change"
        p["fields"][0]["options"][0]["name"] = "Concurrent stage"
    respond({"data": {"node": p["meta"]}})

if state.get("refuse_mutation"):
    respond({"message": "mutation denied"}, 403)
state["mutations"].append(payload)
inputs = variables["input"]
target = None
if "createProjectV2(" in query or "copyProjectV2(" in query:
    owner_record = next(v for v in state["owners"].values() if v["node_id"] == inputs["ownerId"])
    number = len(state["projects"]) + 1
    identifier = "PROJECT_" + str(number)
    if "projectId" in inputs:
        target = copy.deepcopy(state["projects"][inputs["projectId"]])
        for i, field in enumerate(target["fields"]):
            field["id"] = identifier + "_FIELD_" + str(i)
            for j, option in enumerate(field.get("options", [])):
                option["id"] = identifier + "_OPTION_" + str(j)
        for i, view in enumerate(target["views"]):
            view.update(id=identifier + "_VIEW_" + str(i), project={"id": identifier}, visible=[])
        target["items"], target["repositories"] = [], []
    else:
        target = {"fields": [], "views": [], "items": [], "workflows": [], "repositories": []}
    target["meta"] = {"id": identifier, "number": number, "title": inputs["title"], "url": "https://github.com/" + ("users" if owner_record["type"] == "User" else "orgs") + "/" + owner_record["login"] + "/projects/" + str(number), "owner": {"id": owner_record["node_id"], "login": owner_record["login"]}, "closed": False, "public": False, "updatedAt": "created", "viewerCanUpdate": True}
    if inputs.get("repositoryId"):
        target["repositories"].append({"id": inputs["repositoryId"], "nameWithOwner": state["repository"]["full_name"]})
    state["projects"][identifier] = target
    resource_id = identifier
elif "linkProjectV2ToRepository" in query:
    target = state["projects"][inputs["projectId"]]
    resource_id = inputs["repositoryId"]
    target["repositories"].append({"id": resource_id, "nameWithOwner": state["repository"]["full_name"]})
elif "ProjectV2Field(" in query:
    if "fieldId" in inputs:
        target = next(p for p in state["projects"].values() if any(f["id"] == inputs["fieldId"] for f in p["fields"]))
        field = next(f for f in target["fields"] if f["id"] == inputs["fieldId"])
    else:
        target = state["projects"][inputs["projectId"]]
        field = {"id": "FIELD_NEW_" + str(len(target["fields"])), "dataType": inputs["dataType"]}
        target["fields"].append(field)
    field["name"] = inputs["name"]
    if "singleSelectOptions" in inputs:
        field["options"] = [{**value, "id": value.get("id", "OPTION_NEW_" + str(i))} for i, value in enumerate(inputs["singleSelectOptions"])]
        for item in target["items"]:
            value = item.get("fieldValueByName") or {}
            if value.get("field", {}).get("id") == field["id"]:
                selected = next((v for v in field["options"] if v["id"] == value.get("optionId")), None)
                if selected:
                    value["name"] = selected["name"]
    if state.get("swap_option_ids"):
        a, b = field["options"][:2]
        a["id"], b["id"] = b["id"], a["id"]
    if state.get("drop_unrelated_field"):
        target["fields"] = [field]
    resource_id = field["id"]
elif "ProjectV2View(" in query:
    if "viewId" in inputs:
        target = next(p for p in state["projects"].values() if any(v["id"] == inputs["viewId"] for v in p["views"]))
        view = next(v for v in target["views"] if v["id"] == inputs["viewId"])
    else:
        target = state["projects"][inputs["projectId"]]
        view = {"id": "VIEW_NEW_" + str(len(target["views"])), "number": len(target["views"]) + 1, "project": {"id": inputs["projectId"]}, "filter": "", "updatedAt": "created", "visible": []}
        target["views"].append(view)
    for key in ("name", "layout", "filter"):
        if key in inputs:
            view[key] = inputs[key]
    if "configuration" in inputs:
        view["visible"] = inputs["configuration"]["visibleFieldIds"]
    resource_id = view["id"]
elif "addProjectV2ItemById" in query:
    target = state["projects"][inputs["projectId"]]
    content_id = inputs["contentId"]
    item = {"id": "ITEM_NEW_" + str(len(target["items"])), "content": {"id": content_id}, "fieldValueByName": None}
    target["items"].append(item)
    resource_id = item["id"]
elif "updateProjectV2ItemFieldValue" in query:
    target = state["projects"][inputs["projectId"]]
    item = next(v for v in target["items"] if v["id"] == inputs["itemId"])
    field = next(v for v in target["fields"] if v["id"] == inputs["fieldId"])
    option = next(v for v in field["options"] if v["id"] == inputs["value"]["singleSelectOptionId"])
    if not state.get("ignore_status_write"):
        item["fieldValueByName"] = {"optionId": option["id"], "name": option["name"], "field": {"id": field["id"]}}
    resource_id = item["id"]
else:
    raise RuntimeError("Unmodeled mutation: " + query)
result = {"data": {"result": {"resource": {"id": state.get("wrong_result_id", resource_id)}}}}
if "mutation_result" in state:
    result = state["mutation_result"]
respond(result, malformed=state.get("lose_response", False))
