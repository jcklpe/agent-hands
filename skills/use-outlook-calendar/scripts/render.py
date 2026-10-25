#!/usr/bin/env python3
"""Render a bounded Outlook calendar export."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

_support_path = Path(__file__).resolve().parents[2] / "authorize-microsoft/scripts/text.py"
_spec = importlib.util.spec_from_file_location("microsoft_text", _support_path)
_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text)
clean_text, truncate, quote, address = _text.clean_text, _text.truncate, _text.quote, _text.address


def event_start(event):
    start = event.get("start") or {}
    return start.get("dateTime") or ""

def render_calendar(args, data):
    lines = [
        f"# Microsoft 365 Calendar - {args.alias}",
        "",
        f"Last refreshed: {args.refreshed}",
        "",
        f"Account email: `{args.email}`",
        "",
        f"Window: {args.start} to {args.end}",
        "",
        f"Response time zone: `{args.timezone}`",
        "",
        "## Events",
        "",
    ]
    flattened = []
    for calendar in data.get("calendars") or []:
        for event in calendar.get("events") or []:
            flattened.append((calendar, event))
    flattened.sort(key=lambda item: event_start(item[1]))
    if not flattened:
        lines.append("_No events matched this calendar window._")
        return "\n".join(lines) + "\n"
    for calendar, event in flattened:
        start = event.get("start") or {}
        end = event.get("end") or {}
        body = event.get("body") or {}
        description = truncate(clean_text(body.get("content") or event.get("bodyPreview") or "", body.get("contentType")), args.description_limit)
        attendees = [address(item) for item in event.get("attendees") or []]
        lines.extend(
            [
                f"### {start.get('dateTime') or 'unknown time'} - {event.get('subject') or '(untitled event)'}",
                "",
                f"- Calendar: {calendar.get('name') or calendar.get('id') or 'Calendar'}",
                f"- Calendar ID: `{calendar.get('id') or ''}`",
                f"- Event ID: `{event.get('id') or ''}`",
                f"- Start: {start.get('dateTime') or ''} ({start.get('timeZone') or args.timezone})",
                f"- End: {end.get('dateTime') or ''} ({end.get('timeZone') or args.timezone})",
                f"- All day: {'yes' if event.get('isAllDay') else 'no'}",
                f"- Location: {(event.get('location') or {}).get('displayName') or ''}",
                f"- Organizer: {address(event.get('organizer'))}",
                f"- Attendees: {', '.join(filter(None, attendees))}",
                f"- Online meeting: {'yes' if event.get('isOnlineMeeting') else 'no'}",
            ]
        )
        if event.get("webLink"):
            lines.append(f"- Outlook: {event['webLink']}")
        if description:
            lines.extend(["- Description:", "", quote(description), ""])
        else:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["calendar"])
    for name in ("alias", "email", "refreshed", "input"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--description-limit", required=True, type=int)
    for name in ("start", "end", "timezone"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("calendars"), list) or data.get("error"):
        raise ValueError("Expected a calendar collection")
    print(render_calendar(args, data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
