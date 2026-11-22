"""Native Outlook reply drafts and guarded saved-draft body edits; never sends."""
import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlsplit

CAPABILITY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAPABILITY_ROOT.parent / "setup-microsoft-services/scripts"))
from runtime_state import location
from bounded_client import Client, Store, digest, identifier

SELECT = "id,subject,body,from,sender,replyTo,toRecipients,ccRecipients,bccRecipients,conversationId,internetMessageId,isDraft,changeKey,webLink,hasAttachments"
PREFER = {'Prefer': 'IdType="ImmutableId", outlook.body-content-type="html"'}
ATTACHMENT_SELECT = "id,name,contentType,size,isInline"
EDIT_KIND = "outlook-draft-body-edit-v1"
EDIT_PRESERVED = ("id", "subject", "from", "sender", "replyTo", "toRecipients", "ccRecipients", "bccRecipients", "conversationId", "internetMessageId", "hasAttachments")


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", value) or len(value) > 254:
        raise ValueError("Supply exact email addresses; display names and groups are not inferred")
    return value.casefold()


def recipients(values):
    result = [address(v["emailAddress"]["address"]) for v in values]
    if len(result) != len(set(result)) or len(result) > 50:
        raise ValueError("Recipient list is duplicated or exceeds 50")
    return sorted(result)


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.hidden += 1
        if tag in ("p", "div", "br", "li", "tr", "hr"): self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li", "tr"): self.parts.append("\n")

    def handle_data(self, value):
        if not self.hidden: self.parts.append(value)


def lines(content):
    p = BodyText(); p.feed(content)
    return [re.sub(r"\s+", " ", line).strip() for line in "".join(p.parts).splitlines() if line.strip()]


