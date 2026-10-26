#!/usr/bin/env python3
"""Render bounded GitHub responses as Markdown."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "authorize-github" / "scripts"))
from render_common import days_since, preview, header, names, label_names

def render_discussions(data, args):
    items = data.get("items", [])
    out = header("Discussions", args.owner, args.repo, len(items), "discussions")
    out += ["*Bounded view: up to 50 discussions, 50 comments per discussion, and 25 replies per comment.*", ""]
    by_cat = {}
    for d in items:
        by_cat.setdefault((d.get("category") or {}).get("name", "Uncategorized"), []).append(d)
    for cat in sorted(by_cat):
        out += ["## %s" % cat.upper(), ""]
        for d in by_cat[cat]:
            age = days_since(d.get("updatedAt"))
            replies = d.get("replyCount") or 0
            out += [
                "### [#%d %s](discussions/%d.md)" % (d["number"], d["title"], d["number"]),
                "",
                "**Updated:** %sd ago | **Author:** @%s | **Comments:** %d%s%s"
                % (
                    age if age is not None else "?",
                    (d.get("author") or {}).get("login", "unknown"),
                    d.get("commentCount", 0),
                    " (+%d replies)" % replies if replies else "",
                    " | **Answered**" if d.get("isAnswered") else "",
                ),
                "",
                "[On GitHub](%s)" % d.get("url", ""),
                "",
            ]
            p = preview(d.get("body"))
            if p:
                out += [p, ""]
            out += ["---", ""]
    return "\n".join(out)


def render_discussion_detail(data, args):
    """Render retrieved comments/replies and disclose known truncation."""
    d = data
    created, updated = days_since(d.get("createdAt")), days_since(d.get("updatedAt"))
    comments = (d.get("comments") or {}).get("nodes") or []
    total = (d.get("comments") or {}).get("totalCount", len(comments))
    out = [
        "# #%d — %s" % (d["number"], d["title"]),
        "",
        "**Category:** %s" % (d.get("category") or {}).get("name", "Uncategorized"),
        "",
        "**Opened:** %sd ago by @%s" % (created if created is not None else "?",
                                       (d.get("author") or {}).get("login", "unknown")),
        "",
        "**Updated:** %sd ago" % (updated if updated is not None else "?"),
        "",
    ]
    if d.get("isAnswered"):
        out += ["**Answered**", ""]
    if d.get("url"):
        out += ["**URL:** %s" % d["url"], ""]
    out += ["---", "", "## Opening Post", "", d.get("body") or "(empty)", ""]

    if comments:
        out += ["---", "", "## Comments (%d)" % total, ""]
        for c in comments:
            who = (c.get("author") or {}).get("login", "unknown")
            when = c.get("createdAt") or ""
            try:
                when = datetime.fromisoformat(when.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                pass
            mark = " — **marked as answer**" if c.get("isAnswer") else ""
            out += ["### @%s — %s%s" % (who, when, mark), "", c.get("body") or "", ""]
            replies = (c.get("replies") or {}).get("nodes") or []
            for r in replies:
                rwho = (r.get("author") or {}).get("login", "unknown")
                rwhen = r.get("createdAt") or ""
                try:
                    rwhen = datetime.fromisoformat(rwhen.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
                except ValueError:
                    pass
                # Replies are indented as a blockquote so nesting survives plain-text reading.
                body = (r.get("body") or "").split("\n")
                out += ["> **@%s — %s**" % (rwho, rwhen), ">"]
                out += ["> " + line if line else ">" for line in body]
                out += [""]
            reply_total = (c.get("replies") or {}).get("totalCount", len(replies))
            if reply_total > len(replies):
                out += ["*Note: %d of %d replies fetched for this comment.*" % (len(replies), reply_total), ""]
            out += ["---", ""]
    if total > len(comments):
        out += ["*Note: %d of %d comments fetched; the thread exceeds the page size.*" % (len(comments), total), ""]
    return "\n".join(out)


RENDERERS = {'discussions': render_discussions, 'discussion-detail': render_discussion_detail}

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
