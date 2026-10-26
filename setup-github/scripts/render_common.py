"""Shared GitHub Markdown formatting primitives."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PREVIEW_CHARS = 160

def days_since(stamp):
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).days


def preview(body):
    text = (body or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) > PREVIEW_CHARS:
        text = text[:PREVIEW_CHARS].rstrip() + "..."
    return text


def header(title, owner, repo, count, noun):
    return [
        "# %s — %s/%s" % (title, owner, repo),
        "",
        "**Generated:** %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "",
        "**Count:** %d %s" % (count, noun),
        "",
        "---",
        "",
    ]


def names(items, key="login"):
    return ", ".join(i.get(key, "?") for i in items or [])


def label_names(labels):
    return ", ".join("`%s`" % l.get("name", "?") for l in labels or [])
