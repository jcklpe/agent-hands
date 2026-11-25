"""Native unsent Outlook drafts, bounded file attachments and guarded body edits; never sends."""
import argparse
import base64
import hashlib
import mimetypes
from decimal import Decimal
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
SIGNATURE_EDIT_KIND = "outlook-draft-signature-style-v1"
FRAGMENT_EDIT_KIND = "outlook-draft-fragment-edit-v1"
ATTACH_KIND = "outlook-draft-attachments-v1"
NEW_KIND = "outlook-new-draft-v1"
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


COLORS = dict(zip("black silver gray white maroon red purple fuchsia green lime olive yellow navy blue teal aqua".split(), "000000 c0c0c0 808080 ffffff 800000 ff0000 800080 ff00ff 008000 00ff00 808000 ffff00 000080 0000ff 008080 00ffff".split()))


def css_color(value):
    value = value.strip().lower()
    if value in COLORS: return "#" + COLORS[value]
    if re.fullmatch(r"#[0-9a-f]{3}", value): return "#" + "".join(c * 2 for c in value[1:])
    if re.fullmatch(r"#[0-9a-f]{6}", value): return value
    rgb = re.fullmatch(r"rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)", value)
    if rgb and all(int(c) <= 255 for c in rgb.groups()): return "#" + "".join(f"{int(c):02x}" for c in rgb.groups())
    raise ValueError("Signature colors must use a basic color name, hex or integer rgb()")


def css_length(value, maximum):
    match = re.fullmatch(r"(\d{1,2}(?:\.\d{1,3})?)(px|pt)?", value.strip().lower())
    if match:
        number = Decimal(match[1]) * 4 / 3 if match[2] == "pt" else Decimal(match[1])
        if 0 <= number <= maximum and (match[2] or number == 0): return str(number.normalize())
    raise ValueError("Signature spacing must be 0–48px and border widths 0–4px (or equivalent pt)")


def signature_styles(value, strict=True):
    """Validate a small CSS vocabulary; project equivalent provider CSS for readback."""
    result = {}; seen = set()
    if not isinstance(value, str) or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", value):
        if strict: raise ValueError("Invalid signature style")
        return result
    for declaration in value.split(";"):
        if not declaration.strip(): continue
        key, separator, val = declaration.partition(":"); key = key.strip().lower(); val = val.strip().lower()
        try:
            if not separator or key in seen: raise ValueError("Malformed or duplicate signature style")
            seen.add(key)
            if key == "color": result[key] = css_color(val)
            elif key in ("margin-top", "margin-bottom", "padding-top", "padding-bottom"):
                result[key] = css_length(val, 48)
            elif key in ("border-top", "border-bottom"):
                border = re.fullmatch(r"(\S+)\s+solid\s+(.+)", val)
                if not border: raise ValueError("Signature borders must be a width, solid, and a color")
                result.update({key + "-width": css_length(border[1], 4), key + "-style": "solid", key + "-color": css_color(border[2])})
            elif not strict and re.fullmatch(r"border-(?:top|bottom)-(?:width|style|color)", key):
                if key.endswith("-width"): result[key] = css_length(val, 4)
                elif key.endswith("-color"): result[key] = css_color(val)
                elif val == "solid": result[key] = val
                else: raise ValueError("Unsupported border style")
            else: raise ValueError("Signature styles support color, top/bottom borders, and top/bottom margin/padding only")
        except ValueError:
            if strict: raise
            if key in seen and (key == "color" or key.startswith(("border-", "margin-", "padding-"))): return {}
    return result


class SignatureHTML(HTMLParser):
    def __init__(self, existing=False):
        super().__init__(convert_charrefs=True); self.stack = []; self.existing = existing

    def handle_starttag(self, tag, attrs):
        if tag not in ("p", "div", "br", "b", "strong", "i", "em", "span", "a", "ul", "ol", "li"):
            raise ValueError("Signature HTML supports simple text, paragraphs, emphasis, lists and links only; no images, scripts or remote resources")
        if self.existing:
            if tag != "br": self.stack.append(tag)
            return
        if len({key for key, _ in attrs}) != len(attrs): raise ValueError("Duplicate signature HTML attribute")
        for key, value in attrs:
            if key == "style":
                signature_styles(value)
            elif tag != "a" or key != "href" or urlsplit(value or "").scheme not in ("https", "mailto") or any(c in (value or "") for c in "\r\n"):
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


