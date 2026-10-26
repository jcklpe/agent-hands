#!/usr/bin/env python3
"""Bounded Slack messages operations; writes require --execute."""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "setup-slack" / "scripts"))
import slack_auth as support

def send(acct, channel, text, thread_ts):
    support.verify_identity(acct)
    sent = support.call(acct, "chat.postMessage", {"channel": channel, "text": text, "thread_ts": thread_ts}, json_body=True)
    ts = sent.get("ts")
    channel = sent.get("channel") or channel
    posted = ((sent.get("message") or {}).get("user"))
    if posted and posted != acct["user_id"]:
        raise support.SlackError(f"Posted message is attributed to {posted}, not {acct['user_id']}; check the token type")
    link = support.call(acct, "chat.getPermalink", {"channel": channel, "message_ts": ts}).get("permalink", "")
    print(f"Sent as {acct['user_id']} to {channel} at ts {ts}")
    if link:
        print(f"Permalink: {link}")


def cmd_channels(args):
    acct = support.account(args.alias)
    channels = support.paged(acct, "conversations.list", {"types": "public_channel,private_channel", "exclude_archived": "true", "limit": 200}, "channels")
    query = (args.query or "").lower()
    for ch in sorted(channels, key=lambda c: c.get("name", "")):
        if query and query not in ch.get("name", "").lower():
            continue
        member = "member" if ch.get("is_member") else "not a member"
        print(f"- #{ch.get('name')} | id: {ch.get('id')} | {'private' if ch.get('is_private') else 'public'} | {member}")
    return 0


def conversation_types(value):
    types = value.split(",")
    if not types or any(t not in ("public_channel", "private_channel", "im", "mpim") for t in types):
        raise argparse.ArgumentTypeError("types must be comma-separated public_channel,private_channel,im,mpim")
    return value


def cmd_conversations(args):
    acct = support.account(args.alias)
    support.verify_identity(acct)
    conversations = support.paged(acct, "conversations.list", {"types": args.types, "exclude_archived": "false" if args.archived else "true", "limit": 200}, "channels")
    selected = []
    for ch in conversations:
        if args.user:
            if ch.get("is_im"):
                if ch.get("user") != args.user:
                    continue
            elif ch.get("is_mpim"):
                members = support.paged(acct, "conversations.members", {"channel": ch["id"], "limit": 200}, "members")
                if args.user not in members:
                    continue
            else:
                continue
        if ch.get("is_im"):
            label = "DM with " + ch.get("user", "?")
        elif ch.get("is_mpim"):
            label = "group DM " + ch.get("name", "")
        else:
            label = "#" + ch.get("name", "?")
        selected.append(f"- {label} | id: {ch.get('id')} | archived: {bool(ch.get('is_archived'))}")
    print("Existing visible conversations; listing never opens or joins a conversation.")
    print("\n".join(selected) if selected else "No matching visible conversations.")
    return 0


def print_history_message(message):
    suffix = f" | thread: {message['thread_ts']}" if message.get("thread_ts") else ""
    if message.get("reply_count"):
        suffix += f" | replies: {message['reply_count']}"
    print(f"- [{message.get('ts')}] {message.get('user') or message.get('bot_id') or '?'}{suffix}: {message.get('text', '')}")


def cmd_history(args):
    acct = support.account(args.alias)
    support.verify_identity(acct)
    page = support.call(acct, "conversations.history", {"channel": args.channel, "limit": args.limit, "cursor": args.cursor, "oldest": args.oldest, "latest": args.latest, "inclusive": "true" if args.inclusive else "false"})
    cursor = ((page.get("response_metadata") or {}).get("next_cursor") or "").strip()
    if page.get("has_more") and not cursor:
        raise support.SlackError("conversations.history: more results reported without a cursor; narrow the time range")
    print(f"History in {args.channel}, newest first; one page, up to {args.limit} messages. Thread replies require `thread`.")
    for message in page.get("messages") or []:
        print_history_message(message)
    print(f"Next cursor: {cursor}" if cursor else "End of accessible history in the requested time range.")
    return 0


def cmd_search(args):
    if not args.query.strip():
        raise support.SlackError("search needs a nonempty query")
    acct = support.account(args.alias)
    support.verify_identity(acct)
    result = support.call(acct, "search.messages", {"query": args.query, "count": args.limit, "page": args.page, "sort": "timestamp", "sort_dir": "desc", "highlight": "false"}).get("messages") or {}
    paging = result.get("paging") or {}
    pagination = result.get("pagination") or {}
    total = result.get("total", paging.get("total", pagination.get("total_count", "unknown")))
    pages = paging.get("pages", pagination.get("page_count", "unknown"))
    print(f"Search results newest first: page {args.page} of {pages}; total {total}. Search visibility and Slack search filters apply.")
    for message in result.get("matches") or []:
        channel = message.get("channel") or {}
        print(f"Conversation: {channel.get('name', '?')} ({channel.get('id', '?')})")
        print_history_message(message)
        if message.get("permalink"):
            print(f"Permalink: {message['permalink']}")
    return 0


def search_page(value):
    value = int(value)
    if not 1 <= value <= 100:
        raise argparse.ArgumentTypeError("page must be between 1 and 100")
    return value


def cmd_permalink(args):
    acct = support.account(args.alias)
    support.verify_identity(acct)
    link = support.call(acct, "chat.getPermalink", {"channel": args.channel, "message_ts": args.ts}).get("permalink")
    if not link:
        raise support.SlackError("chat.getPermalink returned no permalink")
    print(link)
    return 0


