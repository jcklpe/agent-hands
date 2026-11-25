"""Stateful mailbox tests exercise native reply creation, body preservation and failures."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlsplit

spec = importlib.util.spec_from_file_location("drafts", Path(__file__).parents[1] / "scripts/drafts.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def recipient(email): return {"emailAddress": {"address": email}}


class Mailbox:
    alias = "example"
    def __init__(self):
        self.source = {"id": "source", "subject": "Review", "body": {"contentType": "html", "content": '<p>Original message</p><p>Nested history</p>'}, "from": recipient("sender@example.com"), "replyTo": [], "toRecipients": [recipient("me@example.com")], "ccRecipients": [], "bccRecipients": [], "conversationId": "conversation", "internetMessageId": "<message@example.com>", "isDraft": False, "changeKey": "one"}
        self.writes = []; self.draft = None; self.allow = True; self.lost = False; self.bad_readback = False; self.edit_on_read = False; self.no_etag = False; self.bad_recipients = False; self.reads = 0

    def identity(self): return {"id": "me", "mail": "me@example.com"}
    def require_write(self):
        if not self.allow: raise ValueError("not opted in")

    def request(self, method, path, body=None, headers=None, output=None):
        if method == "GET":
            if urlsplit(path).path == "/me/messages/source": return copy.deepcopy(self.source)
            self.reads += 1
            if self.bad_readback and len(self.writes) == 2: raise RuntimeError("failed saved read")
            if self.edit_on_read and self.reads == 2:
                self.draft["body"]["content"] += "<p>User edit</p>"; self.draft["changeKey"] = "user"
            return copy.deepcopy(self.draft)
        self.writes.append((method, path, copy.deepcopy(body), headers))
        if method == "POST":
            self.draft = copy.deepcopy(self.source)
            self.draft.update(id="draft", isDraft=True, changeKey="draft-one", **{"@odata.etag": 'W/"draft-one"'})
            self.draft["subject"] = "Re: Review"; self.draft["from"] = recipient("me@example.com")
            self.draft["toRecipients"] = [recipient("sender@example.com")]
            if path.endswith("createReplyAll"):
                self.draft["ccRecipients"] = copy.deepcopy(self.source["ccRecipients"])
            else: self.draft["ccRecipients"] = []
            if self.source["replyTo"]: self.draft["toRecipients"] = copy.deepcopy(self.source["replyTo"])
            self.draft["body"]["content"] = '<html><body><div>From: sender@example.com</div>' + self.source["body"]["content"] + '</body></html>'
            self.draft["webLink"] = "https://outlook.office.com/mail/drafts/id/draft"
            if self.no_etag: self.draft.pop("@odata.etag")
            if self.bad_recipients: self.draft["toRecipients"] = [recipient("other@example.com")]
            if self.lost: raise RuntimeError("lost create response")
            return {"id": "draft"}
        if method != "PATCH" or path != "/me/messages/draft": raise AssertionError("Unexpected mutation")
        if headers.get("If-Match") != self.draft.get("@odata.etag"): raise RuntimeError("412")
        self.draft["body"] = copy.deepcopy(body["body"]); self.draft["changeKey"] = "draft-two"
        return copy.deepcopy(self.draft)


class Drafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = mod.Store(Path(self.tmp.name) / "state", "example"); self.client = Mailbox()
        self.sig = {"account": "me@example.com", "format": "text", "content": "Regards,\nSample Person"}

    def plan(self, **kw):
        return mod.preview(self.client, self.store, "source", "First paragraph.\n\nSecond 😀 paragraph.", ["sender@example.com"], [], self.sig, **kw)

    def apply(self, p): return mod.apply(self.client, self.store, p["operation"], p["hash"], True, True)

    def test_native_reply_preserves_quote_signature_paragraphs_and_unsent_state(self):
        p = self.plan(); self.assertEqual(self.client.writes, [])
        r = self.apply(p); self.assertEqual(r["status"], "draft_verified")
        self.assertEqual(self.client.writes[0][:3], ("POST", "/me/messages/source/createReply", {}))
        self.assertEqual(set(self.client.writes[1][2]), {"body"})
        self.assertEqual(mod.lines(self.client.draft["body"]["content"]), ["First paragraph.", "Second 😀 paragraph.", "Regards,", "Sample Person", "From: sender@example.com", "Original message", "Nested history"])
        self.assertTrue(self.client.draft["isDraft"])
        self.assertTrue(self.store.status(p["operation"])["created"]["draft"])

    def test_reply_all_requires_explicit_intent_and_cc(self):
        self.client.source["ccRecipients"] = [recipient("cc@example.com")]
        with self.assertRaisesRegex(ValueError, "Explicit To/CC"):
            self.plan(reply_all=True)
        p = mod.preview(self.client, self.store, "source", "Reply", ["sender@example.com"], ["cc@example.com"], self.sig, reply_all=True)
        self.assertEqual(self.apply(p)["status"], "draft_verified")
        self.assertTrue(self.client.writes[0][1].endswith("createReplyAll"))

    def test_reply_to_overrides_sender_without_inference(self):
        self.client.source["replyTo"] = [recipient("reply@example.com")]
        with self.assertRaisesRegex(ValueError, "Explicit To/CC"): self.plan()
        p = mod.preview(self.client, self.store, "source", "Reply", ["reply@example.com"], [], self.sig)
        self.assertEqual(self.apply(p)["status"], "draft_verified")

    def test_signature_account_absence_active_html_and_duplication_are_refused(self):
        for signature in [None, {**self.sig, "account": "wrong@example.com"}, {**self.sig, "format": "html", "content": '<img src="https://evil.example/track">'}, {**self.sig, "format": "html", "content": '<span onclick="run()">Sign</span>'}]:
            with self.subTest(signature=signature), self.assertRaises(ValueError):
                mod.preview(self.client, self.store, "source", "Reply", ["sender@example.com"], [], signature)
        with self.assertRaisesRegex(ValueError, "duplicates"):
            mod.preview(self.client, self.store, "source", "Reply\n\nSample Person", ["sender@example.com"], [], self.sig)
        self.assertEqual(self.client.writes, [])

    def test_signature_cannot_escape_or_restyle_the_quotation(self):
        for text in ("</body><p>Signature</p>", "<strong>Signature", "<p><b>Signature</p></b>"):
            with self.assertRaises(ValueError): mod.signature({**self.sig, "format": "html", "content": text}, "me@example.com")
        self.assertEqual(mod.signature({**self.sig, "format": "html", "content": '<p>Signature<br><a href="https://example.com">Profile</a></p>'}, "me@example.com"), '<p>Signature<br><a href="https://example.com">Profile</a></p>')

    def test_styled_signature_round_trip_preserves_blue_divider_and_quote(self):
        self.sig = {**self.sig, "format": "html", "content": '<div style="border-top: 2px solid #0070c0; padding-top: 8px; margin-top: 12px"><p style="color:navy">Sample Person<br><a href="https://example.com">Profile</a></p></div>'}
        p = self.plan()
        self.assertIn('border-top: 2px solid #0070c0', p["signatureHTML"])
        self.assertEqual(self.client.writes, [])
        self.assertEqual(self.apply(p)["status"], "draft_verified")
        self.assertIn(self.sig["content"], self.client.draft["body"]["content"])
        self.assertTrue(self.client.draft["isDraft"])
        self.assertIn('Original message', self.client.draft["body"]["content"])

    def test_style_injection_and_unsupported_layout_fail_before_write(self):
        invalid = [
            'background:url(https://example.com/track)', 'color:expression(alert(1))',
            'color:var(--remote)', 'color:blue!important', 'color:blue;position:fixed',
            'color:blue;color:red', r'c\6flor:blue', 'color:blue/*comment*/',
            'border-top:1px solid url(https://example.com)', 'border-top:99px solid blue',
            'padding-top:-1px', 'margin-top:100vh', 'color:rgb(256,0,0)', 'color:blue;@import:evil',
        ]
        for style in invalid:
            with self.subTest(style=style), self.assertRaises(ValueError):
                mod.preview(self.client, self.store, "source", "Reply", ["sender@example.com"], [], {**self.sig, "format": "html", "content": f'<p style="{style}">Sample Person</p>'})
        with self.assertRaises(ValueError):
            mod.signature({**self.sig, "format": "html", "content": '<p style="color:blue" style="color:red">Sample Person</p>'}, 'me@example.com')
        self.assertEqual(self.client.writes, [])

    def test_style_readback_accepts_equivalent_css_but_not_quote_only_or_changed_color(self):
        expected = '<p>Reply</p><p style="color:blue;border-top:2px solid #abc;padding-top:8px">Name</p>'
        normalized = '<html><head><title>Mail</title></head><body><p>Reply</p><p style="border-top-color:rgb(170,187,204);border-top-style:solid;border-top-width:1.5pt;padding-top:6pt"><span style="COLOR: #0000FF">Name</span></p></body></html>'
        mod.verify_styles(normalized, expected)
        for saved in (normalized.replace('#0000FF', '#ff0000'), '<p>Reply</p><p>Name</p>' + expected, normalized.replace('border-top-width:1.5pt;', '')):
            with self.subTest(saved=saved), self.assertRaisesRegex(ValueError, 'styles differ'):
                mod.verify_styles(saved, expected)

    def test_stripped_style_is_uncertain_and_never_replayed(self):
        self.sig = {**self.sig, "format": "html", "content": '<p style="color:blue">______</p><p>Sample Person</p>'}
        request = self.client.request
        def strip(method, path, body=None, headers=None, output=None):
            result = request(method, path, body, headers, output)
            if method == 'PATCH': self.client.draft['body']['content'] = self.client.draft['body']['content'].replace(' style="color:blue"', '')
            return result
        self.client.request = strip
        p = self.plan()
        self.assertEqual(self.apply(p)['status'], 'uncertain_after_dispatch')
        with self.assertRaisesRegex(ValueError, 'Already dispatched'): self.apply(p)
        self.assertEqual(len(self.client.writes), 2)
        self.assertTrue(self.client.draft['isDraft'])

    def test_explicit_no_signature_and_quote_signature_do_not_forge_a_new_signature(self):
        self.client.source["body"]["content"] += "<p>Old Signature</p>"
        p = mod.preview(self.client, self.store, "source", "Reply", ["sender@example.com"], [], no_signature=True)
        self.assertTrue(p["signatureOmitted"]); self.assertEqual(p["signatureHTML"], "")
        self.assertEqual(self.apply(p)["status"], "draft_verified")

    def test_source_revision_and_wrong_hash_refuse_before_create(self):
        p = self.plan(); self.client.source["changeKey"] = "two"
        with self.assertRaisesRegex(ValueError, "Source changed"): self.apply(p)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            mod.apply(self.client, self.store, p["operation"], "wrong", True, True)
        self.assertEqual(self.client.writes, [])

    def test_creation_loss_and_failed_readback_never_duplicate(self):
        for flag in ("lost", "bad_readback"):
            self.client = Mailbox(); p = self.plan(); setattr(self.client, flag, True)
            self.assertEqual(self.apply(p)["status"], "uncertain_after_dispatch")
            with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)
            self.assertEqual(sum(w[0] == "POST" for w in self.client.writes), 1)

    def test_user_edit_or_missing_etag_preserves_generated_draft(self):
        for flag in ("edit_on_read", "no_etag", "bad_recipients"):
            self.client = Mailbox(); p = self.plan(); setattr(self.client, flag, True)
            self.assertEqual(self.apply(p)["status"], "uncertain_after_dispatch")
            self.assertEqual(len(self.client.writes), 1)
            self.assertEqual(self.store.status(p["operation"])["created"]["draft"], "draft")

    def test_saved_body_without_signature_or_quote_is_not_verified(self):
        p = self.plan(); self.assertEqual(self.apply(p)["status"], "draft_verified")
        created = self.store.read(self.store.path(p["operation"], ".quote.json"))
        self.client.draft["body"]["content"] = p["replyHTML"]
        with self.assertRaisesRegex(ValueError, "differs"): mod.verify_saved(self.client.draft, p, created)
        self.client.draft["conversationId"] = "new conversation"
        with self.assertRaisesRegex(ValueError, "conversation"): mod.verify_saved(self.client.draft, p, created)

    def test_reordered_generated_quote_is_preserved_for_inspection_without_body_write(self):
        original = self.client.request
        def request(method, path, body=None, headers=None, output=None):
            result = original(method, path, body, headers, output)
            if method == "POST": self.client.draft["body"]["content"] = "<p>Nested history</p><p>Original message</p>"
            return result
        self.client.request = request
        p = self.plan(); self.assertEqual(self.apply(p)["status"], "uncertain_after_dispatch")
        self.assertEqual(len(self.client.writes), 1)

    def test_no_send_endpoint_and_action_time_optin(self):
        p = self.plan()
        for execute, allowed in [(False, True), (True, False)]:
            with self.assertRaisesRegex(ValueError, "Require"):
                mod.apply(self.client, self.store, p["operation"], p["hash"], execute, allowed)
        self.client.allow = False
        with self.assertRaisesRegex(ValueError, "opted"): self.apply(p)
        self.assertEqual(self.client.writes, [])
        self.assertIsNone(mod.safe_link("https://evil.example/draft"))


class EditMailbox(Mailbox):
    def __init__(self):
        super().__init__()
        self.draft = copy.deepcopy(self.source)
        self.draft.update(id="draft", isDraft=True, **{"@odata.etag": 'W/"one"'})
        self.draft["from"] = recipient("me@example.com")
        self.draft["toRecipients"] = [recipient("reader@example.com")]
        self.draft["ccRecipients"] = [recipient("copy@example.com")]
        self.draft["bccRecipients"] = [recipient("private@example.com")]
        self.draft["hasAttachments"] = True
        self.attachments = [{"id": "attachment", "name": "proposal.pdf", "contentType": "application/pdf", "size": 1234, "isInline": False}]
        self.paged = False; self.race = False; self.lose_patch = False; self.fail_read = False

    def request(self, method, path, body=None, headers=None, output=None):
        if method == "GET" and urlsplit(path).path.endswith("/attachments"):
            return {"value": copy.deepcopy(self.attachments), **({"@odata.nextLink": "more"} if self.paged else {})}
        if method == "GET" and self.fail_read and self.writes: raise RuntimeError("read failed")
        if method == "PATCH" and self.race:
            self.draft["@odata.etag"] = 'W/"user-edit"'
            self.draft["body"]["content"] = "<p>User's latest edit</p>"
        result = super().request(method, path, body, headers, output)
        if method == "PATCH" and self.lose_patch: raise RuntimeError("lost patch response")
        return result


class NewDrafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = mod.Store(Path(self.tmp.name) / "state", "example"); self.client = EditMailbox()
        self.lose = False
        request = self.client.request
        def create(method, path, body=None, headers=None, output=None):
            if method == "POST" and path == "/me/messages":
                self.client.writes.append((method, path, copy.deepcopy(body), headers))
                self.client.draft.update(body); self.client.draft['bccRecipients'] = []
                if self.lose: raise RuntimeError("lost response")
                return {"id": "draft"}
            return request(method, path, body, headers, output)
        self.client.request = create

    def plan(self): return mod.preview_new(self.client, self.store, "Application materials", "Hi reader,\n\nAttached are my materials.", ["reader@example.com"], [], no_signature=True)

    def test_new_unsent_draft_has_exact_content_and_explicit_recipients(self):
        plan = self.plan(); self.assertEqual(self.client.writes, [])
        result = mod.apply(self.client, self.store, plan["operation"], plan["hash"], True, True)
        self.assertEqual(result["status"], "draft_verified")
        self.assertTrue(self.client.draft["isDraft"])
        self.assertEqual(self.client.draft["subject"], "Application materials")
        self.assertEqual(self.client.draft["ccRecipients"], [])

    def test_unknown_outcome_never_recreates_and_invalid_audience_refuses(self):
        with self.assertRaises(ValueError): mod.preview_new(self.client, self.store, "Subject", "Body", ["reader@example.com"]*2, [], no_signature=True)
        self.assertEqual(self.client.writes, [])
        plan = self.plan(); self.lose = True
        self.assertEqual(mod.apply(self.client, self.store, plan["operation"], plan["hash"], True, True)["status"], "uncertain_after_dispatch")
        with self.assertRaisesRegex(ValueError, "Already dispatched"): mod.apply(self.client, self.store, plan["operation"], plan["hash"], True, True)
        self.assertEqual(len(self.client.writes), 1)


class AttachmentMailbox(EditMailbox):
    def __init__(self):
        super().__init__()
        self.uploaded = {}; self.lose_upload = False; self.corrupt = False; self.edit_after_upload = False

    def request(self, method, path, body=None, headers=None, output=None):
        route = urlsplit(path).path
        if method == "POST" and route.endswith("/attachments"):
            self.writes.append((method, path, copy.deepcopy(body), headers))
            if headers["If-Match"] != self.draft["@odata.etag"]: raise RuntimeError("412")
            key = "upload-" + str(len(self.uploaded))
            value = {**body, "id": key, "size": len(mod.base64.b64decode(body["contentBytes"]))}
            self.uploaded[key] = value
            self.attachments.append({k: value[k] for k in mod.ATTACHMENT_SELECT.split(",")})
            self.draft["changeKey"] = key; self.draft["@odata.etag"] = 'W/"' + key + '"'
            if self.edit_after_upload: self.draft["body"]["content"] += "User edit"
            if self.lose_upload: raise RuntimeError("lost upload response")
            return {"id": key}
        if method == "GET" and "/attachments/" in route:
            if urlsplit(path).query: raise RuntimeError("contentBytes is not a base attachment property")
            value = copy.deepcopy(self.uploaded[route.rsplit("/", 1)[1]])
            if self.corrupt: value["contentBytes"] = "eA=="
            return value
        return super().request(method, path, body, headers, output)


class AttachDrafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = mod.Store(Path(self.tmp.name) / "state", "example"); self.client = AttachmentMailbox()
        self.files = [Path(self.tmp.name) / "statement.pdf", Path(self.tmp.name) / "resume.pdf"]
        for i, path in enumerate(self.files): path.write_bytes(b"%PDF-synthetic-" + bytes([i]))

    def plan(self): return mod.preview_attachments(self.client, self.store, "draft", self.files)
    def apply(self, plan): return mod.apply(self.client, self.store, plan["operation"], plan["hash"], True, True)

    def test_two_files_verified_by_bytes_preserving_body_audience_and_existing_attachment(self):
        before = copy.deepcopy(self.client.draft); existing = copy.deepcopy(self.client.attachments)
        plan = self.plan(); self.assertEqual(self.client.writes, [])
        result = self.apply(plan)
        self.assertEqual(result["status"], "draft_attachments_verified")
        self.assertEqual(self.client.draft["body"], before["body"])
        self.assertEqual(self.client.draft["toRecipients"], before["toRecipients"])
        self.assertEqual(self.client.attachments[:1], existing)
        self.assertEqual(len(self.client.writes), 2)
        self.assertTrue(self.client.draft["isDraft"])

    def test_file_or_draft_changes_stop_before_upload(self):
        plan = self.plan(); self.files[0].write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Local attachment changed"): self.apply(plan)
        plan = self.plan(); self.client.draft["subject"] = "User edit"
        with self.assertRaisesRegex(ValueError, "Draft changed"): self.apply(plan)
        self.assertEqual(self.client.writes, [])

    def test_lost_response_keeps_partial_upload_and_refuses_replay(self):
        plan = self.plan(); self.client.lose_upload = True
        self.assertEqual(self.apply(plan)["status"], "uncertain_after_dispatch")
        self.assertEqual(len(self.client.writes), 1)
        with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(plan)
        with self.assertRaisesRegex(ValueError, "incomplete"): mod.verify_attachments(self.client, plan)
        reconciled = mod.reconcile_attachments(self.client, plan)
        self.assertEqual(reconciled["status"], "draft_attachments_partial")
        self.assertEqual(reconciled["missing"], ["resume.pdf"])

    def test_corrupt_bytes_or_intervening_edit_stop_second_upload(self):
        for flag in ("corrupt", "edit_after_upload"):
            self.client = AttachmentMailbox(); setattr(self.client, flag, True)
            plan = self.plan()
            self.assertEqual(self.apply(plan)["status"], "uncertain_after_dispatch")
            self.assertEqual(len(self.client.writes), 1)

    def test_duplicate_names_size_sent_targets_and_partial_inventory_refused(self):
        with self.assertRaisesRegex(ValueError, "unique"): mod.preview_attachments(self.client, self.store, "draft", self.files * 2)
        self.client.attachments[0]["name"] = self.files[0].name
        with self.assertRaisesRegex(ValueError, "already exists"): self.plan()
        self.client = AttachmentMailbox(); self.client.draft["isDraft"] = False
        with self.assertRaisesRegex(ValueError, "unsent"): self.plan()
        self.client = AttachmentMailbox(); self.client.paged = True
        with self.assertRaisesRegex(ValueError, "Incomplete"): self.plan()
        self.client = AttachmentMailbox(); self.files[0].write_bytes(b"x" * 3_000_000)
        with self.assertRaisesRegex(ValueError, "smaller"): self.plan()
        self.assertEqual(self.client.writes, [])


class EditDrafts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = mod.Store(Path(self.tmp.name) / "state", "example"); self.client = EditMailbox()
        self.body = "Hi reader,\n\nNew dates — January 7–14.\n\nRegards,\nExample Person"

    def plan(self): return mod.preview_edit(self.client, self.store, "draft", self.body)
    def apply(self, p, execute=True, allowed=True): return mod.apply(self.client, self.store, p["operation"], p["hash"], execute, allowed)

    def test_edits_same_draft_once_and_preserves_subject_audience_and_attachment(self):
        before = copy.deepcopy(self.client.draft); attachments = copy.deepcopy(self.client.attachments)
        p = self.plan(); self.assertEqual(self.client.writes, [])
        result = self.apply(p)
        self.assertEqual(result["status"], "draft_edit_verified")
        self.assertEqual(result["draft"], before["id"])
        self.assertEqual(len(self.client.writes), 1)
        method, path, payload, headers = self.client.writes[0]
        self.assertEqual((method, path), ("PATCH", "/me/messages/draft"))
        self.assertEqual(set(payload), {"body"}); self.assertEqual(headers["If-Match"], before["@odata.etag"])
        for key in mod.EDIT_PRESERVED: self.assertEqual(self.client.draft.get(key), before.get(key))
        self.assertEqual(self.client.attachments, attachments)
        self.assertTrue(self.client.draft["isDraft"])
        self.assertEqual(mod.lines(self.client.draft["body"]["content"]), ["Hi reader,", "New dates — January 7–14.", "Regards,", "Example Person"])
        with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)

    def test_new_draft_without_sender_is_bound_to_verified_mailbox(self):
        self.client.draft.pop("from")
        self.assertEqual(self.apply(self.plan())["status"], "draft_edit_verified")

    def test_received_sent_alternate_sender_missing_etag_and_partial_attachments_refused(self):
        changes = [lambda: self.client.draft.update(isDraft=False), lambda: self.client.draft.update(sender=recipient("other@example.com")), lambda: self.client.draft.pop("@odata.etag"), lambda: setattr(self.client, "paged", True)]
        for change in changes:
            self.client = EditMailbox(); change()
            with self.assertRaises(ValueError): self.plan()
            self.assertEqual(self.client.writes, [])

    def test_blank_body_and_rich_or_inline_content_refused_before_mutation(self):
        self.body = "   "
        with self.assertRaises(ValueError): self.plan()
        self.body = "Replacement"
        for content in ('<a href="https://example.com">Link</a>', '<img src="cid:photo">', '<table><tr><td>Cell</td></tr></table>'):
            self.client.draft["body"]["content"] = content
            with self.assertRaisesRegex(ValueError, "formatting-preserving"): self.plan()
        self.client.draft["body"]["content"] = "<p>Simple</p>"; self.client.attachments[0]["isInline"] = True
        with self.assertRaisesRegex(ValueError, "formatting-preserving"): self.plan()
        self.assertEqual(self.client.writes, [])

    def test_changed_body_recipients_subject_or_attachment_stops_before_write(self):
        changes = [lambda: self.client.draft["body"].update(content="User edit"), lambda: self.client.draft.update(subject="Other subject"), lambda: self.client.draft["toRecipients"].append(recipient("new@example.com")), lambda: self.client.attachments[0].update(size=999)]
        for change in changes:
            self.client = EditMailbox(); p = self.plan(); change()
            with self.assertRaisesRegex(ValueError, "changed since preview"): self.apply(p)
            self.assertEqual(self.client.writes, [])

    def test_patch_race_preserves_intervening_edit_and_blocks_replay(self):
        p = self.plan(); self.client.race = True
        self.assertEqual(self.apply(p)["status"], "uncertain_after_dispatch")
        self.assertEqual(self.client.draft["body"]["content"], "<p>User's latest edit</p>")
        with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)
        self.assertEqual(len(self.client.writes), 1)

    def test_uncertain_patch_or_readback_recovers_by_read_only_verification(self):
        for flag in ("lose_patch", "fail_read"):
            self.client = EditMailbox(); p = self.plan(); setattr(self.client, flag, True)
            result = self.apply(p); self.assertEqual(result["status"], "uncertain_after_dispatch")
            self.assertEqual(self.store.status(p["operation"])["dispatch"]["draft"], "draft")
            setattr(self.client, flag, False)
            self.assertEqual(mod.verify_edit(self.client, p)["status"], "draft_edit_verified")
            with self.assertRaisesRegex(ValueError, "Already dispatched"): self.apply(p)
            self.assertEqual(len(self.client.writes), 1)

    def test_verification_rejects_metadata_body_attachment_or_sent_state_changes(self):
        changes = [lambda: self.client.draft.update(isDraft=False), lambda: self.client.draft.update(subject="Changed"), lambda: self.client.attachments.clear(), lambda: self.client.draft["body"].update(content="Wrong body")]
        for change in changes:
            self.client = EditMailbox(); p = self.plan(); self.apply(p); change()
            with self.assertRaises(ValueError): mod.verify_edit(self.client, p)

    def test_write_optin_identity_hash_and_execution_flags_are_required(self):
        p = self.plan()
        for execute, allowed in ((False, True), (True, False)):
            with self.assertRaisesRegex(ValueError, "Require"): self.apply(p, execute, allowed)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            mod.apply(self.client, self.store, p["operation"], "wrong", True, True)
        self.client.allow = False
        with self.assertRaisesRegex(ValueError, "opted"): self.apply(p)
        self.client.allow = True; self.client.identity = lambda: {"id": "other", "mail": "other@example.com"}
        with self.assertRaisesRegex(ValueError, "Mailbox identity changed"): self.apply(p)
        self.assertEqual(self.client.writes, [])


class StyleDraftSignature(unittest.TestCase):
    def setUp(self):
        EditDrafts.setUp(self)
        self.match = '<p class="signature">______</p><p>Example Person<br><a href="https://example.com">Website</a></p>'
        self.sig = {"account": "me@example.com", "format": "html", "content": '<p style="color:#0070c0">______</p><p>Example Person<br><a href="https://example.com">Website</a></p>'}
        self.prefix = '<html><body><p>Keep my latest reply.</p>'
        self.suffix = '<blockquote><p>Quoted content</p><img src="cid:original"></blockquote></body></html>'
        self.client.draft['body']['content'] = self.prefix + self.match + self.suffix
        self.client.attachments[0]['isInline'] = True

    def plan(self): return mod.preview_signature_edit(self.client, self.store, 'draft', self.match, self.sig)
    apply = EditDrafts.apply

    def test_restyles_same_draft_without_rewriting_reply_quote_or_inline_content(self):
        before = copy.deepcopy(self.client.draft)
        p = self.plan(); self.assertEqual(self.client.writes, [])
        self.assertEqual(self.apply(p)['status'], 'draft_edit_verified')
        self.assertEqual(self.client.draft['body']['content'], self.prefix + self.sig['content'] + self.suffix)
        for key in mod.EDIT_PRESERVED: self.assertEqual(self.client.draft.get(key), before.get(key))
        self.assertEqual(len(self.client.writes), 1)

    def test_ambiguous_changed_text_links_or_unbalanced_fragment_refused(self):
        changes = [lambda: self.client.draft['body'].update(content=self.match + self.match), lambda: self.sig.update(content=self.sig['content'].replace('Example Person', 'Someone else')), lambda: self.sig.update(content=self.sig['content'].replace('https://example.com', 'https://elsewhere.example')), lambda: setattr(self, 'match', '</body><p>Example Person</p>')]
        for change in changes:
            self.setUp(); change()
            with self.assertRaises(ValueError): self.plan()
            self.assertEqual(self.client.writes, [])

    def test_fragment_inside_attribute_is_not_an_element(self):
        self.match = '<p>Example Person</p>'
        self.sig['content'] = '<p style="color:blue">Example Person</p>'
        self.client.draft['body']['content'] = '<div title="' + self.match + '">Hello</div>'
        with self.assertRaisesRegex(ValueError, 'element boundary'): self.plan()
        self.assertEqual(self.client.writes, [])

    def test_style_loss_or_changed_resource_is_unverified(self):
        for replace in [('color:#0070c0', 'color:red'), ('cid:original', 'cid:changed')]:
            self.setUp(); p = self.plan(); self.apply(p)
            self.client.draft['body']['content'] = self.client.draft['body']['content'].replace(*replace)
            with self.assertRaises(ValueError): mod.verify_edit(self.client, p)

    def test_stale_preview_race_and_lost_response_preserve_edits_and_block_replay(self):
        p = self.plan(); self.client.draft['body']['content'] += '<p>User edit</p>'
        with self.assertRaisesRegex(ValueError, 'changed since preview'): self.apply(p)
        self.assertEqual(self.client.writes, [])
        for flag in ('race', 'lose_patch', 'fail_read'):
            self.setUp(); p = self.plan(); setattr(self.client, flag, True)
            self.assertEqual(self.apply(p)['status'], 'uncertain_after_dispatch')
            with self.assertRaisesRegex(ValueError, 'Already dispatched'): self.apply(p)
            setattr(self.client, flag, False)
            if flag == 'race': self.assertIn("User's latest edit", self.client.draft['body']['content'])
            else: self.assertEqual(mod.verify_edit(self.client, p)['status'], 'draft_edit_verified')
            self.assertEqual(len(self.client.writes), 1)

    test_write_optin_identity_hash_and_execution_flags_are_required = EditDrafts.test_write_optin_identity_hash_and_execution_flags_are_required


class ReplaceDraftFragment(unittest.TestCase):
    def setUp(self):
        EditDrafts.setUp(self)
        self.match = '<p class="reply">Old reply.</p><p>Thanks,</p>'
        self.replacement = '<p>Updated reply. See the <a href="https://example.com/project">project board</a>.</p><p>Thanks,</p>'
        self.prefix = '<html><body><div>'
        self.suffix = '<p style="color:rgb(0,0,255)"><strong>______</strong></p><p>Example Person</p></div><blockquote><table><tr><td style="font-size:11pt">Quoted history</td></tr></table><img src="cid:original"></blockquote></body></html>'
        self.client.draft['body']['content'] = self.prefix + self.match + self.suffix
        self.client.attachments[0]['isInline'] = True

    def plan(self): return mod.preview_fragment_edit(self.client, self.store, 'draft', self.match, self.replacement)
    apply = EditDrafts.apply

    def test_replaces_selected_reply_and_retains_rich_signature_quote_and_attachment(self):
        before = copy.deepcopy(self.client.draft); attachments = copy.deepcopy(self.client.attachments)
        p = self.plan(); self.assertEqual(self.client.writes, [])
        self.assertEqual(self.apply(p)['status'], 'draft_edit_verified')
        self.assertEqual(self.client.draft['body']['content'], self.prefix + self.replacement + self.suffix)
        self.assertEqual(self.client.attachments, attachments)
        for key in mod.EDIT_PRESERVED: self.assertEqual(self.client.draft.get(key), before.get(key))
        self.assertEqual(len(self.client.writes), 1)
        self.assertEqual(set(self.client.writes[0][2]), {'body'})
        with self.assertRaisesRegex(ValueError, 'Already dispatched'): self.apply(p)

    def test_missing_ambiguous_unbalanced_and_non_element_matches_fail_before_plan(self):
        originals = [self.prefix + self.suffix, self.prefix + self.match * 2 + self.suffix, '<div title="' + self.match + '">Hello</div>', '<!--' + self.match + '-->']
        for original in originals:
            self.client.draft['body']['content'] = original
            with self.assertRaisesRegex(ValueError, 'exactly once'): self.plan()
        for match in ('</div><p>Old reply.</p>', '<p>Old reply.', '<table><tr><td>Old reply.</td></tr></table>'):
            self.match = match
            with self.assertRaises(ValueError): self.plan()
        self.assertEqual(self.client.writes, [])
        self.assertEqual(list(Path(self.tmp.name).rglob('*.json')), [])

    def test_unsafe_replacement_refused_and_plain_text_is_escaped(self):
        for content in ('<p onclick="run()">New</p>', '<img src="https://example.com/pixel">', '<p><a href="javascript:run()">New</a></p>', '<p style="position:fixed">New</p>', '<p>New</p></div>', '<p><strong>New</p></strong>', '<script>run()</script>'):
            self.replacement = content
            with self.assertRaises(ValueError): self.plan()
        self.assertEqual(self.client.writes, [])
        self.replacement = mod.paragraphs('New <text> & more\n\nSecond paragraph.')
        self.assertIn('&lt;text&gt; &amp;', self.plan()['replacementHTML'])
        self.assertEqual(self.apply(self.plan())['status'], 'draft_edit_verified')

    def test_structural_readback_rejects_style_quote_link_and_image_changes(self):
        changes = [('color:rgb(0,0,255)', 'color:red'), ('font-size:11pt', 'font-size:18pt'), ('https://example.com/project', 'https://elsewhere.example'), ('cid:original', 'cid:other'), ('<strong>______</strong>', '______')]
        for old, new in changes:
            with self.subTest(old=old):
                self.setUp(); p = self.plan(); self.apply(p)
                self.client.draft['body']['content'] = self.client.draft['body']['content'].replace(old, new)
                with self.assertRaisesRegex(ValueError, 'HTML structure'): mod.verify_edit(self.client, p)

    def test_harmless_attribute_order_and_tag_spacing_readback(self):
        expected = '<html><body><p class="x" style="color:blue">Hello &amp; world</p><br></body></html>'
        actual = '<HTML>\r\n<BODY><p style="color:blue" class="x">Hello &#38; world</p>\n<br /></BODY></HTML>'
        self.assertEqual(mod.HTMLStructure(expected).tokens, mod.HTMLStructure(actual).tokens)

    test_received_sent_alternate_sender_missing_etag_and_partial_attachments_refused = EditDrafts.test_received_sent_alternate_sender_missing_etag_and_partial_attachments_refused
    def test_changed_body_recipients_subject_or_attachment_stops_before_write(self):
        changes = [lambda: self.client.draft['body'].update(content='User edit'), lambda: self.client.draft.update(subject='Other subject'), lambda: self.client.draft['toRecipients'].append(recipient('new@example.com')), lambda: self.client.attachments[0].update(size=999)]
        for change in changes:
            self.setUp(); p = self.plan(); change()
            with self.assertRaisesRegex(ValueError, 'changed since preview'): self.apply(p)
            self.assertEqual(self.client.writes, [])

    test_stale_preview_race_and_lost_response_preserve_edits_and_block_replay = StyleDraftSignature.test_stale_preview_race_and_lost_response_preserve_edits_and_block_replay
    test_write_optin_identity_hash_and_execution_flags_are_required = EditDrafts.test_write_optin_identity_hash_and_execution_flags_are_required


if __name__ == "__main__": unittest.main()
