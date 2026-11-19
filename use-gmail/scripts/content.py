"""Offline MIME helpers for bounded Gmail attachments and manually sent drafts."""
import argparse
import base64
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import sys


def load(path):
    return json.loads(Path(path).read_text())


def decode(data):
    if not isinstance(data, str) or not re.fullmatch(r"[A-Za-z0-9_-]*={0,2}", data):
        raise ValueError("Invalid attachment base64url data; existing output was preserved")
    return base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)


def message(path, expected):
    item = load(path)
    if item.get("id") != expected or not isinstance(item.get("payload"), dict) or item.get("error"):
        raise ValueError("Message response did not match the exact requested message ID")
    return item


def walk(part):
    yield part
    for child in part.get("parts", []):
        yield from walk(child)


def attachments(item):
    result = []
    seen = set()
    for part in walk(item["payload"]):
        body = part.get("body", {})
        headers = {x["name"].lower(): x["value"] for x in part.get("headers", [])}
        disposition = headers.get("content-disposition", "").split(";", 1)[0].lower()
        if not (part.get("filename") or body.get("attachmentId") or disposition == "attachment"):
            continue
        part_id = part.get("partId") or "root"
        if part_id in seen:
            raise ValueError("Ambiguous attachment part IDs; no attachment was selected")
        seen.add(part_id)
        result.append({"partId": part_id, "filename": part.get("filename", ""), "mimeType": part.get("mimeType", "application/octet-stream"), "size": body.get("size"), "attachmentId": body.get("attachmentId"), "disposition": disposition, "body": body})
    return result


def selected(item, part_id):
    matches = [x for x in attachments(item) if x["partId"] == part_id]
    if len(matches) != 1:
        raise ValueError("No unique attachment with that --part; run gmail attachments for this message")
    return matches[0]


def header(value):
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Mail headers must not contain control characters")
    return value


def addresses(values):
    result = []
    for value in values:
        header(value)
        parsed = getaddresses([value])
        if not parsed or any(not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+", address) for _, address in parsed):
            raise ValueError("Supply explicit valid recipient email addresses")
        result.extend(address for _, address in parsed)
    return result


def snapshot(raw):
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    headers = {name: str(msg.get(name, "")) for name in ["From", "To", "Cc", "Bcc", "Subject", "In-Reply-To", "References"]}
    files = [{"filename": part.get_filename(), "type": part.get_content_type(), "sha256": hashlib.sha256(part.get_payload(decode=True)).hexdigest()} for part in msg.iter_attachments()]
    plain = msg.get_body(preferencelist=("plain",))
    return {"headers": headers, "body": plain.get_content().replace("\r\n", "\n") if plain else None, "attachments": files}


def draft(args):
    sender = addresses([args.sender])
    if len(sender) != 1:
        raise ValueError("Configured account email must be one email address")
    to = addresses(args.to)
    if not to:
        raise ValueError("At least one explicit --to recipient is required")
    msg = EmailMessage()
    msg["From"] = sender[0]
    msg["To"] = ", ".join(to)
    for name, values in [("Cc", args.cc), ("Bcc", args.bcc)]:
        resolved = addresses(values)
        if resolved:
            msg[name] = ", ".join(resolved)
    thread = None
    subject = args.subject
    if args.reply_source:
        source = message(args.reply_source, args.reply_message)
        source_headers = {x["name"].lower(): x["value"] for x in source["payload"].get("headers", [])}
        original_subject = source_headers.get("subject", "")
        message_id = source_headers.get("message-id", "")
        if not source.get("threadId") or not re.fullmatch(r"<[^\s<>]+@[^\s<>]+>", message_id):
            raise ValueError("Reply source lacks a valid thread or Message-ID; create an unthreaded draft explicitly instead")
        if subject and re.sub(r"^(re:\s*)+", "", subject, flags=re.I) != re.sub(r"^(re:\s*)+", "", original_subject, flags=re.I):
            raise ValueError("Reply subject must match the source subject")
        subject = subject or (original_subject if original_subject.lower().startswith("re:") else "Re: " + original_subject)
        msg["In-Reply-To"] = header(message_id)
        msg["References"] = header((source_headers.get("references", "") + " " + message_id).strip())
        thread = source["threadId"]
    if not subject:
        raise ValueError("A --subject is required for a new draft")
    msg["Subject"] = header(subject)
    body = Path(args.body_file).read_text(encoding="utf-8")
    msg.set_content(body)
    for filename in args.attach:
        path = Path(filename)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        main, sub = mime.split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=main, subtype=sub, filename=header(path.name))
    raw = msg.as_bytes(policy=policy.SMTP)
    request = {"message": {"raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")}}
    if thread:
        request["message"]["threadId"] = thread
    Path(args.request).write_text(json.dumps(request))
    Path(args.expected).write_text(json.dumps(snapshot(raw)))
    print(json.dumps({"from": sender[0], "to": to, "cc": addresses(args.cc), "bcc": addresses(args.bcc), "subject": subject, "threadId": thread, "body": body, "attachments": [str(Path(x)) for x in args.attach]}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["attachments", "select", "decode"]:
        p = sub.add_parser(command)
        p.add_argument("message_file")
        p.add_argument("message_id")
        if command != "attachments":
            p.add_argument("part_id")
        if command == "decode":
            p.add_argument("body_file")
            p.add_argument("output")
    p = sub.add_parser("draft")
    for name in ["sender", "body-file", "request", "expected"]:
        p.add_argument("--" + name, required=True)
    for name in ["to", "cc", "bcc", "attach"]:
        p.add_argument("--" + name, action="append", default=[])
    p.add_argument("--subject")
    p.add_argument("--reply-source")
    p.add_argument("--reply-message")
    p = sub.add_parser("verify-draft")
    p.add_argument("readback")
    p.add_argument("expected")
    p.add_argument("draft_id")
    p.add_argument("message_id")
    p.add_argument("thread_id")
    args = parser.parse_args()
    if args.command == "draft":
        return draft(args)
    if args.command == "verify-draft":
        value = load(args.readback)
        msg = value.get("message", {})
        if value.get("id") != args.draft_id or msg.get("id") != args.message_id or "DRAFT" not in msg.get("labelIds", []) or "SENT" in msg.get("labelIds", []):
            raise ValueError("Draft identity or DRAFT label was not confirmed")
        if args.thread_id and msg.get("threadId") != args.thread_id:
            raise ValueError("Draft reply thread did not match")
        if snapshot(decode(msg.get("raw"))) != load(args.expected):
            raise ValueError("Draft recipients, subject, body, reply headers or attachments differ from the preview")
        return
    item = message(args.message_file, args.message_id)
    if args.command == "attachments":
        print(json.dumps([{k: v for k, v in x.items() if k != "body"} for x in attachments(item)], indent=2))
    elif args.command == "select":
        print(json.dumps(selected(item, args.part_id)))
    else:
        part = selected(item, args.part_id)
        body = load(args.body_file)
        data = decode(body.get("data"))
        if body.get("size") != len(data) or part.get("size") != len(data):
            raise ValueError("Attachment byte count did not match the message; existing output was preserved")
        Path(args.output).write_bytes(data)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