def cmd_users(args):
    acct = support.account(args.alias)
    users = support.paged(acct, "users.list", {"limit": 200}, "members")
    query = (args.query or "").lower()
    for user in sorted(users, key=lambda u: (u.get("profile") or {}).get("real_name", "")):
        if user.get("deleted") or user.get("is_bot"):
            continue
        profile = user.get("profile") or {}
        names = " ".join(filter(None, [profile.get("real_name"), profile.get("display_name"), user.get("name")]))
        if query and query not in names.lower():
            continue
        print(f"- {profile.get('real_name') or user.get('name')} | display: {profile.get('display_name') or '-'} | id: {user.get('id')}")
    return 0


def cmd_thread(args):
    acct = support.account(args.alias)
    if args.url:
        channel, ts = support.parse_message_url(args.url)
    elif args.channel and args.ts:
        channel, ts = args.channel, args.ts
    else:
        raise support.SlackError("thread needs a message URL, or --channel ID --ts TS")
    messages = support.paged(acct, "conversations.replies", {"channel": channel, "ts": ts, "limit": 200}, "messages")
    print(f"Thread {ts} in {support.channel_label(acct, channel)}")
    for message in messages:
        print(f"- [{message.get('ts')}] {message.get('user') or message.get('bot_id') or '?'}: {message.get('text', '')}")
    return 0


def cmd_post(args):
    acct = support.account(args.alias)
    text = support.read_text(args)
    channel, thread_ts = args.channel, args.thread_ts
    if args.url:
        channel, thread_ts = support.parse_message_url(args.url)
    if not channel:
        raise support.SlackError("post needs --channel ID (or --url of a message to reply in its thread)")
    support.print_message_plan("reply" if thread_ts else "post", acct, support.channel_label(acct, channel), thread_ts, text)
    if not args.execute:
        print("DRY RUN: nothing was sent. Re-run with --execute after approval.")
        return 0
    send(acct, channel, text, thread_ts)
    return 0


def cmd_dm(args):
    acct = support.account(args.alias)
    text = support.read_text(args)
    if not re.fullmatch(r"[UW][A-Z0-9]+", args.user):
        raise support.SlackError("--user needs a Slack user ID (U...); resolve names with the Slack messaging skill’s users command")
    support.print_message_plan("direct message", acct, f"DM with {support.user_label(acct, args.user)}", None, text)
    if not args.execute:
        print("DRY RUN: nothing was sent. Re-run with --execute after approval.")
        return 0
    support.verify_identity(acct)
    channel = (support.call(acct, "conversations.open", {"users": args.user}).get("channel") or {}).get("id")
    if not channel:
        raise support.SlackError("conversations.open returned no channel")
    send(acct, channel, text, None)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog="slack-messages", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accounts").set_defaults(func=support.cmd_accounts)
    p = sub.add_parser("whoami"); p.add_argument("alias"); p.set_defaults(func=support.cmd_whoami)
    p = sub.add_parser("channels"); p.add_argument("alias"); p.add_argument("query", nargs="?"); p.set_defaults(func=cmd_channels)
    p = sub.add_parser("conversations", help="list existing channels, DMs and group DMs without opening or joining")
    p.add_argument("alias"); p.add_argument("--types", type=conversation_types, default="public_channel,private_channel,im,mpim"); p.add_argument("--user", help="filter existing DMs/group DMs by verified user ID"); p.add_argument("--archived", action="store_true"); p.set_defaults(func=cmd_conversations)
    p = sub.add_parser("history", help="read one page of conversation history; use thread for replies")
    p.add_argument("alias"); p.add_argument("--channel", required=True); p.add_argument("--limit", type=support.positive_limit, default=50); p.add_argument("--cursor"); p.add_argument("--oldest"); p.add_argument("--latest"); p.add_argument("--inclusive", action="store_true"); p.set_defaults(func=cmd_history)
    p = sub.add_parser("search", help="read one page of message search; requires existing search:read scope")
    p.add_argument("alias"); p.add_argument("query"); p.add_argument("--limit", type=support.positive_limit, default=50); p.add_argument("--page", type=search_page, default=1); p.set_defaults(func=cmd_search)
    p = sub.add_parser("permalink", help="get Slack's permalink for an existing message")
    p.add_argument("alias"); p.add_argument("--channel", required=True); p.add_argument("--ts", required=True); p.set_defaults(func=cmd_permalink)
    p = sub.add_parser("users"); p.add_argument("alias"); p.add_argument("query", nargs="?"); p.set_defaults(func=cmd_users)
    p = sub.add_parser("thread"); p.add_argument("alias"); p.add_argument("url", nargs="?"); p.add_argument("--channel"); p.add_argument("--ts"); p.set_defaults(func=cmd_thread)
    for name in ("post", "reply"):
        p = sub.add_parser(name); p.add_argument("alias"); p.add_argument("--channel"); p.add_argument("--thread-ts"); p.add_argument("--url", help="message URL; replies in its thread")
        p.add_argument("--text"); p.add_argument("--text-file"); p.add_argument("--execute", action="store_true"); p.set_defaults(func=cmd_post)
    p = sub.add_parser("dm"); p.add_argument("alias"); p.add_argument("--user", required=True); p.add_argument("--text"); p.add_argument("--text-file"); p.add_argument("--execute", action="store_true"); p.set_defaults(func=cmd_dm)
    return parser


def main(argv=None, *, load_config=True):
    args = build_parser().parse_args(argv)
    try:
        if load_config:
            support.load_env()
        return args.func(args)
    except (support.SlackError, OSError) as exc:
        return support.fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
