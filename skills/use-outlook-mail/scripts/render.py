#!/usr/bin/env python3
"""Render bounded Outlook Mail exports and individual messages."""
import argparse
import json
from pathlib import Path
import runpy
import sys
_shared = runpy.run_path(str(Path(__file__).resolve().parents[2] / "authorize-microsoft/scripts/text.py"))
clean_text, truncate, quote, address = (_shared[name] for name in ("clean_text", "truncate", "quote", "address"))

def unsubscribe_line(message):
    headers = {(item.get("name") or "").lower(): item.get("value") or "" for item in message.get("internetMessageHeaders") or []}
    value = " ".join(headers.get("list-unsubscribe", "").split())
    if not value:
        return ""
    one_click = "one-click" in headers.get("list-unsubscribe-post", "").lower()
    return value + (" (one-click supported)" if one_click else "")


def recipients(message, key):
    return ", ".join(filter(None, (address(item) for item in message.get(key) or [])))


def message_body(message, body_limit):
    body = message.get("body") or {}
    content = clean_text(body.get("content") or message.get("bodyPreview") or "", body.get("contentType"))
    return truncate(content, body_limit) if body_limit > 0 else content


def render_mail(args, data):
    lines = [
        f"# Microsoft 365 Mail - {args.alias}",
        "",
        f"Last refreshed: {args.refreshed}",
        "",
        f"Account email: `{args.email}`",
        "",
        f"Folder: `Inbox`",
        "",
        f"Window: last {args.days} days",
        "",
        f"Max results: {args.max_results}",
        "",
        "## Messages",
        "",
    ]
    messages = data.get("value") or []
    if not messages:
        lines.append("_No messages matched this export window._")
        return "\n".join(lines) + "\n"
    for message in messages:
        subject = message.get("subject") or "(no subject)"
        content = message_body(message, args.body_limit)
        lines.extend(
            [
                f"### {message.get('receivedDateTime') or 'unknown date'} - {subject}",
                "",
                f"- From: {address(message.get('from')) or 'unknown'}",
                f"- To: {recipients(message, 'toRecipients')}",
                f"- Cc: {recipients(message, 'ccRecipients')}",
                f"- Importance: {message.get('importance') or 'normal'}",
                f"- Read: {'yes' if message.get('isRead') else 'no'}",
                f"- Attachments: {'yes' if message.get('hasAttachments') else 'no'}",
                f"- Categories: {', '.join(message.get('categories') or [])}",
                f"- Conversation ID: `{message.get('conversationId') or ''}`",
                f"- Message ID: `{message.get('id') or ''}`",
            ]
        )
        if message.get("webLink"):
            lines.append(f"- Outlook: {message['webLink']}")
        unsubscribe = unsubscribe_line(message)
        if unsubscribe:
            lines.append(f"- Unsubscribe: {unsubscribe}")
        if content:
            lines.extend(["- Body:", "", quote(content), ""])
        else:
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def attachment_summary(item):
    parts = [item.get("name") or "(unnamed)", item.get("contentType") or "", f"{item.get('size') or 0} bytes"]
    if item.get("isInline"):
        parts.append("inline")
    return " | ".join(part for part in parts if part)


def render_message(args, message):
    """One message read by ID from any folder; the same fields as the Inbox snapshot plus folder, sent time, Bcc, and attachment names."""
    lines = [f"# {message.get('subject') or '(no subject)'}", ""]
    fields = [
        ("Received", message.get("receivedDateTime")),
        ("Sent", message.get("sentDateTime")),
        ("From", address(message.get("from")) or "unknown"),
        ("To", recipients(message, "toRecipients")),
        ("Cc", recipients(message, "ccRecipients")),
        ("Bcc", recipients(message, "bccRecipients")),
        ("Reply-To", recipients(message, "replyTo")),
        ("Folder", message.get("folder")),
        ("Read", "yes" if message.get("isRead") else "no"),
        ("Draft", "yes" if message.get("isDraft") else ""),
        ("Importance", message.get("importance") or "normal"),
        ("Categories", ", ".join(message.get("categories") or [])),
        ("Conversation ID", f"`{message['conversationId']}`" if message.get("conversationId") else ""),
        ("Message ID", f"`{message.get('id') or ''}`"),
        ("Outlook", message.get("webLink")),
        ("Unsubscribe", unsubscribe_line(message)),
    ]
    lines.extend(f"- {label}: {value}" for label, value in fields if value)
    attachments = message.get("attachments") or []
    if attachments:
        lines.append("- Attachments:")
        lines.extend(f"  - {attachment_summary(item)}" for item in attachments)
    content = message_body(message, args.body_limit)
    lines.extend(["- Body:", "", quote(content) if content else "    _No body text._"])
    return "\n".join(lines).rstrip() + "\n"



def main(argv):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    mail = sub.add_parser("mail")
    for name in ("alias", "email", "refreshed", "input"):
        mail.add_argument("--" + name, required=True)
    for name in ("days", "max-results", "body-limit"):
        mail.add_argument("--" + name, required=True, type=int)
    message = sub.add_parser("message")
    message.add_argument("--input", required=True)
    message.add_argument("--body-limit", required=True, type=int)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as stream:
        data = json.load(stream)
    print((render_mail if args.command == "mail" else render_message)(args, data), end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