class StyledContent(HTMLParser):
    """Anchor styles to visible character ranges, so quoted styles cannot satisfy new ones."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.stack = []; self.position = 0; self.records = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"): self.hidden += 1
        styles = signature_styles(dict(attrs).get("style", ""), strict=False)
        if tag in ("br", "hr", "img", "meta", "link", "input", "area", "base", "col", "embed", "param", "source", "track", "wbr"):
            if styles: self.records.append((self.position, self.position, styles))
        else: self.stack.append((tag, self.position, styles))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"): self.hidden = max(0, self.hidden - 1)
        if self.stack and self.stack[-1][0] == tag:
            _, start, styles = self.stack.pop()
            if styles: self.records.append((start, self.position, styles))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs); self.handle_endtag(tag)

    def handle_data(self, value):
        if not self.hidden: self.position += len(re.sub(r"\s+", "", value))


def verify_styles(saved, expected, offset=0):
    wanted = StyledContent(); wanted.feed(expected); wanted.close()
    if not wanted.records: return
    actual = StyledContent(); actual.feed(saved); actual.close()
    for start, end, styles in wanted.records:
        start += offset; end += offset
        retained = {}
        for a, b, values in actual.records:
            if (a, b) == (start, end): retained.update(values)
        if any(retained.get(key) != value for key, value in styles.items()):
            raise ValueError("Saved signature styles differ from the preview; inspect the draft without replaying")


def resource_links(content):
    return sorted(re.findall(r'\b(?:href|src)\s*=\s*["\']([^"\']*)["\']', content, re.I))


class ElementStarts(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True); self.starts = set(); self.offsets = [0]
        self.offsets.extend(match.end() for match in re.finditer("\n", content))
        self.feed(content); self.close()

    def handle_starttag(self, tag, attrs):
        line, column = self.getpos(); self.starts.add(self.offsets[line - 1] + column)

    handle_startendtag = handle_starttag


def body_fragment(content, existing=False):
    if not isinstance(content, str) or not content.startswith("<") or not content.endswith(">") or len(content) > 30000 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", content):
        raise ValueError("Select a nonempty balanced body fragment up to 30,000 characters, beginning and ending at element boundaries")
    try:
        validator = SignatureHTML(existing=existing); validator.feed(content); validator.close()
        if validator.stack or not lines(content): raise ValueError("Body fragment must be balanced and contain visible text")
    except ValueError as exc:
        raise ValueError(str(exc).replace("Signature", "Body fragment").replace("signature", "body fragment")) from exc
    return content


class HTMLStructure(HTMLParser):
    """Compare stored HTML without depending on attribute order or inter-tag newlines."""
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, content):
        super().__init__(convert_charrefs=True); self.tokens = []
        self.feed(content); self.close()

    def handle_starttag(self, tag, attrs):
        self.tokens.append(("start", tag, sorted(attrs, key=lambda pair: pair[0])))

    def handle_endtag(self, tag):
        if tag not in self.VOID: self.tokens.append(("end", tag))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs); self.handle_endtag(tag)

    def handle_data(self, data):
        if data.strip(): self.tokens.append(("text", re.sub(r"\s+", " ", data)))

    def handle_comment(self, data): self.tokens.append(("comment", data))
    def handle_decl(self, data): self.tokens.append(("declaration", data))
    def unknown_decl(self, data): self.tokens.append(("declaration", data))
    def handle_pi(self, data): self.tokens.append(("instruction", data))


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


def preview_new(client, store, subject, text, to, cc, signature_data=None, no_signature=False):
    if not subject.strip() or len(subject) > 255 or any(ord(c) < 32 for c in subject):
        raise ValueError("Supply a nonempty subject of at most 255 characters without control characters")
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    target = {"to": [address(v) for v in to], "cc": [address(v) for v in cc], "bcc": []}
    all_recipients = target["to"] + target["cc"]
    if not target["to"] or len(all_recipients) > 50 or len(set(all_recipients)) != len(all_recipients):
        raise ValueError("Supply one to fifty unique explicit recipients")
    if (signature_data is None) == (not no_signature):
        raise ValueError("Supply one verified account signature or explicitly choose --no-signature")
    reply_html = paragraphs(text)
    sig = signature(signature_data, account) if signature_data is not None else ""
    if sig and any(line in lines(reply_html) for line in lines(sig)):
        raise ValueError("New text duplicates a signature line; keep the supplied signature separate")
    plan = store.plan({"kind": NEW_KIND, "alias": client.alias, "identity": identity, "account": account, "subject": subject, "audience": target, "bodyHTML": reply_html + sig})
    return {"status": "preview", **plan, "manualSendOnly": True}


def verify_new(client, plan, draft_id):
    saved = read_message(client, draft_id); check_edit_target(saved, plan["account"])
    if saved["id"] != draft_id or saved.get("subject") != plan["subject"]:
        raise ValueError("New draft identity or subject changed")
    for field, key in (("toRecipients", "to"), ("ccRecipients", "cc"), ("bccRecipients", "bcc")):
        if recipients(saved.get(field, [])) != sorted(plan["audience"][key]):
            raise ValueError("New draft recipients differ from the preview")
    if lines(saved["body"]["content"]) != lines(plan["bodyHTML"]) or resource_links(saved["body"]["content"]) != resource_links(plan["bodyHTML"]):
        raise ValueError("New draft content differs from the preview")
    verify_styles(saved["body"]["content"], plan["bodyHTML"])
    return {"status": "draft_verified", "draft": draft_id, "manualSendOnly": True, "webLink": safe_link(saved.get("webLink"))}


def apply_new(client, store, operation, plan):
    if store.dispatched(operation):
        raise ValueError("Already dispatched; inspect draft-status/draft-verify. Never recreate automatically.")
    client.require_write()
    if client.identity() != plan["identity"]: raise ValueError("Mailbox identity changed")
    payload = {"subject": plan["subject"], "body": {"contentType": "HTML", "content": plan["bodyHTML"]}, "toRecipients": [{"emailAddress": {"address": value}} for value in plan["audience"]["to"]], "ccRecipients": [{"emailAddress": {"address": value}} for value in plan["audience"]["cc"]]}
    store.dispatch(operation, {"status": "uncertain_after_dispatch", "hash": plan["hash"]})
    result = {"operation": operation, "status": "uncertain_after_dispatch", "manualSendOnly": True, "replayAllowed": False}
    try:
        response = client.request("POST", "/me/messages", payload, PREFER)
        draft_id = identifier(response.get("id"))
        store.receipt(operation, {"draft": draft_id}, ".created.json")
        result["draft"] = draft_id
        result.update(verify_new(client, plan, draft_id))
    except Exception:
        result["detail"] = "A draft may exist. Inspect draft-status and Outlook Drafts; never recreate automatically."
    store.receipt(operation, result)
    return result


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
    if resource_links(saved["body"]["content"]) != resource_links(created["originalHTML"] + plan["signatureHTML"]):
        raise ValueError("Quoted/signature resource references changed")
    verify_styles(saved["body"]["content"], plan["replyHTML"] + plan["signatureHTML"])
    return {"status": "draft_verified", "draft": saved["id"], "manualSendOnly": True, "webLink": safe_link(saved.get("webLink")), "limits": "Stored paragraphs, supplied signature styles, recipients, account, conversation and quote content checked; visual rendering and recipient-side threading remain unverified."}


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


def local_attachment(filename):
    path = Path(filename).expanduser().resolve(strict=True)
    if not path.is_file() or path.stat().st_size >= 3_000_000:
        raise ValueError("Select a regular local file smaller than 3 MB")
    if any(ord(c) < 32 for c in path.name) or path.name in ("", ".", ".."):
        raise ValueError("Use a file with a safe attachment name")
    with path.open("rb") as source:
        content = source.read(3_000_000)
    if len(content) >= 3_000_000:
        raise ValueError("Attachment grew beyond the 3 MB limit")
    info = {"path": str(path), "name": path.name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest(), "contentType": mimetypes.guess_type(path.name)[0] or "application/octet-stream"}
    return info, content


def preview_attachments(client, store, message, filenames):
    if not 1 <= len(filenames) <= 10:
        raise ValueError("Select one to ten local files")
    files = [local_attachment(name)[0] for name in filenames]
    if sum(f["size"] for f in files) > 10_000_000 or len({f["name"].casefold() for f in files}) != len(files):
        raise ValueError("Attachment names must be unique and combined size at most 10 MB")
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    current = edit_snapshot(client, message, account)
    if len(current["attachments"]) + len(files) > 100 or {f["name"].casefold() for f in files} & {a["name"].casefold() for a in current["attachments"]}:
        raise ValueError("An attachment name already exists or the inventory would exceed 100; inspect the draft")
    plan = store.plan({"kind": ATTACH_KIND, "alias": client.alias, "identity": identity, "account": account, "current": current, "currentHash": digest(current), "files": files})
    return {"status": "preview", **plan, "manualSendOnly": True, "limits": "Files are added sequentially. A partial or uncertain upload is never automatically retried. Keep this draft closed until verification finishes."}


def verify_attachments(client, plan, files=None):
    before = plan["current"]
    saved = edit_snapshot(client, before["message"]["id"], plan["account"])
    for field in (*EDIT_PRESERVED, "body"):
        if field != "hasAttachments" and saved["message"].get(field) != before["message"].get(field):
            raise ValueError("Draft body or metadata changed during attachment upload")
    existing = {a["id"]: a for a in before["attachments"]}
    actual = {a["id"]: a for a in saved["attachments"]}
    if any(actual.get(key) != value for key, value in existing.items()):
        raise ValueError("An existing attachment changed")
    added = [a for a in saved["attachments"] if a["id"] not in existing]
    expected = plan["files"] if files is None else files
    if len(added) != len(expected):
        raise ValueError("Attachment inventory is incomplete or has unexpected additions; inspect before any further upload")
    for item in expected:
        matches = [a for a in added if a["name"] == item["name"] and a["isInline"] is False]
        if len(matches) != 1:
            raise ValueError("Uploaded attachment name is missing or ambiguous")
        # contentBytes belongs to fileAttachment, not the base attachment type; Graph rejects it in a base-resource $select. Read the exact created attachment and verify its derived type before decoding.
        attachment = client.request("GET", message_path(before["message"]["id"]) + "/attachments/" + quote(matches[0]["id"], safe=""), headers=PREFER)
        if attachment.get("id") != matches[0]["id"] or attachment.get("@odata.type") != "#microsoft.graph.fileAttachment":
            raise ValueError("Uploaded attachment identity/type differs")
        content = base64.b64decode(attachment.get("contentBytes", ""), validate=True)
        if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Uploaded attachment bytes differ from the preview")
    if read_message(client, before["message"]["id"]) != saved["message"]:
        raise ValueError("Draft changed during attachment verification")
    return saved


def attachment_result(saved):
    return {"status": "draft_attachments_verified", "draft": saved["message"]["id"], "manualSendOnly": True, "webLink": safe_link(saved["message"].get("webLink")), "attachments": saved["attachments"]}


def reconcile_attachments(client, plan):
    existing = {a["id"] for a in plan["current"]["attachments"]}
    actual = attachment_state(client, plan["current"]["message"]["id"])
    names = {a["name"] for a in actual if a["id"] not in existing}
    present = [f for f in plan["files"] if f["name"] in names]
    saved = verify_attachments(client, plan, present)
    result = attachment_result(saved)
    missing = [f["name"] for f in plan["files"] if f["name"] not in names]
    if missing:
        result.update(status="draft_attachments_partial", missing=missing, replayAllowed=False)
    return result


def apply_attachments(client, store, operation, plan):
    if store.dispatched(operation):
        raise ValueError("Already dispatched; use draft-status/draft-verify and inspect partial uploads. Never replay automatically.")
    client.require_write()
    if client.identity() != plan["identity"]:
        raise ValueError("Mailbox identity changed")
    payloads = []
    for item in plan["files"]:
        fresh, content = local_attachment(item["path"])
        if fresh != item:
            raise ValueError("Local attachment changed since preview; no files were uploaded")
        payloads.append({"@odata.type": "#microsoft.graph.fileAttachment", "name": item["name"], "contentType": item["contentType"], "isInline": False, "contentBytes": base64.b64encode(content).decode("ascii")})
    current = edit_snapshot(client, plan["current"]["message"]["id"], plan["account"])
    if digest(current) != plan["currentHash"]:
        raise ValueError("Draft changed since preview; preserve the newer draft and preview again")
    draft_id = current["message"]["id"]
    store.dispatch(operation, {"status": "uncertain_after_dispatch", "draft": draft_id, "hash": plan["hash"]})
    result = {"operation": operation, "status": "uncertain_after_dispatch", "draft": draft_id, "manualSendOnly": True, "replayAllowed": False}
    try:
        for index, payload in enumerate(payloads):
            if edit_snapshot(client, draft_id, plan["account"]) != current:
                raise ValueError("Draft changed before upload")
            store.receipt(operation, {"name": payload["name"], "status": "dispatching"}, f".attachment-{index}.dispatch.json")
            response = client.request("POST", message_path(draft_id) + "/attachments", payload, {**PREFER, "If-Match": draft_etag(current["message"])})
            store.receipt(operation, {"name": payload["name"], "id": identifier(response.get("id"))}, f".attachment-{index}.created.json")
            current = verify_attachments(client, plan, plan["files"][:index + 1])
        result.update(attachment_result(current))
    except Exception:
        result["detail"] = "Some files may already be attached. Inspect draft-status/draft-verify and the draft; never repeat this upload automatically."
    store.receipt(operation, result)
    return result


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


def preview_signature_edit(client, store, message, match_html, signature_data):
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    proposed = signature(signature_data, account)
    if not isinstance(match_html, str) or not match_html.startswith("<") or len(match_html) > 10000:
        raise ValueError("Select an exact balanced signature HTML fragment from read-draft, beginning at its opening tag")
    existing = SignatureHTML(existing=True); existing.feed(match_html); existing.close()
    if existing.stack or not match_html.endswith(">") or lines(match_html) != lines(proposed) or resource_links(match_html) != resource_links(proposed):
        raise ValueError("Signature restyling must preserve its text, paragraph boundaries and links; select a complete balanced fragment")
    current = edit_snapshot(client, message, account)
    original = current["message"]["body"]["content"]
    start = original.find(match_html)
    if original.count(match_html) != 1 or start not in ElementStarts(original).starts:
        raise ValueError("Signature fragment must match exactly once at an HTML element boundary; inspect read-draft and select a unique fragment")
    updated = original[:start] + proposed + original[start + len(match_html):]
    if lines(updated) != lines(original) or resource_links(updated) != resource_links(original):
        raise ValueError("Signature replacement changes message content; no edit prepared")
    plan = store.plan({"kind": SIGNATURE_EDIT_KIND, "alias": client.alias, "identity": identity, "account": account, "current": current, "currentHash": digest(current), "bodyHTML": updated, "signatureHTML": proposed, "signaturePrefix": original[:start], "matchedSignatureHTML": match_html})
    return {"status": "preview", **plan, "manualSendOnly": True, "replacement": "Only the exact selected signature fragment is restyled. Its text/links and all other body HTML, recipients, subject and attachments are retained."}


def preview_fragment_edit(client, store, message, match_html, replacement_html):
    body_fragment(match_html, existing=True); proposed = body_fragment(replacement_html)
    identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
    current = edit_snapshot(client, message, account)
    original = current["message"]["body"]["content"]
    start = original.find(match_html)
    if original.count(match_html) != 1 or start not in ElementStarts(original).starts:
        raise ValueError("Body fragment must match exactly once at an HTML element boundary; inspect read-draft and select a unique fragment")
    updated = original[:start] + proposed + original[start + len(match_html):]
    plan = store.plan({"kind": FRAGMENT_EDIT_KIND, "alias": client.alias, "identity": identity, "account": account, "current": current, "currentHash": digest(current), "bodyHTML": updated, "matchedHTML": match_html, "replacementHTML": proposed})
    return {"status": "preview", **plan, "manualSendOnly": True, "replacement": "Only the exact selected fragment is replaced. All HTML outside it, including signatures and quotations, is retained in the body payload. Subject, recipients and attachments are unchanged."}


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
    if plan["kind"] == FRAGMENT_EDIT_KIND:
        if HTMLStructure(saved["message"]["body"]["content"]).tokens != HTMLStructure(plan["bodyHTML"]).tokens:
            raise ValueError("Saved draft HTML structure, attributes or resources differ from the preview; inspect without replaying")
    if plan["kind"] == SIGNATURE_EDIT_KIND:
        content = saved["message"]["body"]["content"]
        if resource_links(content) != resource_links(before["body"]["content"]):
            raise ValueError("Saved draft resource references changed")
        # Include the unmodified prefix only to locate the new signature in the full document; its existing styles are not part of this edit's acceptance.
        expected = StyledContent(); expected.feed(plan["signaturePrefix"])
        prefix_length = expected.position
        verify_styles(content, plan["signatureHTML"], offset=prefix_length)
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
    if plan.get("kind") == NEW_KIND and plan.get("alias") == client.alias:
        return apply_new(client, store, operation, plan)
    if plan.get("kind") == ATTACH_KIND and plan.get("alias") == client.alias:
        return apply_attachments(client, store, operation, plan)
    if plan.get("kind") in (EDIT_KIND, SIGNATURE_EDIT_KIND, FRAGMENT_EDIT_KIND) and plan.get("alias") == client.alias:
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
    p = subs.add_parser("new-draft"); p.add_argument("alias"); p.add_argument("--subject", required=True); p.add_argument("--body-file", required=True)
    p.add_argument("--to", action="append", required=True); p.add_argument("--cc", action="append", default=[])
    signatures = p.add_mutually_exclusive_group(required=True); signatures.add_argument("--signature-file"); signatures.add_argument("--no-signature", action="store_true")
    p = subs.add_parser("edit-draft"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--body-file", required=True)
    p = subs.add_parser("read-draft"); p.add_argument("alias"); p.add_argument("--message", required=True)
    p = subs.add_parser("attach-draft"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--file", action="append", required=True)
    p = subs.add_parser("style-draft-signature"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--match-html-file", required=True); p.add_argument("--signature-file", required=True)
    p = subs.add_parser("replace-draft-fragment"); p.add_argument("alias"); p.add_argument("--message", required=True); p.add_argument("--match-html-file", required=True)
    replacement = p.add_mutually_exclusive_group(required=True); replacement.add_argument("--body-file"); replacement.add_argument("--body-html-file")
    for command in ("draft-apply", "draft-status", "draft-verify"):
        p = subs.add_parser(command); p.add_argument("alias"); p.add_argument("--plan", required=True)
        if command == "draft-apply": p.add_argument("--hash", required=True); p.add_argument("--execute", action="store_true"); p.add_argument("--allow-draft", action="store_true")
    args = parser.parse_args(argv); client = Client(args.alias, "mail"); store = Store(location("mail") / ".draft-state", args.alias)
    if args.command == "reply-draft":
        data = json.loads(Path(args.signature_file).read_text()) if args.signature_file else None
        result = preview(client, store, args.message, Path(args.body_file).read_text(), args.to, args.cc, data, args.no_signature, args.reply_all)
    elif args.command == "new-draft":
        data = json.loads(Path(args.signature_file).read_text()) if args.signature_file else None
        result = preview_new(client, store, args.subject, Path(args.body_file).read_text(encoding="utf-8"), args.to, args.cc, data, args.no_signature)
    elif args.command == "edit-draft": result = preview_edit(client, store, args.message, Path(args.body_file).read_text(encoding="utf-8"))
    elif args.command == "attach-draft": result = preview_attachments(client, store, args.message, args.file)
    elif args.command == "read-draft":
        identity = client.identity(); account = address(identity.get("mail") or identity["userPrincipalName"])
        result = {"status": "draft_read", "account": account, **edit_snapshot(client, args.message, account)}
    elif args.command == "style-draft-signature":
        result = preview_signature_edit(client, store, args.message, Path(args.match_html_file).read_text(encoding="utf-8"), json.loads(Path(args.signature_file).read_text(encoding="utf-8")))
    elif args.command == "replace-draft-fragment":
        replacement = paragraphs(Path(args.body_file).read_text(encoding="utf-8")) if args.body_file else Path(args.body_html_file).read_text(encoding="utf-8")
        result = preview_fragment_edit(client, store, args.message, Path(args.match_html_file).read_text(encoding="utf-8"), replacement)
    elif args.command == "draft-apply": result = apply(client, store, args.plan, args.hash, args.execute, args.allow_draft)
    elif args.command == "draft-status": result = store.status(args.plan)
    else:
        plan = store.load(args.plan)
        if plan.get("alias") != args.alias or client.identity() != plan["identity"]: raise ValueError("Mailbox mismatch")
        if plan.get("kind") == NEW_KIND:
            result = verify_new(client, plan, store.read(store.path(args.plan, ".created.json"))["draft"])
        elif plan.get("kind") == ATTACH_KIND:
            result = reconcile_attachments(client, plan)
        elif plan.get("kind") in (EDIT_KIND, SIGNATURE_EDIT_KIND, FRAGMENT_EDIT_KIND):
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
