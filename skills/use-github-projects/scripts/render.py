#!/usr/bin/env python3
"""Render bounded GitHub responses as Markdown."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "authorize-github" / "scripts"))
from render_common import days_since, preview, header, names, label_names

def render_board(data, args):
    items = data.get("items", [])
    out = [
        "# Project #%s — %s" % (args.project_number, args.project_name),
        "",
        "**Generated:** %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "",
        "**Total items:** %d" % len(items),
        "",
        "---",
        "",
    ]
    by_status = {}
    for it in items:
        by_status.setdefault(it.get("status") or "No Status", []).append(it)
    for status in sorted(by_status):
        rows = by_status[status]
        out += ["## %s" % status, "", "**Count:** %d" % len(rows), ""]
        for it in rows:
            content = it.get("content") or {}
            title = it.get("title") or content.get("title") or "(untitled)"
            out += ["### %s" % title, ""]
            meta = []
            if content.get("number"):
                meta.append("**#%s**" % content["number"])
            if it.get("assignees"):
                a = it["assignees"]
                meta.append("**Assigned:** %s" % (", ".join(a) if isinstance(a, list) else a))
            if it.get("labels"):
                l = it["labels"]
                meta.append("**Labels:** %s" % (", ".join(l) if isinstance(l, list) else l))
            if meta:
                out += [" | ".join(meta), ""]
            out += ["---", ""]
    return "\n".join(out)


RENDERERS = {'board': render_board}

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
