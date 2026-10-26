#!/usr/bin/env python3
"""Render a bounded Planner task export."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

_support_path = Path(__file__).resolve().parents[2] / "setup-microsoft-services/scripts/text.py"
_spec = importlib.util.spec_from_file_location("microsoft_text", _support_path)
_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text)
clean_text, truncate, quote, address = _text.clean_text, _text.truncate, _text.quote, _text.address


PLANNER_PRIORITY = [(1, "urgent"), (4, "important"), (7, "medium"), (10, "low")]

def planner_priority(value):
    if value is None:
        return "medium"
    for ceiling, name in PLANNER_PRIORITY:
        if value <= ceiling:
            return name
    return "low"

def planner_status(task):
    percent = task.get("percentComplete") or 0
    if percent >= 100:
        return "done"
    return "in progress" if percent > 0 else "not started"

def planner_person(users, user_id, me):
    if not user_id:
        return ""
    name = (users.get(user_id) or {}).get("displayName") or user_id
    return f"{name} (you)" if user_id == me else name

def planner_date(value):
    return (value or "")[:10]

def render_planner_task(lines, task, plan_entry, users, me, limit):
    categories = (plan_entry.get("details") or {}).get("categoryDescriptions") or {}
    labels = [categories.get(key) or key for key, on in sorted((task.get("appliedCategories") or {}).items()) if on]
    assignees = [planner_person(users, uid, me) for uid in sorted((task.get("assignments") or {}).keys())]
    details = (plan_entry.get("taskDetails") or {}).get(task.get("id")) or {}
    lines.extend([f"#### {task.get('title') or '(untitled task)'}", ""])
    lines.append(f"- Status: {planner_status(task)}")
    if task.get("dueDateTime"):
        lines.append(f"- Due: {planner_date(task.get('dueDateTime'))}")
    if task.get("startDateTime"):
        lines.append(f"- Start: {planner_date(task.get('startDateTime'))}")
    lines.append(f"- Priority: {planner_priority(task.get('priority'))}")
    lines.append(f"- Assignees: {', '.join(assignees) if assignees else 'unassigned'}")
    if labels:
        lines.append(f"- Labels: {', '.join(labels)}")
    created_by = ((task.get("createdBy") or {}).get("user") or {}).get("id")
    lines.append(f"- Created: {planner_date(task.get('createdDateTime'))}" + (f" by {planner_person(users, created_by, me)}" if created_by else ""))
    lines.append(f"- Task ID: `{task.get('id') or ''}`")
    description = truncate(clean_text(details.get("description") or ""), limit)
    if description:
        lines.extend(["- Description:", "", quote(description), ""])
    checklist = sorted((details.get("checklist") or {}).values(), key=lambda item: item.get("orderHint") or "")
    if checklist:
        lines.append("- Checklist:")
        for item in checklist:
            mark = "x" if item.get("isChecked") else " "
            lines.append(f"  - [{mark}] {item.get('title') or ''}")
    lines.append("")

def render_planner(args, data):
    users = data.get("users") or {}
    me = args.me
    lines = [
        f"# Microsoft 365 Planner - {args.alias}",
        "",
        f"Last refreshed: {args.refreshed}",
        "",
        f"Account email: `{args.email}`",
        "",
        "Generated snapshot of the plans configured for this account. Do not edit by hand; change Planner through the native `use-planner` capability and export again.",
        "",
    ]
    plans = data.get("plans") or []
    if not plans:
        lines.append("_No plans are configured._")
        return "\n".join(lines) + "\n"
    for entry in plans:
        plan = entry.get("plan") or {}
        config = entry.get("config") or {}
        tasks = entry.get("tasks") or []
        open_tasks = [task for task in tasks if (task.get("percentComplete") or 0) < 100]
        done_tasks = [task for task in tasks if (task.get("percentComplete") or 0) >= 100]
        mine = [task for task in open_tasks if me and me in (task.get("assignments") or {})]
        lines.extend([f"## {plan.get('title') or config.get('name') or '(untitled plan)'}", ""])
        if config.get("context"):
            lines.extend([config["context"], ""])
        lines.extend(
            [
                f"- Plan ID: `{plan.get('id') or ''}`",
                f"- Group ID: `{(plan.get('container') or {}).get('containerId') or plan.get('owner') or ''}`",
                f"- Open tasks: {len(open_tasks)} | Done: {len(done_tasks)} | Open and assigned to you: {len(mine)}",
                "",
            ]
        )
        buckets = sorted(entry.get("buckets") or [], key=lambda item: item.get("orderHint") or "")
        known = {bucket.get("id") for bucket in buckets}
        groups = [(bucket.get("name") or "(unnamed bucket)", bucket.get("id")) for bucket in buckets]
        if any(task.get("bucketId") not in known for task in open_tasks):
            groups.append(("(no bucket)", None))
        for name, bucket_id in groups:
            in_bucket = [task for task in open_tasks if (task.get("bucketId") if task.get("bucketId") in known else None) == bucket_id]
            lines.extend([f"### {name}", ""])
            if not in_bucket:
                lines.extend(["_No open tasks._", ""])
                continue
            in_bucket.sort(key=lambda task: (task.get("dueDateTime") or "9999", task.get("orderHint") or ""))
            for task in in_bucket:
                render_planner_task(lines, task, entry, users, me, args.description_limit)
        if done_tasks:
            names = {bucket.get("id"): bucket.get("name") for bucket in buckets}
            lines.extend(["### Completed", ""])
            done_tasks.sort(key=lambda task: task.get("completedDateTime") or "", reverse=True)
            for task in done_tasks:
                completed_by = ((task.get("completedBy") or {}).get("user") or {}).get("id")
                who = f" by {planner_person(users, completed_by, me)}" if completed_by else ""
                lines.append(f"- {task.get('title') or '(untitled task)'} | {names.get(task.get('bucketId')) or 'no bucket'} | completed {planner_date(task.get('completedDateTime'))}{who} | `{task.get('id') or ''}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["planner"])
    for name in ("alias", "email", "refreshed", "input"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--description-limit", required=True, type=int)
    parser.add_argument("--me", default="")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("plans"), list) or data.get("error"):
        raise ValueError("Expected a plan collection")
    print(render_planner(args, data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
