#!/usr/bin/env python3
"""Bounded Projects inspection, provisioning and independently verified item changes."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-github/scripts"))
from collaboration import Context, Refusal, Step, TransportError, add_common, digest, execute, positive, recover, run

META = "id number title url closed public updatedAt viewerCanUpdate owner{...on Organization{id login} ...on User{id login}}"
FIELD = "__typename ...on ProjectV2FieldCommon{id name dataType} ...on ProjectV2SingleSelectField{options{id name color description}}"
VIEW = "id number name layout filter updatedAt project{id}"
ITEM = "id content{__typename ...on Issue{id number repository{nameWithOwner}} ...on PullRequest{id number repository{nameWithOwner}} ...on DraftIssue{id}} fieldValueByName(name:$field){__typename ...on ProjectV2ItemFieldSingleSelectValue{optionId name field{...on ProjectV2SingleSelectField{id}}}}"
FRAGMENTS = {"fields": FIELD, "views": VIEW, "workflows": "id number name enabled", "repositories": "id nameWithOwner", "items": ITEM}
COLORS = {"GRAY", "BLUE", "GREEN", "YELLOW", "ORANGE", "RED", "PINK", "PURPLE"}
LAYOUTS = {"table": "TABLE_LAYOUT", "board": "BOARD_LAYOUT", "roadmap": "ROADMAP_LAYOUT"}
MUTATIONS = {
    "create-project": ("CreateProjectV2Input", "createProjectV2", "projectV2", "id"),
    "copy-project": ("CopyProjectV2Input", "copyProjectV2", "projectV2", "id"),
    "link-repository": ("LinkProjectV2ToRepositoryInput", "linkProjectV2ToRepository", "repository", "id"),
    "create-field": ("CreateProjectV2FieldInput", "createProjectV2Field", "projectV2Field", "...on ProjectV2FieldCommon{id}"),
    "update-field": ("UpdateProjectV2FieldInput", "updateProjectV2Field", "projectV2Field", "...on ProjectV2FieldCommon{id}"),
    "create-view": ("CreateProjectV2ViewInput", "createProjectV2View", "projectV2View", "id"),
    "edit-view": ("UpdateProjectV2ViewInput", "updateProjectV2View", "projectV2View", "id"),
    "add-item": ("AddProjectV2ItemByIdInput", "addProjectV2ItemById", "item", "id"),
    "move-card": ("UpdateProjectV2ItemFieldValueInput", "updateProjectV2ItemFieldValue", "projectV2Item", "id"),
}


def node_id(value):
    if not isinstance(value, str) or value in ("", "null") or not re.fullmatch(r"[A-Za-z0-9_+/=-]+", value):
        raise Refusal("Invalid GitHub resource identifier")
    return value


def text(value, label, limit=4096):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Refusal("Supply a nonempty bounded " + label)
    return value


def load_json(path):
    source = Path(path)
    if source.stat().st_size > 65536:
        raise Refusal("Selected JSON input exceeds 64 KiB")
    return json.loads(source.read_text(encoding="utf-8"))


def alias_selection(args):
    if "/" in args.repo:
        return
    config = Path(os.environ.get("GITHUB_CONFIG_DIR", str(Path(__file__).resolve().parents[2] / "setup-github")))
    selected = Path(os.environ.get("GITHUB_REPOS_PATH", "github-repos.json"))
    entries = json.loads((selected if selected.is_absolute() else config / selected).read_text())["repos"]
    matches = [entry for entry in entries if entry.get("alias") == args.repo]
    if len(matches) != 1:
        raise Refusal("Repository alias is missing or ambiguous")
    entry = matches[0]
    args.owner = args.owner or entry.get("project_owner", entry["owner"])
    if not args.project_id and not args.project_number and entry.get("projects"):
        args.project_number = positive(entry["projects"][0]["number"])


def owner(ctx, login):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", login or ""):
        raise Refusal("Select an explicit project owner login")
    value = ctx.client.get("users/" + login)
    if value.get("login", "").lower() != login.lower() or value.get("type") not in ("User", "Organization"):
        raise Refusal("Cannot independently resolve the project owner")
    return {"id": node_id(value.get("node_id")), "login": value["login"], "kind": "user" if value["type"] == "User" else "organization"}


def selected_project(ctx, selected_owner=None, project_id=None):
    selected_owner = selected_owner or owner(ctx, ctx.args.owner or ctx.repo.split("/")[0])
    identifier = project_id or ctx.args.project_id
    if identifier:
        data = ctx.client.graphql("query($id:ID!){node(id:$id){...on ProjectV2{" + META + "}}}", id=node_id(identifier))
        value = data.get("node")
    elif ctx.args.project_number:
        kind = selected_owner["kind"]
        data = ctx.client.graphql("query($owner:String!,$number:Int!){" + kind + "(login:$owner){projectV2(number:$number){" + META + "}}}", owner=selected_owner["login"], number=positive(ctx.args.project_number))
        value = (data.get(kind) or {}).get("projectV2")
    else:
        raise Refusal("Select --project-id or --project-number; --project selects the local checkout")
    if not isinstance(value, dict) or not value.get("id") or not isinstance(value.get("number"), int):
        raise Refusal("Selected project is unavailable or malformed")
    node_id(value["id"])
    if identifier and value["id"] != identifier:
        raise Refusal("Project identity mismatch")
    if value.get("owner", {}).get("id") != selected_owner["id"] or value["owner"].get("login", "").lower() != selected_owner["login"].lower():
        raise Refusal("Project does not belong to the selected owner")
    if ctx.args.project_number and value["number"] != ctx.args.project_number:
        raise Refusal("Project number and identifier disagree")
    expected = f"https://{ctx.host}/{'users' if selected_owner['kind'] == 'user' else 'orgs'}/{selected_owner['login']}/projects/{value['number']}"
    if value.get("url", "").lower() != expected.lower():
        raise Refusal("Project host/owner URL mismatch")
    if not isinstance(value.get("public"), bool) or not isinstance(value.get("closed"), bool) or not isinstance(value.get("viewerCanUpdate"), bool):
        raise Refusal("Project visibility/state/permission evidence is incomplete")
    return value


def collection(ctx, identifier, family, owner_record=None):
    if family == "projects":
        kind = owner_record["kind"]
        query = "query($owner:String!,$after:String){" + kind + "(login:$owner){id projectsV2(first:100,after:$after){nodes{" + META + "} pageInfo{hasNextPage endCursor}}}}"
        variables = {"owner": owner_record["login"]}
    else:
        extra = ",$field:String!" if family == "items" else ""
        query = "query($id:ID!,$after:String" + extra + "){node(id:$id){...on ProjectV2{id " + family + "(first:100,after:$after){nodes{" + FRAGMENTS[family] + "} pageInfo{hasNextPage endCursor}}}}}"
        variables = {"id": identifier}
        if family == "items":
            variables["field"] = ctx.args.field_name
    values, seen, after, complete = [], set(), None, False
    for _ in range(ctx.args.page_limit):
        data = ctx.client.graphql(query, **variables, after=after)
        parent = data.get(kind if family == "projects" else "node") or {}
        if parent.get("id") != (owner_record["id"] if family == "projects" else identifier):
            raise Refusal("Collection parent identity mismatch")
        connection = parent.get("projectsV2" if family == "projects" else family) or {}
        nodes, page = connection.get("nodes"), connection.get("pageInfo") or {}
        if not isinstance(nodes, list) or len(nodes) > 100 or not all(isinstance(v, dict) and v.get("id") for v in nodes) or not isinstance(page.get("hasNextPage"), bool):
            raise Refusal("Malformed project collection", "failed")
        for value in nodes:
            node_id(value["id"])
            if family == "views" and value.get("project", {}).get("id") != identifier:
                raise Refusal("View collection contains a foreign project resource")
        if len({v["id"] for v in values + nodes}) != len(values) + len(nodes):
            raise Refusal("Duplicate resource IDs in paginated evidence", "failed")
        remaining = ctx.args.item_limit - len(values)
        values.extend(nodes[:remaining])
        if not page["hasNextPage"] and len(nodes) <= remaining:
            complete = True
            break
        after = page.get("endCursor")
        if len(values) >= ctx.args.item_limit:
            break
        if not after or after in seen:
            raise Refusal("Missing or repeated pagination cursor", "failed")
        seen.add(after)
    return values, {"complete": complete, "observed": len(values), "page_limit": ctx.args.page_limit, "item_limit": ctx.args.item_limit}


def required(ctx, p, family):
    values, coverage = collection(ctx, p["id"], family)
    if not coverage["complete"]:
        raise Refusal("Complete " + family + " evidence is required for this operation", "unsupported")
    return values


def visible_fields(ctx, p, view_id):
    query = "query($id:ID!,$after:String){node(id:$id){...on ProjectV2View{id project{id} configuration{visibleFields(first:100,after:$after){nodes{" + FIELD + "} pageInfo{hasNextPage endCursor}}}}}}"
    values, seen, after = [], set(), None
    for _ in range(ctx.args.page_limit):
        data = ctx.client.graphql(query, id=view_id, after=after)
        view = data.get("node") or {}
        if view.get("id") != view_id or view.get("project", {}).get("id") != p["id"]:
            raise Refusal("View configuration parent mismatch")
        connection = (view.get("configuration") or {}).get("visibleFields") or {}
        nodes, page = connection.get("nodes"), connection.get("pageInfo") or {}
        if not isinstance(nodes, list) or not all(isinstance(v, dict) and v.get("id") for v in nodes) or not isinstance(page.get("hasNextPage"), bool):
            raise Refusal("Malformed visible-field configuration", "failed")
        for value in nodes:
            node_id(value["id"])
        if len({v["id"] for v in values + nodes}) != len(values) + len(nodes):
            raise Refusal("Duplicate visible field IDs", "failed")
        if len(values) + len(nodes) > ctx.args.item_limit:
            raise Refusal("Visible-field configuration is incomplete", "unsupported")
        values.extend(nodes)
        if not page["hasNextPage"]:
            return [v["id"] for v in values]
        after = page.get("endCursor")
        if not after or after in seen:
            raise Refusal("Invalid visible-field pagination", "failed")
        seen.add(after)
    raise Refusal("Visible-field configuration is incomplete", "unsupported")


def one(values, key, value, label):
    matches = [v for v in values if v.get(key) == value]
    if len(matches) != 1:
        raise Refusal(label + " must identify exactly one resource")
    return matches[0]


def field_shape(value):
    result = {"name": value.get("name"), "dataType": value.get("dataType")}
    text(result["name"], "observed field name", 256)
    text(result["dataType"], "observed field type", 256)
    if result["dataType"] == "SINGLE_SELECT":
        options = value.get("options")
        if not isinstance(options, list) or not options or len({v.get("id") for v in options}) != len(options) or len({v.get("name") for v in options}) != len(options):
            raise Refusal("Single-select options are missing or ambiguous")
        for option in options:
            node_id(option["id"])
            text(option["name"], "observed option name", 256)
            if option.get("color") not in COLORS or not isinstance(option.get("description"), str):
                raise Refusal("Malformed observed option metadata")
        result["options"] = [{k: v[k] for k in ("name", "color", "description")} for v in options]
    return result


def option_input(path):
    values = load_json(path)
    if not isinstance(values, list) or not 1 <= len(values) <= 50:
        raise Refusal("Supply 1–50 selected options in a JSON array")
    result = []
    for value in values:
        if not isinstance(value, dict) or not set(value) <= {"id", "name", "color", "description"}:
            raise Refusal("Options accept an existing option ID, name, color and description only")
        name = text(value.get("name"), "option name", 256)
        if "color" in value and value["color"] not in COLORS or "description" in value and (not isinstance(value["description"], str) or len(value["description"]) > 1024):
            raise Refusal("Invalid option color or description")
        result.append({**value, "name": name})
        if "id" in value:
            node_id(value["id"])
    if len({v["name"] for v in result}) != len(result):
        raise Refusal("Selected option names must be unique")
    return result


def view_shape(value, include_visible=False):
    result = {key: value.get(key) for key in ("name", "layout", "filter")}
    if result["filter"] is None:
        result["filter"] = ""
    if include_visible:
        result["visible"] = value["visible"]
    return result


def copy_shape(ctx, p):
    fields = required(ctx, p, "fields")
    views = required(ctx, p, "views")
    return {"fields": sorted((field_shape(v) for v in fields), key=lambda v: str(v["name"])), "views": sorted((view_shape(v) for v in views), key=lambda v: str(v["name"]))}


def mutation_step(ctx, operation, inputs, spec):
    input_type, mutation, resource, shape = MUTATIONS[operation]
    query = "mutation($input:" + input_type + "!){result:" + mutation + "(input:$input){resource:" + resource + "{" + shape + "}}}"
    def identifiers(response):
        value = (response.get("data") or {}).get("result") or {}
        return {"node_id": node_id((value.get("resource") or {}).get("id"))}
    def verify(response):
        identifier = identifiers(response)["node_id"]
        return verify_operation(ctx, {**spec, "result_id": identifier})
    return Step(operation, "POST", "graphql", {"query": query, "variables": {"input": inputs}}, spec, verify, identifiers)


def prepare(ctx):
    args, steps = ctx.args, []
    selected_owner = owner(ctx, args.owner or ctx.repo.split("/")[0])
    effects = ["Project subscribers may be notified; native project workflows may cause further effects"]
    baseline = {"owner": selected_owner}
    if args.command in ("create-project", "copy-project"):
        title = text(args.title, "project title", 256)
        destination = owner(ctx, args.new_owner) if args.command == "copy-project" and args.new_owner else selected_owner
        projects, coverage = collection(ctx, None, "projects", destination)
        if not coverage["complete"]:
            raise Refusal("Destination project coverage is incomplete", "unsupported")
        if any(v["title"] == title for v in projects):
            raise Refusal("Project title already exists; select its exact ID/number instead of creating a duplicate")
        baseline.update(destination=destination, known_project_ids=[v["id"] for v in projects])
        spec = {"kind": "project-operation", "action": args.command, "owner": destination, "before_ids": [v["id"] for v in projects], "expected": digest({"title": title, "owner": destination["id"], "closed": False})}
        inputs = {"ownerId": destination["id"], "title": title}
        if args.command == "copy-project":
            p = selected_project(ctx, selected_owner)
            snapshot = copy_shape(ctx, p)
            workflows = required(ctx, p, "workflows")
            baseline.update(source=p, source_schema=snapshot, native_workflows=workflows)
            inputs.update(projectId=p["id"], includeDraftIssues=False)
            spec.update(source_id=p["id"], source_owner=selected_owner, copy_digest=digest(snapshot))
            effects += ["Copies views, custom fields and native workflow configuration; excludes draft issues, original items, collaborators and repository/team links", "Hidden native settings and view grouping/sorting require manual verification after copy"]
        elif args.link_repository:
            inputs["repositoryId"] = node_id(ctx.repository.get("node_id"))
            spec["repository_id"] = inputs["repositoryId"]
        effects += ["Creates an open project using GitHub's default visibility; inspect the returned visibility before adding content"]
        steps.append(mutation_step(ctx, args.command, inputs, spec))
        return ctx.plan(baseline, steps, effects), steps
    p = selected_project(ctx, selected_owner)
    if p["viewerCanUpdate"] is not True or p["closed"]:
        raise Refusal("Selected project must be open and writable")
    baseline["project"] = p
    spec = {"kind": "project-operation", "action": args.command, "owner": selected_owner, "project_id": p["id"]}
    if args.command == "link-repository":
        repos = required(ctx, p, "repositories")
        identifier = node_id(ctx.repository.get("node_id"))
        baseline["repository_ids"] = [v["id"] for v in repos]
        if identifier not in baseline["repository_ids"]:
            spec.update(repository_id=identifier, preserve_ids=baseline["repository_ids"])
            steps.append(mutation_step(ctx, args.command, {"projectId": p["id"], "repositoryId": identifier}, spec))
    elif args.command == "ensure-field":
        name = text(args.name, "field name", 256)
        fields = required(ctx, p, "fields")
        matches = [v for v in fields if v.get("name") == name]
        if len(matches) > 1:
            raise Refusal("Field name is ambiguous")
        current = matches[0] if matches else None
        baseline["fields"] = fields
        desired = {"name": name, "dataType": args.data_type}
        inputs = {"projectId": p["id"], "name": name, "dataType": args.data_type}
        if current and current.get("dataType") != args.data_type:
            raise Refusal("An existing field has a different type; no replacement is authorized")
        preserve = {}
        if args.data_type == "SINGLE_SELECT":
            if not args.options_file:
                raise Refusal("Single-select provisioning requires --options-file")
            options = option_input(args.options_file)
            existing = current.get("options", []) if current else []
            if current:
                field_shape(current)
            by_name = {v["name"]: v for v in existing}
            by_id = {v["id"]: v for v in existing}
            merged, selected_ids = [], set()
            for value in options:
                prior = by_id.get(value["id"]) if "id" in value else by_name.get(value["name"])
                if "id" in value and not prior:
                    raise Refusal("Renaming requires an option ID from the selected field")
                if prior and prior["id"] in selected_ids:
                    raise Refusal("The same existing option was selected twice")
                if prior:
                    selected_ids.add(prior["id"])
                merged.append({**({k: prior[k] for k in ("id", "name", "color", "description")} if prior else {"color": "GRAY", "description": ""}), **value})
            merged += [{k: v[k] for k in ("id", "name", "color", "description")} for v in existing if v["id"] not in selected_ids]
            if len(merged) > 50 or len({v["name"] for v in merged}) != len(merged):
                raise Refusal("Merged options exceed the 50-option bound or contain colliding names")
            desired["options"] = [{k: v[k] for k in ("name", "color", "description")} for v in merged]
            preserve = {node_id(v["id"]): digest({k: v[k] for k in ("name", "color", "description")}) for v in merged if "id" in v}
            inputs["singleSelectOptions"] = merged
            effects += ["Orders the selected options first and retains unrelated options and all existing option IDs"]
        elif args.options_file:
            raise Refusal("Only single-select fields accept options")
        if current and field_shape(current) == desired:
            return ctx.plan(baseline, [], effects), []
        spec.update(expected=digest(desired), before_ids=[v["id"] for v in fields], preserve_options=preserve, preserve_others={v["id"]: digest(field_shape(v)) for v in fields if not current or v["id"] != current["id"]})
        if current:
            spec["resource_id"] = current["id"]
            inputs.pop("projectId"); inputs.pop("dataType"); inputs["fieldId"] = current["id"]
        steps.append(mutation_step(ctx, "update-field" if current else "create-field", inputs, spec))
    elif args.command in ("create-view", "edit-view"):
        views = required(ctx, p, "views")
        baseline["views"] = views
        current = one(views, "id", node_id(args.view_id), "View ID") if args.command == "edit-view" else None
        inputs = {"viewId": current["id"]} if current else {"projectId": p["id"]}
        if args.name is not None:
            inputs["name"] = text(args.name, "view name", 256)
            collisions = [v for v in views if v["name"] == args.name and (not current or v["id"] != current["id"])]
            if collisions:
                if args.command == "create-view" and len(collisions) == 1 and collisions[0]["layout"] == LAYOUTS[args.layout]:
                    if not args.visible_field:
                        return ctx.plan(baseline, [], effects), []
                    configured = visible_fields(ctx, p, collisions[0]["id"])
                    if configured == args.visible_field + [v for v in configured if v not in args.visible_field]:
                        return ctx.plan(baseline, [], effects), []
                raise Refusal("View name already exists or is ambiguous; select the exact view ID")
        if args.layout:
            inputs["layout"] = LAYOUTS[args.layout]
        if args.filter is not None:
            if len(args.filter) > 4096:
                raise Refusal("View filter exceeds 4096 characters")
            inputs["filter"] = args.filter
        desired = view_shape(current) if current else {"name": args.name, "layout": LAYOUTS[args.layout], "filter": ""}
        desired.update({k: v for k, v in inputs.items() if k in ("name", "layout", "filter")})
        if args.visible_field:
            fields = required(ctx, p, "fields")
            selected = [node_id(v) for v in args.visible_field]
            if len(set(selected)) != len(selected) or not set(selected) <= {v["id"] for v in fields}:
                raise Refusal("Visible fields must identify unique fields of the selected project")
            if current:
                existing = visible_fields(ctx, p, current["id"])
            else:
                if not views:
                    raise Refusal("Create a basic view first, then verify configuration reads before selecting visible fields", "unsupported")
                visible_fields(ctx, p, views[0]["id"])
                existing = []
            baseline["visible_fields"] = existing
            desired["visible"] = selected + [v for v in existing if v not in selected]
            inputs["configuration"] = {"visibleFieldIds": desired["visible"]}
        if current and len(inputs) == 1:
            raise Refusal("Select a view property to change")
        if current and view_shape({**current, "visible": baseline.get("visible_fields")}, bool(args.visible_field)) == desired:
            return ctx.plan(baseline, [], effects), []
        spec.update(expected=digest(desired), before_ids=[v["id"] for v in views], visible=bool(args.visible_field), preserve_others={v["id"]: digest(view_shape(v)) for v in views if not current or v["id"] != current["id"]})
        if current:
            spec["resource_id"] = current["id"]
        effects += ["Unselected view properties and other views remain unchanged; grouping/sorting are manual setup requirements"]
        steps.append(mutation_step(ctx, args.command, inputs, spec))
    elif args.command in ("move-card", "add-item"):
        item = ctx.item(args.issue or args.pr, "issues" if args.issue else "pulls")
        content_id = node_id(item.get("node_id"))
        items = required(ctx, p, "items")
        matches = [v for v in items if (v.get("content") or {}).get("id") == content_id]
        if len(matches) > 1:
            raise Refusal("The selected issue/PR appears more than once on the project")
        baseline["items"] = items
        spec.update(content_id=content_id, before_ids=[v["id"] for v in items])
        if args.command == "add-item":
            if not matches:
                steps.append(mutation_step(ctx, args.command, {"projectId": p["id"], "contentId": content_id}, spec))
        else:
            if not matches:
                raise Refusal("Issue/PR is absent from the selected project; adding it is a separate operation")
            fields = required(ctx, p, "fields")
            field = one(fields, "name", args.field_name, "Status field name")
            if field.get("dataType") != "SINGLE_SELECT":
                raise Refusal("Status changes require a single-select field")
            field_shape(field)
            option = one(field["options"], "name", args.status, "Status option")
            current = matches[0]
            if "fieldValueByName" not in current:
                raise Refusal("The current item status is unreadable")
            state = current["fieldValueByName"]
            if state is not None and (not isinstance(state, dict) or state.get("field", {}).get("id") != field["id"] or not any(v["id"] == state.get("optionId") and v["name"] == state.get("name") for v in field["options"])):
                raise Refusal("Current item status is malformed or does not belong to the selected field")
            baseline["field"] = field
            if state is None or state["optionId"] != option["id"]:
                spec.update(resource_id=current["id"], field_id=field["id"], field_name=args.field_name, option_id=option["id"])
                steps.append(mutation_step(ctx, args.command, {"projectId": p["id"], "itemId": current["id"], "fieldId": field["id"], "value": {"singleSelectOptionId": option["id"]}}, spec))
    else:
        raise Refusal("Unsupported project operation", "unsupported")
    return ctx.plan(baseline, steps, effects), steps


def verify_operation(ctx, spec):
    if spec.get("kind") != "project-operation":
        raise Refusal("This recovery operation belongs to another domain", "unsupported")
    selected_owner = owner(ctx, spec["owner"]["login"])
    if selected_owner != spec["owner"]:
        raise Refusal("Project owner changed during readback", "uncertain")
    resource_id = spec.get("result_id") or getattr(ctx.args, "result_id", None) or spec.get("resource_id")
    action = spec["action"]
    if spec.get("resource_id") and resource_id != spec["resource_id"]:
        raise Refusal("Mutation result identifies a different resource", "uncertain")
    if action in ("ensure-field", "create-view", "add-item") and not spec.get("resource_id") and resource_id in spec["before_ids"]:
        raise Refusal("Creation result identifies a resource present before the operation", "uncertain")
    saved_number = ctx.args.project_number
    ctx.args.project_number = None
    try:
        if action in ("create-project", "copy-project"):
            values, coverage = collection(ctx, None, "projects", selected_owner)
            if not coverage["complete"]:
                raise Refusal("Project recovery coverage is incomplete", "uncertain")
            matches = [v for v in values if v["id"] not in spec["before_ids"] and digest({"title": v["title"], "owner": v["owner"]["id"], "closed": v["closed"]}) == spec["expected"] and (not resource_id or v["id"] == resource_id)]
            if len(matches) != 1:
                raise Refusal("Project creation is ambiguous or not independently verified", "uncertain")
            p = selected_project(ctx, selected_owner, matches[0]["id"])
            if digest({"title": p["title"], "owner": p["owner"]["id"], "closed": p["closed"]}) != spec["expected"]:
                raise Refusal("Created project state differs from the recorded action", "uncertain")
            if action == "copy-project":
                if digest(copy_shape(ctx, p)) != spec["copy_digest"]:
                    raise Refusal("Copied field/view evidence differs from the selected source", "uncertain")
                if required(ctx, p, "items") or required(ctx, p, "repositories"):
                    raise Refusal("Copied project unexpectedly contains items or repository links", "uncertain")
            elif spec.get("repository_id") and spec["repository_id"] not in {v["id"] for v in required(ctx, p, "repositories")}:
                raise Refusal("Creation repository link was not independently verified", "uncertain")
            return {**spec, "result_id": p["id"], "project_id": p["id"], "project_number": p["number"], "public": p["public"], "url": p["url"]}
        p = selected_project(ctx, selected_owner, spec["project_id"])
        if action == "link-repository":
            if resource_id and resource_id != spec["repository_id"]:
                raise Refusal("Repository mutation result mismatch", "uncertain")
            identifiers = {v["id"] for v in required(ctx, p, "repositories")}
            if spec["repository_id"] not in identifiers or not set(spec["preserve_ids"]) <= identifiers:
                raise Refusal("Repository link readback failed", "uncertain")
        elif action == "ensure-field":
            fields = required(ctx, p, "fields")
            candidates = [v for v in fields if (v["id"] == resource_id if resource_id else v["id"] not in spec["before_ids"]) and digest(field_shape(v)) == spec["expected"]]
            observed = {v["id"]: digest({k: v[k] for k in ("name", "color", "description")}) for v in candidates[0].get("options", [])} if len(candidates) == 1 else {}
            others = {v["id"]: digest(field_shape(v)) for v in fields}
            if len(candidates) != 1 or any(observed.get(identifier) != shape for identifier, shape in spec["preserve_options"].items()) or any(others.get(identifier) != shape for identifier, shape in spec["preserve_others"].items()):
                raise Refusal("Field shape or preserved option IDs were not independently verified", "uncertain")
            resource_id = candidates[0]["id"]
        elif action in ("create-view", "edit-view"):
            views = required(ctx, p, "views")
            others = {v["id"]: digest(view_shape(v)) for v in views}
            if any(others.get(identifier) != shape for identifier, shape in spec["preserve_others"].items()):
                raise Refusal("An unrelated view changed during the operation", "uncertain")
            candidates = [v for v in views if v["id"] == resource_id] if resource_id else [v for v in views if v["id"] not in spec["before_ids"]]
            matches = []
            for v in candidates:
                if v.get("project", {}).get("id") != p["id"]:
                    raise Refusal("View belongs to another project", "uncertain")
                if spec["visible"]:
                    v["visible"] = visible_fields(ctx, p, v["id"])
                if digest(view_shape(v, spec["visible"])) == spec["expected"]:
                    matches.append(v)
            if len(matches) != 1:
                raise Refusal("View state was not independently verified", "uncertain")
            resource_id = matches[0]["id"]
        elif action in ("add-item", "move-card"):
            original_field = ctx.args.field_name
            ctx.args.field_name = spec.get("field_name", original_field)
            try:
                items = required(ctx, p, "items")
            finally:
                ctx.args.field_name = original_field
            matches = [v for v in items if (v.get("content") or {}).get("id") == spec["content_id"] and (not resource_id or v["id"] == resource_id)]
            if len(matches) != 1:
                raise Refusal("Item membership was not independently verified", "uncertain")
            current = matches[0]
            if action == "add-item" and not spec.get("resource_id") and current["id"] in spec["before_ids"]:
                raise Refusal("Recovery matched an item present before creation", "uncertain")
            if action == "move-card":
                state = current.get("fieldValueByName") or {}
                if state.get("optionId") != spec["option_id"] or state.get("field", {}).get("id") != spec["field_id"]:
                    raise Refusal("Selected status was not independently verified", "uncertain")
            resource_id = current["id"]
        else:
            raise Refusal("Unknown Projects recovery action", "unsupported")
        return {**spec, "result_id": resource_id or spec.get("repository_id"), "url": p["url"]}
    finally:
        ctx.args.project_number = saved_number


def inspect(ctx):
    p = selected_project(ctx)
    families = set(ctx.args.fields.split(","))
    if not families <= {"project", *FRAGMENTS}:
        raise Refusal("Unknown project read family")
    result = {"schema_version": 1, "outcome": "success", "project": p, "coverage": {}, "manual_requirements": ["Native enabled flags do not verify trigger/status settings; inspect and record the actual saved native configuration", "View grouping/sorting and Insights configuration have no supported setter here"]}
    for family in sorted(families - {"project"}):
        try:
            result[family], result["coverage"][family] = collection(ctx, p["id"], family)
        except (TransportError, Refusal) as exc:
            result[family], result["coverage"][family] = [], {"complete": False, "reason": str(exc)}
    after = selected_project(ctx, project_id=p["id"])
    result["coverage"]["revision_stable"] = after == p
    return result


def automation_config(ctx):
    p = selected_project(ctx)
    fields = required(ctx, p, "fields")
    field = one(fields, "name", ctx.args.field_name, "Lifecycle field name")
    if field.get("dataType") != "SINGLE_SELECT":
        raise Refusal("Lifecycle mapping requires a single-select field")
    field_shape(field)
    mapping = load_json(ctx.args.mapping_file)
    names = {"entry": "PW_ENTRY_OPTION_ID", "done": "PW_DONE_OPTION_ID", "reopen": "PW_REOPEN_OPTION_ID", "blocked": "PW_BLOCKED_OPTION_ID", "ready": "PW_READY_OPTION_ID"}
    if not isinstance(mapping, dict) or not {"entry", "done"} <= mapping.keys() or not set(mapping) <= names.keys():
        raise Refusal("Lifecycle JSON selects entry/done and optional reopen/blocked/ready status names")
    variables = {"PW_PROJECT_ID": p["id"], "PW_STATUS_FIELD_ID": field["id"], "PW_STATUS_FIELD_NAME": field["name"], "PW_AUTOMATION_ENABLED": "false", "PW_NATIVE_SETTINGS_VERIFIED": "false"}
    for key, name in mapping.items():
        variables[names[key]] = one(field["options"], "name", text(name, "status name"), "Lifecycle status name")["id"]
    if selected_project(ctx, project_id=p["id"]) != p:
        raise Refusal("Project changed while resolving lifecycle IDs")
    return {"schema_version": 1, "outcome": "success", "project": {"id": p["id"], "url": p["url"]}, "variables": variables, "writes_sent": 0, "manual_requirements": ["Select and adapt the existing Project Workflows lifecycle starter in the consuming project", "Choose runner credentials and other lifecycle policy variables under separate setup authorization", "Verify actual native settings, view grouping/sorting and one writer per transition before enabling automation"]}


def handler(args):
    alias_selection(args)
    ctx = Context(args)
    if args.command == "recover":
        return recover(ctx, lambda spec: verify_operation(ctx, spec))
    if args.command in ("read-project", "read-view", "automation-config"):
        if args.execute:
            raise Refusal("Inspection/configuration reads do not execute service writes")
        if args.command == "automation-config":
            return automation_config(ctx)
        if args.command == "read-view":
            p = selected_project(ctx)
            view = one(required(ctx, p, "views"), "id", node_id(args.view_id), "View ID")
            result = {"schema_version": 1, "outcome": "success", "view": view, "coverage": {}}
            try:
                result["visible_field_ids"] = visible_fields(ctx, p, view["id"])
                result["coverage"]["visible_fields"] = {"complete": True}
            except (Refusal, TransportError) as exc:
                result["coverage"]["visible_fields"] = {"complete": False, "reason": str(exc)}
            result["coverage"]["revision_stable"] = one(required(ctx, p, "views"), "id", view["id"], "View ID") == view
            result["manual_requirements"] = ["Grouping/sorting setters and native workflow configuration are unsupported"]
            return result
        return inspect(ctx)
    plan, steps = prepare(ctx)
    return execute(ctx, plan, steps, prepare)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    commands = ("read-project", "read-view", "create-project", "copy-project", "link-repository", "ensure-field", "create-view", "edit-view", "add-item", "move-card", "automation-config", "recover")
    for command in commands:
        p = sub.add_parser(command)
        add_common(p)
        p.add_argument("--owner", help="Explicit project owner; defaults to configured owner or repository owner")
        p.add_argument("--project-id")
        p.add_argument("--project-number", type=positive)
        p.add_argument("--field-name", default="Status")
        if command == "read-project":
            p.add_argument("--fields", default="project,fields,views,workflows,repositories")
        if command in ("read-view", "edit-view"):
            p.add_argument("--view-id", required=True)
        if command in ("create-project", "copy-project"):
            p.add_argument("--title", required=True)
        if command == "create-project":
            p.add_argument("--link-repository", action="store_true")
        if command == "copy-project":
            p.add_argument("--new-owner")
        if command == "ensure-field":
            p.add_argument("--name", required=True)
            p.add_argument("--data-type", choices=("TEXT", "NUMBER", "DATE", "SINGLE_SELECT"), required=True)
            p.add_argument("--options-file")
        if command in ("create-view", "edit-view"):
            p.add_argument("--name", required=command == "create-view")
            p.add_argument("--layout", choices=tuple(LAYOUTS), required=command == "create-view")
            p.add_argument("--visible-field", action="append", default=[])
            if command == "edit-view":
                p.add_argument("--filter", help="Exact GitHub view filter")
            else:
                p.set_defaults(filter=None)
        if command in ("add-item", "move-card"):
            target = p.add_mutually_exclusive_group(required=True)
            target.add_argument("--issue", type=positive)
            target.add_argument("--pr", type=positive)
        if command == "move-card":
            p.add_argument("--status", required=True)
        if command == "automation-config":
            p.add_argument("--mapping-file", required=True)
        if command == "recover":
            p.add_argument("--result-id", help="Independently inspected project/field/view/item node ID")
    return run(parser, handler)


if __name__ == "__main__":
    raise SystemExit(main())
