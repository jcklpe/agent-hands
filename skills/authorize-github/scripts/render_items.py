#!/usr/bin/env python3
"""Render bounded GitHub responses as Markdown."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from render_common import days_since, preview, header, names, label_names

def render_issue_index(data, args):
    items = data.get("items", [])
    noun = "open pull requests" if args.kind == "pr" else "open issues"
    title = "Open Pull Requests" if args.kind == "pr" else "Open Issues"
    out = header(title, args.owner, args.repo, len(items), noun)

    # Group by first label so the index mirrors how work is actually organized.
    grouped, ungrouped = {}, []
    for it in items:
        labels = [l.get("name") for l in it.get("labels") or []]
        (grouped.setdefault(labels[0], []).append(it) if labels else ungrouped.append(it))

    def block(it):
        d = days_since(it.get("updatedAt"))
        line = "### [#%d %s](%s/%d.md)" % (it["number"], it["title"], args.detail_dir, it["number"])
        meta = ["**Updated:** %sd ago" % d if d is not None else "**Updated:** unknown"]
        if it.get("assignees"):
            meta.append("**Assigned:** %s" % names(it["assignees"]))
        if it.get("labels"):
            meta.append("**Labels:** %s" % label_names(it["labels"]))
        chunk = [line, "", " | ".join(meta), ""]
        p = preview(it.get("body"))
        if p:
            chunk += [p, ""]
        chunk += ["---", ""]
        return chunk

    for label in sorted(grouped):
        out += ["## %s" % label.upper(), ""]
        for it in sorted(grouped[label], key=lambda x: -(days_since(x.get("updatedAt")) or 0)):
            out += block(it)
    if ungrouped:
        out += ["## UNLABELED", ""]
        for it in ungrouped:
            out += block(it)
    return "\n".join(out)


def render_item_detail(data, args):
    it = data
    kind = "Pull Request" if args.kind == "pr" else "Issue"
    created, updated = days_since(it.get("createdAt")), days_since(it.get("updatedAt"))
    author = (it.get("author") or {}).get("login", "unknown")
    out = [
        "# #%d — %s" % (it["number"], it["title"]),
        "",
        "**Type:** %s" % kind,
        "",
        "**State:** %s" % it.get("state", "?"),
        "",
        "**Created:** %sd ago by @%s" % (created if created is not None else "?", author),
        "",
        "**Updated:** %sd ago" % (updated if updated is not None else "?"),
        "",
    ]
    if it.get("assignees"):
        out += ["**Assigned:** %s" % names(it["assignees"]), ""]
    if it.get("labels"):
        out += ["**Labels:** %s" % label_names(it["labels"]), ""]
    if it.get("url"):
        out += ["**URL:** %s" % it["url"], ""]
    out += ["---", "", "## Description", "", it.get("body") or "(No description provided)", ""]

    comments = it.get("comments") or []
    if comments:
        out += ["---", "", "## Comments (%d)" % len(comments), ""]
        for c in comments:
            who = (c.get("author") or {}).get("login") or (c.get("user") or {}).get("login", "unknown")
            when = c.get("createdAt") or c.get("created_at") or ""
            try:
                when = datetime.fromisoformat(when.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                pass
            out += ["### @%s — %s" % (who, when), "", c.get("body") or "", "", "---", ""]
    return "\n".join(out)


RENDERERS = {'issue-index': render_issue_index, 'item-detail': render_item_detail}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("renderer", choices=sorted(RENDERERS))
    p.add_argument("--owner", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--kind", default="issue", choices=["issue", "pr"])
    p.add_argument("--detail-dir", default="issues")
    p.add_argument("--project-number", default="")
    p.add_argument("--project-name", default="")
    args = p.parse_args()
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print("ERROR: could not parse JSON on stdin: %s" % exc, file=sys.stderr)
        return 1
    print(RENDERERS[args.renderer](data, args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
