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


if __name__ == "__main__": unittest.main()