def paragraphs(text):
    if not isinstance(text, str) or not text.strip() or len(text) > 30000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text):
        raise ValueError("Use nonempty UTF-8 text up to 30,000 characters without control codes")
    return "".join("<p>" + "<br>".join(html.escape(line) for line in block.split("\n")) + "</p>" for block in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n") if block.strip())


class SignatureHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack = []

    def handle_starttag(self, tag, attrs):
        if tag not in ("p", "div", "br", "b", "strong", "i", "em", "span", "a", "ul", "ol", "li"):
            raise ValueError("Signature HTML supports simple text, paragraphs, emphasis, lists and links only; no images, scripts or remote resources")
        for key, value in attrs:
            if tag != "a" or key != "href" or urlsplit(value or "").scheme not in ("https", "mailto") or any(c in (value or "") for c in "\r\n"):
                raise ValueError("Unsupported signature HTML attribute")
        if tag != "br": self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise ValueError("Signature tags must be balanced and properly nested")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag != "br": self.handle_endtag(tag)
    def handle_comment(self, data): raise ValueError("Signature comments are unsupported")
    def handle_decl(self, data): raise ValueError("Signature declarations are unsupported")


def signature(value, account):
    if not isinstance(value, dict) or set(value) != {"account", "format", "content"} or address(value["account"]) != account:
        raise ValueError("Signature must explicitly identify this sending account")
    content = value["content"]
    if value["format"] == "text": return paragraphs(content)
    if value["format"] != "html" or not isinstance(content, str) or not content.strip() or len(content) > 10000:
        raise ValueError("Use a verified text or bounded HTML signature")
    validator = SignatureHTML(); validator.feed(content); validator.close()
    if validator.stack: raise ValueError("Signature tags must be closed before the quotation")
    if not lines(content): raise ValueError("Signature has no visible content")
    return content


def message_path(message):
    return "/me/messages/" + quote(identifier(message), safe="")


def read_message(client, message):
    value = client.request("GET", message_path(message) + "?$select=" + SELECT, headers=PREFER)
    # Immutable IDs can differ from a caller's ordinary message ID on the first read; all subsequent operations use the returned immutable ID.
    identifier(value.get("id"))
    if not value.get("conversationId") or not value.get("changeKey") or value.get("body", {}).get("contentType", "").casefold() != "html" or len(value["body"].get("content", "")) > 500000:
        raise ValueError("Message identity, revision or bounded HTML body is unavailable")
    return value


def source_state(value):
    return {k: value.get(k) for k in ("id", "subject", "body", "from", "sender", "replyTo", "toRecipients", "ccRecipients", "conversationId", "internetMessageId", "isDraft", "changeKey")}


def audience(source, account, reply_all):
    own = address(account)
    reply = recipients(source.get("replyTo") or [source.get("from", {})])
    if own in reply or source.get("isDraft") is not False:
        raise ValueError("Select a received, non-draft message from another sender")
    to = set(reply)
    cc = set()
    if reply_all:
        to.update(recipients(source.get("toRecipients", [])))
        cc.update(recipients(source.get("ccRecipients", [])))
        to.discard(own); cc.discard(own); cc.difference_update(to)
    if not to or len(to | cc) > 50: raise ValueError("Unsupported reply audience")
    return {"to": sorted(to), "cc": sorted(cc), "bcc": []}


def preview(client, store, message, text, to, cc, signature_data=None, no_signature=False, reply_all=False):
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    source = read_message(client, message)
    expected = audience(source, account, reply_all)
    requested = {"to": sorted(address(v) for v in to), "cc": sorted(address(v) for v in cc), "bcc": []}
    if expected != requested: raise ValueError("Explicit To/CC must match the selected reply intent and source Reply-To; review recipients before creating a draft")
    if (signature_data is None) == (not no_signature): raise ValueError("Supply one verified account signature or explicitly choose --no-signature")
    reply_html = paragraphs(text)
    sig = signature(signature_data, account) if signature_data is not None else ""
    if sig and any(line in lines(reply_html) for line in lines(sig)):
        raise ValueError("New text duplicates a signature line; keep the supplied signature separate")
    plan = store.plan({"kind": "outlook-reply-draft-v1", "alias": client.alias, "identity": identity, "account": account, "source": source_state(source), "sourceHash": digest(source_state(source)), "audience": expected, "replyAll": reply_all, "replyHTML": reply_html, "signatureHTML": sig, "signatureOmitted": no_signature})
    return {"status": "preview", **plan, "attachments": "No new attachments; provider-generated quoted inline attachments may remain", "quote": "The provider-generated reply history will be retained and verified after creation. No signature setting is read or changed.", "manualSendOnly": True}


def check_draft(value, plan):
    if value.get("isDraft") is not True or value.get("conversationId") != plan["source"]["conversationId"] or value.get("bccRecipients"):
        raise ValueError("The returned message is not the expected unsent conversation draft")
    for field, key in (("toRecipients", "to"), ("ccRecipients", "cc")):
        if recipients(value.get(field, [])) != plan["audience"][key]: raise ValueError("Provider draft recipients differ from the preview")
    sender = value.get("from", {}).get("emailAddress", {}).get("address")
    if not sender or address(sender) != plan["account"]: raise ValueError("Draft sender does not match the selected mailbox")


def prefix_body(original, prefix):
    # Preserve the entire provider-generated document, including quote attribution, ordering and formatting. Insert inside its HTML body without reparsing/reformatting it.
    matches = list(re.finditer(r"<body\b[^>]*>", original, re.I))
    if len(matches) > 1: raise ValueError("Ambiguous generated HTML body; inspect the created draft")
    if matches:
        end = matches[0].end(); return original[:end] + prefix + original[end:]
    if re.search(r"<html\b", original, re.I): raise ValueError("Generated HTML has no usable body; inspect the created draft")
    return prefix + original


def verify_saved(saved, plan, created):
    check_draft(saved, plan)
    if saved.get("id") != created["draft"] or saved.get("subject") != created["subject"]:
        raise ValueError("Draft identity/subject changed")
    expected = lines(plan["replyHTML"] + plan["signatureHTML"]) + created["quoteLines"]
    if lines(saved["body"]["content"]) != expected:
        raise ValueError("New paragraphs, signature or quoted history differs from the saved draft")
    # Confirm quoted links/media references survived server normalization as a multiset; their remote content is never fetched.
    links = lambda text: sorted(re.findall(r'\b(?:href|src)\s*=\s*["\']([^"\']*)["\']', text, re.I))
    if links(saved["body"]["content"]) != links(created["originalHTML"] + plan["signatureHTML"]):
        raise ValueError("Quoted/signature resource references changed")
    return {"status": "draft_verified", "draft": saved["id"], "manualSendOnly": True, "webLink": safe_link(saved.get("webLink")), "limits": "Stored paragraphs, recipients, account, conversation and quote content checked; visual rendering and recipient-side threading remain unverified."}


def safe_link(value):
    if not isinstance(value, str): return None
    url = urlsplit(value)
    return value if url.scheme == "https" and url.hostname in ("outlook.office.com", "outlook.office365.com", "outlook.live.com") and not url.username and not url.password and not url.port else None


def draft_etag(value):
    etag = value.get("@odata.etag")
    if not isinstance(etag, str) or not etag or any(c in etag for c in "\r\n"):
        raise ValueError("Missing draft ETag; refuse an unguarded update")
    return etag


def check_edit_target(value, account):
    if value.get("isDraft") is not True:
        raise ValueError("Select an existing unsent draft; sent or received messages cannot be edited")
    # New-message drafts may omit From/Sender until sending. The /me route and verified identity bind the mailbox; an explicit alternate sender is refused.
    for field in ("from", "sender"):
        if value.get(field) and address(value[field]["emailAddress"]["address"]) != account:
            raise ValueError("Draft sender does not match the selected mailbox")
    for field in ("toRecipients", "ccRecipients", "bccRecipients", "replyTo"):
        recipients(value.get(field, []))
    draft_etag(value)


def attachment_state(client, message):
    value = client.request("GET", message_path(message) + "/attachments?$select=" + ATTACHMENT_SELECT + "&$top=100", headers=PREFER)
    items = value.get("value")
    if value.get("@odata.nextLink") or not isinstance(items, list) or len(items) > 100:
        raise ValueError("Incomplete attachment metadata; inspect the draft instead of editing it")
    result = []
    for item in items:
        if not all(k in item for k in ATTACHMENT_SELECT.split(",")):
            raise ValueError("Missing attachment metadata; inspect the draft instead of editing it")
        identifier(item["id"])
        result.append({k: item[k] for k in ATTACHMENT_SELECT.split(",")})
    if len({item["id"] for item in result}) != len(result):
        raise ValueError("Duplicate attachment identity")
    return sorted(result, key=lambda item: item["id"])


def edit_snapshot(client, message, account):
    value = read_message(client, message)
    check_edit_target(value, account)
    attachments = attachment_state(client, value["id"])
    fresh = read_message(client, value["id"])
    if fresh != value:
        raise ValueError("Draft changed while reading; preview again after editing stops")
    return {"message": value, "attachments": attachments}


def preview_edit(client, store, message, text):
    proposed = paragraphs(text)
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    current = edit_snapshot(client, message, account)
    # Replacing a rich body would silently discard signatures, quotations and inline resource placement. Keep this first surface explicitly plain-text-only.
    original = current["message"]["body"]["content"]
    if re.search(r"<(?:img|table|a|blockquote)\b|\b(?:src|href)\s*=", original, re.I) or any(a["isInline"] for a in current["attachments"]):
        raise ValueError("Rich or inline content requires a formatting-preserving editor; this command replaces the whole body with plain text")
    plan = store.plan({"kind": EDIT_KIND, "alias": client.alias, "identity": identity, "account": account, "current": current, "currentHash": digest(current), "bodyHTML": proposed})
    return {"status": "preview", **plan, "manualSendOnly": True, "replacement": "Entire body, including any signature and quoted text; supply all text to retain. Subject, recipients and attachments are unchanged."}


def verify_edit(client, plan):
    if client.identity() != plan["identity"]: raise ValueError("Mailbox identity changed")
    saved = edit_snapshot(client, plan["current"]["message"]["id"], plan["account"])
    before = plan["current"]["message"]
    for key in EDIT_PRESERVED:
        if saved["message"].get(key) != before.get(key):
            raise ValueError("Draft metadata changed: " + key)
    if saved["attachments"] != plan["current"]["attachments"]:
        raise ValueError("Draft attachment metadata changed")
    if lines(saved["message"]["body"]["content"]) != lines(plan["bodyHTML"]):
        raise ValueError("Saved draft text or paragraph boundaries differ from the preview")
    return {"status": "draft_edit_verified", "draft": before["id"], "manualSendOnly": True, "webLink": safe_link(saved["message"].get("webLink")), "limits": "Stored text, unsent state, mailbox, metadata and attachment identities/sizes checked; attachment bytes and visual rendering are not certified."}


def apply_edit(client, store, operation, plan):
    if store.dispatched(operation): raise ValueError("Already dispatched; inspect draft-status/draft-verify before another edit")
    client.require_write()
    if client.identity() != plan["identity"]: raise ValueError("Mailbox identity changed")
    current = edit_snapshot(client, plan["current"]["message"]["id"], plan["account"])
    if digest(current) != plan["currentHash"]:
        raise ValueError("Draft changed since preview; preserve the newer draft and preview again")
    draft = current["message"]
    store.dispatch(operation, {"status": "uncertain_after_dispatch", "draft": draft["id"], "hash": plan["hash"]})
    result = {"operation": operation, "draft": draft["id"], "status": "uncertain_after_dispatch", "manualSendOnly": True, "replayAllowed": False}
    try:
        client.request("PATCH", message_path(draft["id"]), {"body": {"contentType": "HTML", "content": plan["bodyHTML"]}}, {**PREFER, "If-Match": draft_etag(draft)})
        result.update(verify_edit(client, plan))
    except Exception:
        result["detail"] = "The saved draft may have changed. Use draft-status/draft-verify; never retry automatically or overwrite intervening edits."
    store.receipt(operation, result)
    return result


def apply(client, store, operation, expected_hash, execute, allow_draft):
    if not execute or not allow_draft: raise ValueError("Require --execute and --allow-draft for this authorized manual-send draft")
    plan = store.load(operation, expected_hash)
    if plan.get("kind") == EDIT_KIND and plan.get("alias") == client.alias:
        return apply_edit(client, store, operation, plan)
    if plan.get("kind") != "outlook-reply-draft-v1" or plan.get("alias") != client.alias: raise ValueError("Wrong operation/account")
    if store.dispatched(operation): raise ValueError("Already dispatched; inspect draft-status/draft-verify and Outlook Drafts. Never recreate automatically.")
    client.require_write()
    if client.identity() != plan["identity"]: raise ValueError("Mailbox identity changed")
    source = read_message(client, plan["source"]["id"])
    if digest(source_state(source)) != plan["sourceHash"]: raise ValueError("Source changed since preview; no draft was created")
    store.dispatch(operation, {"status": "uncertain_after_dispatch", "source": source["id"], "hash": plan["hash"]})
    result = {"operation": operation, "status": "uncertain_after_dispatch", "manualSendOnly": True, "replayAllowed": False}
    try:
        endpoint = message_path(source["id"]) + ("/createReplyAll" if plan["replyAll"] else "/createReply")
        response = client.request("POST", endpoint, {}, PREFER)
        draft_id = identifier(response.get("id"))
        # Retain the returned identity before any subsequent read can fail.
        store.receipt(operation, {"draft": draft_id}, ".created.json")
        result["draft"] = draft_id
        draft = read_message(client, draft_id); check_draft(draft, plan)
        if draft["id"] != draft_id: raise ValueError("Generated draft identity changed")
        original = draft["body"]["content"]
        quote_lines = lines(original)
        source_lines = lines(source["body"]["content"])
        remaining = iter(quote_lines)
        if not source_lines or not quote_lines or not all(any(candidate == line for candidate in remaining) for line in source_lines):
            raise ValueError("Generated reply does not retain the source body; inspect the created draft")
        created = {"draft": draft_id, "subject": draft.get("subject"), "quoteLines": quote_lines, "originalHTML": original}
        store.receipt(operation, created, ".quote.json")
        updated = prefix_body(original, plan["replyHTML"] + plan["signatureHTML"])
        fresh = read_message(client, draft_id)
        if fresh != draft: raise ValueError("Draft changed after creation; preserve the user's changes")
        etag = fresh.get("@odata.etag")
        if not isinstance(etag, str) or not etag or any(c in etag for c in "\r\n"):
            raise ValueError("Missing draft ETag; refuse an unguarded update and inspect the created draft")
        client.request("PATCH", message_path(draft_id), {"body": {"contentType": "HTML", "content": updated}}, {**PREFER, "If-Match": etag})
        result.update(verify_saved(read_message(client, draft_id), plan, created))
    except Exception:
        result["detail"] = "A reply draft may exist or be partially populated. Inspect the receipt and Outlook Drafts; never recreate, overwrite user edits or delete it automatically."
    store.receipt(operation, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); subs = parser.add_subparsers(dest="command", required=True)
    p = subs.add_parser("reply-draft"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--body-file", required=True)
    p.add_argument("--to", action="append", required=True); p.add_argument("--cc", action="append", default=[]); p.add_argument("--reply-all", action="store_true")
    signatures = p.add_mutually_exclusive_group(required=True); signatures.add_argument("--signature-file"); signatures.add_argument("--no-signature", action="store_true")
    p = subs.add_parser("edit-draft"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--body-file", required=True)
    for command in ("draft-apply", "draft-status", "draft-verify"):
        p = subs.add_parser(command); p.add_argument("alias"); p.add_argument("--plan", required=True)
        if command == "draft-apply": p.add_argument("--hash", required=True); p.add_argument("--execute", action="store_true"); p.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args(argv); client = Client(args.alias, "mail"); store = Store(location("mail") / ".draft-state", args.alias)
    if args.command == "reply-draft":
        data = json.loads(Path(args.signature_file).read_text()) if args.signature_file else None
        result = preview(client, store, args.message, Path(args.body_file).read_text(), args.to, args.cc, data, args.no_signature, args.reply_all)
    elif args.command == "edit-draft": result = preview_edit(client, store, args.message, Path(args.body_file).read_text(encoding="utf-8"))
    elif args.command == "draft-apply": result = apply(client, store, args.plan, args.hash, args.execute, args.allow_draft)
    elif args.command == "draft-status": result = store.status(args.plan)
    else:
        plan = store.load(args.plan)
        if plan.get("alias") != args.alias or client.identity() != plan["identity"]: raise ValueError("Mailbox mismatch")
        if plan.get("kind") == EDIT_KIND:
            result = verify_edit(client, plan)
        else:
            created = store.read(store.path(args.plan, ".quote.json"))
            result = verify_saved(read_message(client, created["draft"]), plan, created)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("status") == "uncertain_after_dispatch" else 0


if __name__ == "__main__":
    try: sys.exit(main())
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({"status": "refused_or_unverified", "detail": str(exc)})); sys.exit(1)
