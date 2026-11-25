"""Read Canvas Inbox conversations without marking them read, and reply to one reviewed conversation."""
import re
from pathlib import Path

from canvas_auth import MAX_PAGES, CanvasError, id_string, parse_json, parse_link_header
from canvas_feedback import records
from canvas_write import Executor, digest

PATH = "/api/v1/conversations"
SCOPES = ("inbox", "unread", "starred", "sent", "archived")
COMMANDS = {"inbox", "conversation", "reply-conversation"}
DEFAULT_LIMIT = 25
# Canvas may queue a large conversation's reply, so its message can take a moment to appear.
READBACK_TRIES, READBACK_PAUSE = 5, 2


def add_commands(commands, canvas_id):
    for name, description in (("inbox", "list Inbox conversations without changing their read state"), ("conversation", "read one Inbox conversation without marking it read"), ("reply-conversation", "preview or send one reply in an existing Inbox conversation")):
        command = commands.add_parser(name, help=description)
        command.add_argument("alias")
        command.add_argument("--history-dir", type=Path)
        command.add_argument("--json", action="store_true")
        if name == "inbox":
            command.add_argument("--scope", choices=SCOPES, default="inbox")
            command.add_argument("--course", type=canvas_id, help="Only conversations Canvas files under this course")
            size = command.add_mutually_exclusive_group()
            size.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help=f"Newest conversations to list (default {DEFAULT_LIMIT})")
            size.add_argument("--all", action="store_true", help="List every conversation in the scope")
        else:
            command.add_argument("--conversation", type=canvas_id, required=True)
        if name == "reply-conversation":
            command.add_argument("--body-file", type=Path, required=True, help="Plain UTF-8 text, sent as written")
            audience = command.add_mutually_exclusive_group(required=True)
            audience.add_argument("--to-all", action="store_true", help="Everyone else now in the conversation")
            audience.add_argument("--to", type=canvas_id, action="append", metavar="USER_ID", help="Only these people already in the conversation; repeat")
            command.add_argument("--execute", action="store_true")
            command.add_argument("--expect", help="preview_hash from the reviewed preview")


def text(raw, key):
    value = raw.get(key)
    if value is not None and not isinstance(value, str):
        raise CanvasError("malformed", "Canvas returned invalid Inbox text")
    return value


def ids(value, label):
    if not isinstance(value, list):
        raise CanvasError("malformed", f"Canvas returned invalid {label}")
    return [id_string(item) for item in value]


