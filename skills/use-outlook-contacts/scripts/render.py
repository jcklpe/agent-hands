#!/usr/bin/env python3
"""Render a bounded Outlook contact export."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

_support_path = Path(__file__).resolve().parents[2] / "authorize-microsoft/scripts/text.py"
_spec = importlib.util.spec_from_file_location("microsoft_text", _support_path)
_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text)
clean_text, truncate, quote = _text.clean_text, _text.truncate, _text.quote


def render_contacts(args, data):
    lines = [
        f"# Microsoft 365 Contacts - {args.alias}",
        "",
        f"Last refreshed: {args.refreshed}",
        "",
        f"Account email: `{args.email}`",
        "",
        f"Max results: {args.max_results}",
        "",
        "## Contacts",
        "",
    ]
    contacts = sorted(data.get("value") or [], key=lambda item: (item.get("displayName") or "").lower())
    if not contacts:
        lines.append("_No Outlook contacts were found._")
        return "\n".join(lines) + "\n"
    for contact in contacts:
        emails = [item.get("address") or "" for item in contact.get("emailAddresses") or []]
        phones = list(contact.get("businessPhones") or [])
        if contact.get("mobilePhone"):
            phones.append(contact["mobilePhone"])
        notes = truncate(clean_text(contact.get("personalNotes") or ""), args.notes_limit)
        lines.extend(
            [
                f"### {contact.get('displayName') or contact.get('givenName') or '(unnamed contact)'}",
                "",
                f"- Contact ID: `{contact.get('id') or ''}`",
                f"- Given name: {contact.get('givenName') or ''}",
                f"- Surname: {contact.get('surname') or ''}",
                f"- Email: {', '.join(filter(None, emails))}",
                f"- Phone: {', '.join(filter(None, phones))}",
                f"- Company: {contact.get('companyName') or ''}",
                f"- Job title: {contact.get('jobTitle') or ''}",
            ]
        )
        if notes:
            lines.extend(["- Notes:", "", quote(notes), ""])
        else:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["contacts"])
    for name in ("alias", "email", "refreshed", "input"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--max-results", required=True, type=int)
    parser.add_argument("--notes-limit", required=True, type=int)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data.get("value"), list) or data.get("error"):
        raise ValueError("Expected a contact collection")
    print(render_contacts(args, data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
