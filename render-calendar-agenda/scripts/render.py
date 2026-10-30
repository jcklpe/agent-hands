#!/usr/bin/env python3
"""Render explicit provider exports without credentials, network access, or workspace defaults."""
import argparse
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import events
from microsoft import normalize_event


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Window boundaries require an explicit UTC offset or Z")
    return result


def convert_event(event, zone, fallback=None):
    result = copy.deepcopy(event)
    if result.get("status") == "cancelled":
        return result
    for key in ("start", "end"):
        point = result.get(key) or {}
        if "date" in point:
            date.fromisoformat(point["date"])
        else:
            value = datetime.fromisoformat(point["dateTime"].replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=ZoneInfo(point.get("timeZone") or fallback or ""))
            point["dateTime"] = value.astimezone(zone).isoformat()
        result[key] = point
    return result


def load_bundle(path, zone, lower, upper):
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != 1 or data.get("complete") is not True:
        raise ValueError("Expected a complete schema_version=1 calendar export")
    provider, source = data["provider"], data["source"]
    if provider not in {"google", "microsoft"} or not isinstance(source, str) or not source.strip() or any(c in source for c in "\r\n"):
        raise ValueError("Invalid source identity")
    if instant(data["start"]) > lower or instant(data["end"]) < upper:
        raise ValueError(f"{source}: export does not cover the requested window")
    if not isinstance(data["calendars"], list) or not data["calendars"]:
        raise ValueError(f"{source}: export selected no calendars")
    pairs, calendar_ids = [], set()
    for calendar in data["calendars"]:
        if provider == "google":
            meta = copy.deepcopy(calendar["calendar"])
            items = calendar["events"]["items"]
        else:
            if data.get("timezone") != "UTC":
                raise ValueError("Microsoft input must have been fetched in UTC")
            meta = {"id": calendar.get("graphId") or calendar["id"], "summary": calendar.get("name") or calendar["id"]}
            items = [normalize_event(event, zone) for event in calendar["events"]]
        if not isinstance(items, list) or not isinstance(meta.get("id"), str) or not meta["id"]:
            raise ValueError("Invalid calendar metadata/events")
        namespace = f"{provider}:{source}:{meta['id']}"
        if namespace in calendar_ids:
            raise ValueError("Duplicate calendar in export")
        calendar_ids.add(namespace)
        meta["id"] = namespace
        meta["summary"] = f"{source} ({provider}): {meta.get('summary') or 'Calendar'}"
        selected = []
        for raw in items:
            event = convert_event(raw, zone, meta.get("timeZone"))
            if event.get("status") == "cancelled":
                continue
            start, end = event["start"], event["end"]
            if "date" in start:
                begins = datetime.combine(date.fromisoformat(start["date"]), datetime.min.time(), zone)
                ends = datetime.combine(date.fromisoformat(end["date"]), datetime.min.time(), zone)
            else:
                begins, ends = instant(start["dateTime"]), instant(end["dateTime"])
            if ends < begins or ("date" in start and ends == begins):
                raise ValueError("Event end must follow start; timed point events may have equal bounds")
            if (ends == begins and begins < lower) or (ends > begins and ends <= lower) or begins >= upper:
                continue
            # Provider-local IDs must not merge lookalikes across accounts; a shared iCalendar UID still can.
            event["id"] = namespace + ":" + event.get("id", "")
            if event.get("recurringEventId"):
                event["recurringEventId"] = namespace + ":" + event["recurringEventId"]
            selected.append(event)
        pairs.append((meta, {"items": selected}))
    return f"{provider}:{source}", pairs


def publish(text, path, force):
    target = Path(path)
    if target.is_symlink() or (target.exists() and (not target.is_file() or not force)):
        raise ValueError("Choose a regular output file; existing output requires --force")
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".calendar-agenda-", dir=target.parent)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        if force:
            os.replace(temporary, target)
        else:
            os.link(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--expect-source", action="append", required=True, help="provider:account alias, repeat for every intended source")
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--omit-description", action="append", default=[], help="Exact displayed calendar label, case insensitive")
    parser.add_argument("--allow-missing", action="store_true", help="Write clearly incomplete output and return status 2")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    lower, upper, zone = instant(args.start), instant(args.end), ZoneInfo(args.timezone)
    if lower >= upper:
        raise ValueError("--from must precede --to (exclusive)")
    if len(set(args.expect_source)) != len(args.expect_source) or any("\n" in item or "\r" in item or (not item.startswith(("google:", "microsoft:")) or not item.split(":", 1)[1].strip()) for item in args.expect_source):
        raise ValueError("Expected sources must be unique provider:account names")
    found, pairs = set(), []
    for path in args.input:
        if Path(path).resolve() == Path(args.output).resolve() or (Path(args.output).exists() and os.path.samefile(path, args.output)):
            raise ValueError("Output must not replace an input")
        key, rows = load_bundle(path, zone, lower, upper)
        if key in found or key not in args.expect_source:
            raise ValueError("Duplicate or unexpected input source: " + key)
        found.add(key)
        pairs.extend(rows)
    missing = set(args.expect_source) - found
    if missing and not args.allow_missing:
        raise ValueError("Missing sources; previous output preserved: " + ", ".join(sorted(missing)))
    lines = ["# Calendar Agenda", "", f"Last rendered: {datetime.now(timezone.utc).isoformat()}", "", f"Window: {args.start} to {args.end} (exclusive)", f"Display timezone: {args.timezone}", "", "## Source coverage", ""]
    for source in args.expect_source:
        lines.append(f"- {source}: {'MISSING — do not infer availability from this agenda' if source in missing else 'included'}")
    lines.append("")
    if missing:
        lines.extend(["**INCOMPLETE: required sources are missing.**", ""])
    events.NO_DESCRIPTION_CALENDARS = {value.strip().lower() for value in args.omit_description}
    if pairs:
        lines.append(events.render_compact(pairs, lower, zone) if args.compact else events.render_combined(pairs))
    else:
        lines.append("No source data was available; this is not an empty calendar.")
    publish("\n".join(lines) + "\n", args.output, args.force)
    return 2 if missing else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