def summary(reader, raw):
    if not isinstance(raw, dict):
        raise CanvasError("malformed", "Canvas returned a non-object conversation")
    cid = id_string(raw.get("id"))
    count = raw.get("message_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise CanvasError("malformed", "Canvas returned an invalid message count")
    row = {key: text(raw, key) for key in ("subject", "workflow_state", "last_message", "last_message_at", "last_authored_message_at", "context_name")}
    people = [{"id": id_string(p.get("id")), "name": text(p, "full_name") or text(p, "name")} for p in records(raw.get("participants"), "participants")]
    row.update(id=cid, message_count=count, private=raw.get("private"), cannot_reply=raw.get("cannot_reply"), participants=sorted(people, key=lambda p: (len(p["id"]), p["id"])), audience=sorted(ids(raw.get("audience"), "audience"), key=lambda i: (len(i), i)) if raw.get("audience") is not None else None, html_url=f"{reader.origin}/conversations/{cid}")
    return row


def inbox(reader, scope="inbox", course=None, limit=DEFAULT_LIMIT, everything=False):
    if not everything and limit < 1:
        raise CanvasError("input_invalid", "--limit must be at least 1")
    params = [] if scope == "inbox" else [("scope", scope)]
    if course:
        params.append(("filter[]", f"course_{course}"))
    params.append(("per_page", 100 if everything else min(limit, 100)))
    client, rows, seen, pages = reader.client, [], set(), 0
    url, complete = client.url_for(PATH, params), True
    while url:
        if pages >= MAX_PAGES:
            raise CanvasError("page_cap", f"The Inbox has more than {MAX_PAGES} pages and was not completed", pages_read=pages)
        seen.add(url)
        response = client.request("GET", url)
        page = parse_json(response)
        if not isinstance(page, list):
            raise CanvasError("malformed", "An Inbox page was not a JSON array", pages_read=pages)
        rows.extend(summary(reader, raw) for raw in page)
        pages += 1
        following = parse_link_header(response.header("link")).get("next")
        url = client.check_api_url(client.url_for(following)) if following else None
        if url in seen:
            raise CanvasError("pagination_cycle", "The Inbox's next link repeated an earlier page", pages_read=pages)
        if not everything and len(rows) >= limit:
            complete = not url and len(rows) == limit
            rows, url = rows[:limit], None
    if len({row["id"] for row in rows}) != len(rows):
        raise CanvasError("listing_changed", "The Inbox changed while it was listed; run it again")
    return {"scope": scope, "course_id": course, "conversations": rows, "coverage": {"status": "complete" if complete else "limited", "count": len(rows), "pages": pages}}


def message(raw, names, depth=0):
    if not isinstance(raw, dict) or depth > 20:
        raise CanvasError("malformed", "Canvas returned an invalid Inbox message")
    author = id_string(raw.get("author_id"))
    row = {"id": id_string(raw.get("id")), "created_at": text(raw, "created_at"), "author_id": author, "author_name": names.get(author), "body": text(raw, "body"), "generated": raw.get("generated") is True}
    row["attachments"] = [{"id": id_string(a["id"]) if a.get("id") is not None else None, "name": text(a, "display_name") or text(a, "filename"), "content_type": text(a, "content-type")} for a in records(raw.get("attachments"), "message attachments")]
    media = raw.get("media_comment")
    if media is not None and not isinstance(media, dict):
        raise CanvasError("malformed", "Canvas returned an invalid media message")
    row["media"] = {"name": text(media, "display_name"), "type": text(media, "media_type")} if media else None
    row["participant_ids"] = sorted(ids(raw["participating_user_ids"], "message participants"), key=lambda i: (len(i), i)) if raw.get("participating_user_ids") is not None else None
    row["forwarded"] = [message(f, names, depth + 1) for f in records(raw.get("forwarded_messages"), "forwarded messages")]
    return row


def conversation(reader, cid):
    cid = id_string(cid)
    # Canvas marks a conversation read by default when its messages are fetched.
    raw = reader.object(f"{PATH}/{cid}", {"auto_mark_as_read": False})
    row = summary(reader, raw)
    if row["id"] != cid:
        raise CanvasError("malformed", "Canvas returned another conversation")
    if not isinstance(raw.get("messages"), list):
        raise CanvasError("malformed", "Canvas returned no message list")
    names = {p["id"]: p["name"] for p in row["participants"]}
    messages = [message(m, names) for m in raw["messages"]]
    if len({m["id"] for m in messages}) != len(messages):
        raise CanvasError("malformed", "Canvas returned a message twice")
    row["messages"] = sorted(messages, key=lambda m: (m["created_at"] or "", len(m["id"]), m["id"]))
    row["coverage"] = {"status": "complete" if len(messages) >= row["message_count"] else "partial", "messages": len(messages), "message_count": row["message_count"]}
    row["limits"] = ["Attachments and media are listed, not downloaded. Links in messages are not followed.", "A conversation lists only messages visible to this account."]
    return row


def body_text(path):
    try:
        raw = Path(path).read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        raise CanvasError("body_invalid", "The reply file must be readable UTF-8 text") from None
    body = raw.replace("\r\n", "\n").strip("\n")
    if not body.strip() or any(ord(c) < 32 and c not in "\n\t" for c in body):
        raise CanvasError("body_invalid", "The reply must be plain text and not empty")
    return body


def same_text(a, b):
    tidy = lambda value: "\n".join(line.rstrip() for line in (value or "").replace("\r\n", "\n").strip().split("\n"))
    return tidy(a) == tidy(b)


def unresolved(history, account, cid):
    return [row["record_id"] for row in history.rows(account=account, kind="write", outcome="uncertain") if row.get("command") == "reply-conversation" and cid in row.get("target_ids", [])]


class Reply:
    """The reviewed plan for one reply, rebuilt from a fresh read before it is sent."""

    def __init__(self, reader, args, history):
        self.reader, self.client, self.args = reader, reader.client, args
        self.me = self.client.account.user_id
        waiting = unresolved(history, self.client.account.alias, args.conversation)
        if waiting:
            raise CanvasError("reconcile_required", f"An earlier reply to this conversation has an unknown outcome. Read the conversation, then record what happened with history-resolve {waiting[0]} --landed or --not-landed")
        found = self.found = conversation(reader, args.conversation)
        if found["coverage"]["status"] != "complete":
            raise CanvasError("partial", "Canvas did not return every message, so the conversation cannot be checked before replying")
        if found["cannot_reply"] is True:
            raise CanvasError("cannot_reply", "Canvas says this account cannot reply to this conversation")
        names = {p["id"]: p["name"] for p in found["participants"]}
        others = [i for i in found["audience"] or [] if i != self.me]
        if not others or any(i not in names for i in others):
            raise CanvasError("audience_unknown", "Canvas did not identify everyone in the conversation")
        chosen = others if args.to_all else sorted(set(args.to), key=lambda i: (len(i), i))
        if set(chosen) - set(others):
            raise CanvasError("input_invalid", "Every --to person must already be in the conversation")
        self.body = body_text(args.body_file)
        mine = [m for m in found["messages"] if m["author_id"] == self.me and same_text(m["body"], self.body)]
        last_other = max((i for i, m in enumerate(found["messages"]) if m["author_id"] != self.me), default=-1)
        if any(found["messages"].index(m) > last_other for m in mine):
            raise CanvasError("already_posted", "This account already posted this text after the latest message from anyone else")
        self.recipients = chosen
        self.fields = [("body", self.body), ("recipients[]", chosen)]
        latest = found["messages"][-1] if found["messages"] else None
        everyone = set(chosen) == set(others)
        # A message inside a group conversation can be addressed to only some of it.
        reached = None if latest is None or latest["participant_ids"] is None else set(latest["participant_ids"])
        added = [] if reached is None else [i for i in chosen if i not in reached]
        self.plan = {
            "command": "reply-conversation", "account": self.client.account.alias, "author_id": self.me, "context": {"type": "inbox"},
            "target": {"conversation_id": found["id"], "subject": found["subject"], "context_name": found["context_name"], "html_url": found["html_url"], "latest_message": {**{k: latest[k] for k in ("id", "author_id", "author_name", "created_at", "body")}, "reached": None if reached is None else [{"id": i, "name": names.get(i)} for i in latest["participant_ids"]]} if latest else None},
            "recipients": [{"id": i, "name": names[i]} for i in chosen],
            "audience": "everyone else in the conversation" if everyone else f"{len(chosen)} of {len(others)} other people in the conversation",
            "body": self.body,
            "effects": ["Canvas posts the message immediately and notifies the recipients by their own settings; it cannot be unsent through this tool"],
            "warnings": (["This account posted the same text earlier in this conversation"] if mine else []) + (["These recipients did not receive the latest message: " + ", ".join(names[i] or i for i in added)] if added else []) + ([] if everyone else ["People in the conversation who are not listed will not see this message"]),
            "steps": [{"method": "POST", "path": f"{PATH}/{found['id']}/add_message", "recipients": chosen}],
            # Read state, stars and similar flags can change without changing what is being answered.
            "dependencies": digest({"messages": [[m["id"], m["author_id"], m["body"]] for m in found["messages"]], "audience": others, "subject": found["subject"], "private": found["private"], "context": found["context_name"]}),
        }
        self.plan["preview_hash"] = digest({"plan": self.plan})


class ReplyExecutor(Executor):
    def __init__(self, reply, history):
        super().__init__(reply, history)
        self.variables["conversation.id"] = reply.found["id"]

    def confirm(self, response):
        """Find the new message in the conversation itself; Canvas may answer before a queued message exists."""
        reply = self.builder
        rows = records(response.get("messages"), "new message") if isinstance(response, dict) else []
        claimed = str(rows[0].get("id")) if len(rows) == 1 and str(rows[0].get("id")) != "0" else None
        before = {m["id"] for m in reply.found["messages"]}
        for attempt in range(READBACK_TRIES):
            if attempt:
                self.client.sleep(READBACK_PAUSE)
            new = [m for m in conversation(self.reader, reply.found["id"])["messages"] if m["id"] not in before and m["author_id"] == reply.me]
            if claimed and any(m["id"] == claimed and not same_text(m["body"], reply.body) for m in new):
                raise CanvasError("readback_mismatch", "The posted message's text differs from the reviewed reply")
            found = [m for m in new if same_text(m["body"], reply.body) and claimed in (None, m["id"])]
            if len(found) > 1:
                raise CanvasError("readback_mismatch", "The reply appears more than once")
            if found:
                if found[0]["participant_ids"] is not None and set(found[0]["participant_ids"]) != {*reply.recipients, reply.me}:
                    raise CanvasError("readback_mismatch", "The posted message reached a different audience")
                return found[0]
        raise CanvasError("readback_missing", "The reply was not found in the conversation")

    def run(self):
        path = self.builder.plan["steps"][0]["path"]
        result = {"mode": "executed", "preview_hash": self.builder.plan["preview_hash"], "conversation_id": self.builder.found["id"]}
        try:
            with self.history.locked():
                self.history.compress()
                self.journal("started")
                try:
                    response, pending = self.request("POST", path, self.builder.fields)
                    posted = self.confirm(response)
                    self.variables["message.id"] = posted["id"]
                    self.resolved(pending)
                except Exception as error:
                    refused = isinstance(error, CanvasError) and error.status in {400, 401, 403, 404, 409, 422, 429} and self.active_record is not None and self.phase == "sending"
                    if refused:
                        try:
                            self.resolved(self.active_record, "not_landed")
                        except OSError:
                            refused = False
                    kind = error.kind if isinstance(error, CanvasError) else "transport_or_history_error"
                    if refused or not self.sent:
                        return {**result, "outcome": "refused", "writes_sent": self.sent, "error_kind": kind}, 1
                    return {**result, "outcome": "PARTIAL or uncertain", "writes_sent": self.sent, "record_id": self.active_record, "error_kind": kind, "next_action": "Read the conversation before anything else, then record what happened with history-resolve. Do not send again."}, 3
                self.journal("verified")
        except OSError:
            if self.sent:
                return {**result, "outcome": "PARTIAL or uncertain", "writes_sent": self.sent, "error_kind": "history_unwritable"}, 3
            raise CanvasError("history_unwritable", "Write history is unavailable; nothing was sent") from None
        return {**result, "outcome": "verified", "writes_sent": self.sent, "message_id": posted["id"], "posted_at": posted["created_at"], "recipients": self.builder.plan["recipients"]}, 0


def run_reply(reader, args, history):
    if args.execute and (not args.expect or not re.fullmatch(r"[0-9a-f]{64}", args.expect)):
        raise CanvasError("preview_required", "Execution requires the reviewed preview hash in --expect; nothing was sent")
    reply = Reply(reader, args, history)
    if not args.execute:
        return {"mode": "preview", **reply.plan, "writes_sent": 0}, 0
    if args.expect != reply.plan["preview_hash"]:
        raise CanvasError("preview_stale", "The conversation, audience or reply differs from the reviewed plan; nothing was sent")
    return ReplyExecutor(reply, history).run()


def render_message(row, indent=""):
    lines = [f"{indent}### {row['author_name'] or 'User ' + row['author_id']} · {row['created_at'] or 'date not returned'} · Message {row['id']}", *[indent + line for line in (row["body"] or "[No text returned]").split("\n")]]
    lines += [f"{indent}Attachment (not downloaded): {a['name'] or a['id']}" for a in row["attachments"]]
    if row["media"]:
        lines.append(f"{indent}Media (not retrieved): {row['media']['name'] or row['media']['type'] or 'unnamed'}")
    for forwarded in row["forwarded"]:
        lines += [f"{indent}Forwarded:", *render_message(forwarded, indent + "> ")]
    return [*lines, ""]


def render(value):
    if "conversations" in value:
        lines = [f"# Inbox: {value['scope']}", f"Coverage: {value['coverage']['status']}, {value['coverage']['count']} conversations", ""]
        for row in value["conversations"]:
            names = ", ".join(p["name"] or p["id"] for p in row["participants"])
            lines += [f"- {row['id']} · {max(filter(None, (row['last_message_at'], row['last_authored_message_at'])), default='date not returned')} · {row['workflow_state']} · {row['subject'] or '(no subject)'} · {row['context_name'] or 'no course'} · {row['message_count']} messages · {names}"]
        return "\n".join(lines) + "\n"
    lines = [f"# {value['subject'] or '(no subject)'}", value["html_url"], f"Conversation {value['id']} · {value['context_name'] or 'no course'} · {value['workflow_state']}", "People: " + ", ".join(f"{p['name'] or 'unnamed'} ({p['id']})" for p in value["participants"]), f"Coverage: {value['coverage']['status']}, {value['coverage']['messages']} of {value['coverage']['message_count']} messages", ""]
    for row in value["messages"]:
        lines += render_message(row)
    return "\n".join([*lines, *["- " + limit for limit in value["limits"]]]) + "\n"
