"""Inbox reading and the guarded reply against a synthetic, stateful conversation; no live Canvas."""
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from canvas_fixture import CanvasFixture, TOKEN, auth
from canvas_history import History
import test_cli

PATH = "/api/v1/conversations"
PEOPLE = [{"id": 1001, "name": "Example User"}, {"id": 2002, "name": "Example Teacher"}, {"id": 3003, "name": "Example Assistant"}]


def msg(mid, author, body, at, **more):
    return {"id": mid, "author_id": author, "body": body, "created_at": at, "generated": False, "attachments": [], "media_comment": None, "forwarded_messages": [], "participating_user_ids": [1001, 2002, 3003], **more}


class InboxFixture(CanvasFixture):
    def __init__(self):
        super().__init__()
        self.conversation = {"id": 77, "subject": "Example question", "workflow_state": "unread", "message_count": 2, "last_message": "Private second", "last_message_at": "2026-10-02T12:00:00Z", "private": False, "context_name": "Example course", "participants": PEOPLE, "audience": [2002, 3003]}
        # Canvas returns the newest message first.
        self.messages = [msg(502, 2002, "Private second", "2026-10-02T12:00:00Z", attachments=[{"id": 9, "display_name": "notes.pdf", "content-type": "application/pdf", "url": "https://files.example/?verifier=private"}]), msg(501, 1001, "Private first", "2026-10-01T12:00:00Z")]
        self.others, self.posts, self.mode, self.reads = [], [], "normal", []

    def send(self, method, url, headers, body=None, token=None):
        parts = urlsplit(url)
        if method != "POST":
            return super().send(method, url, headers, body, token)
        assert token == TOKEN and parts.path == PATH + "/77/add_message"
        fields = parse_qs(body.decode())
        self.posts.append(fields)
        if self.mode == "refuse":
            return auth.Response(401, {"content-type": "application/json"}, b'{"errors":[{"message":"unable to add messages"}]}')
        new = msg(600 + len(self.posts), 1001, fields["body"][0], "2026-10-03T12:00:00Z", participating_user_ids=[1001, *map(int, fields["recipients[]"])])
        if self.mode == "altered":
            new["body"] += " changed"
        if self.mode == "wider":
            new["participating_user_ids"] = [1001, 2002, 3003]
        if self.mode != "lost":
            self.messages.insert(0, new)
            self.conversation["message_count"] += 1
        if self.mode == "drop":
            raise auth.CanvasError("transport", "connection lost")
        shown = dict(new, id=0) if self.mode == "queued" else new
        return auth.Response(202 if self.mode == "queued" else 200, {"content-type": "application/json"}, json.dumps({**self.conversation, "messages": [shown]}).encode())

    def route(self, path, params):
        if path == PATH:
            return [self.conversation, *self.others]
        if path == PATH + "/77":
            self.reads.append(params)
            if params.get("auto_mark_as_read") != ["false"]:
                self.conversation["workflow_state"] = "read"
            return {**self.conversation, "messages": self.messages}
        return super().route(path, params)


class InboxTest(unittest.TestCase):
    run_cli = test_cli.CliTest.run_cli

    def setUp(self):
        test_cli.CliTest.setUp(self)
        self.fixture = InboxFixture()
        pause = patch("canvas_inbox.READBACK_PAUSE", 0)
        pause.start()
        self.addCleanup(pause.stop)
        self.body = self.root / "reply.txt"
        self.body.write_text("Thank you.\n\nExample reply.\n", encoding="utf-8")

    def reply(self, *args, to=("--to-all",)):
        return self.run_cli("reply-conversation", "example", "--conversation", "77", "--body-file", str(self.body), *to, "--json", *args)

    def preview(self, **kwargs):
        code, output, error = self.reply(**kwargs)
        self.assertEqual(code, 0, error)
        return json.loads(output)

    def execute(self, plan, **kwargs):
        code, output, error = self.reply("--execute", "--expect", plan["preview_hash"], **kwargs)
        return code, json.loads(output) if output else None, error

    def history(self):
        return "".join(p.read_text() for p in (self.root / "history").glob("*.jsonl"))

    def test_listing_is_bounded_and_says_so(self):
        self.fixture.others = [dict(self.fixture.conversation, id=80 + n) for n in range(5)]
        code, output, error = self.run_cli("inbox", "example", "--limit", "3", "--json")
        self.assertEqual(code, 0, error)
        value = json.loads(output)
        self.assertEqual(([r["id"] for r in value["conversations"]], value["coverage"]["status"]), (["77", "80", "81"], "limited"))
        self.fixture.page_size = 2
        value = json.loads(self.run_cli("inbox", "example", "--all", "--scope", "unread", "--course", "123", "--json")[1])
        self.assertEqual((len(value["conversations"]), value["coverage"]), (6, {"status": "complete", "count": 6, "pages": 3}))
        listing = [params for path, params in self.fixture.sent if path == PATH][-3]
        self.assertEqual((listing["scope"], listing["filter[]"]), (["unread"], ["course_123"]))
        self.assertEqual(self.fixture.conversation["workflow_state"], "unread")
        self.assertEqual(self.run_cli("inbox", "example", "--limit", "0")[0], 1)
        self.fixture.others = [dict(self.fixture.conversation)]
        self.assertEqual(self.run_cli("inbox", "example", "--all")[0], 1)

    def test_reading_keeps_the_conversation_unread_and_orders_messages(self):
        code, output, error = self.run_cli("conversation", "example", "--conversation", "77", "--json")
        self.assertEqual(code, 0, error)
        value = json.loads(output)
        self.assertEqual([m["id"] for m in value["messages"]], ["501", "502"])
        self.assertEqual((value["messages"][1]["author_name"], value["messages"][1]["attachments"]), ("Example Teacher", [{"id": "9", "name": "notes.pdf", "content_type": "application/pdf"}]))
        self.assertEqual((value["workflow_state"], self.fixture.conversation["workflow_state"], value["coverage"]["status"]), ("unread", "unread", "complete"))
        self.assertNotIn("verifier", output)
        readable = self.run_cli("conversation", "example", "--conversation", "77")[1]
        self.assertIn("Private second", readable)
        self.assertNotIn("Private", self.history())
        self.assertNotIn("Example Teacher", self.history())

    def test_missing_messages_and_malformed_records_are_never_complete(self):
        self.fixture.conversation["message_count"] = 5
        code, output, _ = self.run_cli("conversation", "example", "--conversation", "77", "--json")
        self.assertEqual((code, json.loads(output)["coverage"]["status"]), (1, "partial"))
        self.assertEqual(self.reply()[0], 1)
        self.fixture.conversation["message_count"] = 2
        for change in ({"id": 78}, {"participants": "x"}, {"audience": ["x"]}, {"message_count": "2"}):
            original = dict(self.fixture.conversation)
            self.fixture.conversation.update(change)
            self.assertEqual(self.run_cli("conversation", "example", "--conversation", "77")[0], 1, change)
            self.fixture.conversation = original
        self.fixture.messages.append(self.fixture.messages[0])
        self.assertEqual(self.run_cli("conversation", "example", "--conversation", "77")[0], 1)
        self.fixture.failures[PATH + "/77"] = (404, {"errors": [{"message": "not found"}]})
        self.assertEqual(self.run_cli("conversation", "example", "--conversation", "77")[0], 1)

    def test_preview_shows_everything_and_sends_nothing(self):
        plan = self.preview()
        self.assertEqual((plan["body"], plan["audience"], [r["name"] for r in plan["recipients"]]), ("Thank you.\n\nExample reply.", "everyone else in the conversation", ["Example Teacher", "Example Assistant"]))
        self.assertEqual(plan["target"]["latest_message"]["id"], "502")
        self.assertEqual((self.fixture.posts, self.fixture.conversation["workflow_state"]), ([], "unread"))
        self.assertNotIn("Example reply", self.history())
        self.assertEqual(self.preview()["preview_hash"], plan["preview_hash"])
        one = self.preview(to=("--to", "2002"))
        self.assertIn("1 of 2", one["audience"])
        self.assertTrue(one["warnings"])
        self.assertNotEqual(one["preview_hash"], plan["preview_hash"])

    def test_a_reviewed_reply_is_sent_once_and_read_back(self):
        code, value, error = self.execute(self.preview())
        self.assertEqual((code, value["outcome"], value["message_id"], value["writes_sent"]), (0, "verified", "601", 1), error)
        self.assertEqual(self.fixture.posts, [{"body": ["Thank you.\n\nExample reply."], "recipients[]": ["2002", "3003"]}])
        self.assertEqual(self.fixture.conversation["workflow_state"], "unread")
        self.assertNotIn("Example reply", self.history())
        self.assertEqual([r["outcome"] for r in History(self.root / "history").rows(kind="write") if r.get("outcome") == "uncertain"], [])
        code, _, error = self.reply()
        self.assertEqual(code, 1)
        self.assertIn("already posted", error)
        self.assertEqual(len(self.fixture.posts), 1)

    def test_only_chosen_people_receive_a_narrower_reply(self):
        code, value, _ = self.execute(self.preview(to=("--to", "2002")), to=("--to", "2002"))
        self.assertEqual((code, self.fixture.posts[0]["recipients[]"], [r["id"] for r in value["recipients"]]), (0, ["2002"], ["2002"]))
        for wrong in ("9999", "1001"):
            self.assertEqual(self.reply(to=("--to", wrong))[0], 1)

    def test_the_same_words_are_allowed_after_someone_else_answers(self):
        self.execute(self.preview())
        self.fixture.messages.insert(0, msg(700, 2002, "Private third", "2026-10-04T12:00:00Z"))
        self.fixture.conversation["message_count"] += 1
        self.assertIn("same text earlier", self.preview()["warnings"][0])

    def test_changes_after_review_send_nothing(self):
        plan = self.preview()
        self.fixture.messages.insert(0, msg(503, 3003, "Private later", "2026-10-02T13:00:00Z"))
        self.fixture.conversation["message_count"] = 3
        code, _, error = self.execute(plan)
        self.assertEqual((code, self.fixture.posts), (1, []))
        self.assertIn("differs from the reviewed plan", error)
        plan = self.preview()
        self.fixture.conversation["audience"] = [2002]
        self.assertEqual(self.execute(plan)[0], 1)
        self.fixture.conversation["audience"] = [2002, 3003]
        self.body.write_text("Different reply", encoding="utf-8")
        self.assertEqual(self.execute(plan)[0], 1)
        self.assertEqual(self.reply("--execute")[0], 1)
        self.assertEqual(self.fixture.posts, [])
        # Read state alone does not invalidate a review.
        self.body.write_text("Thank you.\n\nExample reply.\n", encoding="utf-8")
        self.fixture.conversation["workflow_state"] = "read"
        self.assertEqual(self.execute(plan)[0], 0)

    def test_unsafe_conversations_and_bodies_are_refused(self):
        for change in ({"cannot_reply": True}, {"audience": None}, {"audience": []}, {"audience": [2002, 4004]}):
            original = dict(self.fixture.conversation)
            self.fixture.conversation.update(change)
            self.assertEqual(self.reply()[0], 1, change)
            self.fixture.conversation = original
        for content in (b"", b"  \n", b"\xff\xfe", b"a\x00b"):
            self.body.write_bytes(content)
            self.assertEqual(self.reply()[0], 1, content)
        self.assertEqual(self.fixture.posts, [])

    def test_a_refusal_by_canvas_is_settled_and_can_be_retried(self):
        self.fixture.mode = "refuse"
        code, value, _ = self.execute(self.preview())
        self.assertEqual((code, value["outcome"], value["writes_sent"]), (1, "refused", 1))
        self.fixture.mode = "normal"
        self.assertEqual(self.execute(self.preview())[0], 0)

    def test_a_queued_reply_is_found_by_reading(self):
        self.fixture.mode = "queued"
        code, value, _ = self.execute(self.preview())
        self.assertEqual((code, value["message_id"]), (0, "601"))

    def test_unknown_outcomes_block_another_reply_until_recorded(self):
        for mode in ("drop", "lost", "altered"):
            with self.subTest(mode):
                self.setUp()
                self.fixture.mode = mode
                code, value, _ = self.execute(self.preview())
                self.assertEqual((code, value["outcome"], len(self.fixture.posts)), (3, "PARTIAL or uncertain", 1))
                self.fixture.mode = "normal"
                code, _, error = self.reply()
                self.assertEqual(code, 1)
                self.assertIn(value["record_id"], error)
                self.assertEqual(self.run_cli("history-resolve", "example", value["record_id"], "--landed")[0], 0)
                code, _, error = self.reply()
                self.assertEqual((code, "unknown outcome" in error), (1 if mode == "drop" else 0, False))
                self.assertEqual(len(self.fixture.posts), 1)

    def test_a_wider_audience_than_reviewed_is_not_verified(self):
        self.fixture.mode = "wider"
        code, value, _ = self.execute(self.preview(to=("--to", "2002")), to=("--to", "2002"))
        self.assertEqual((code, value["error_kind"]), (3, "readback_mismatch"))

    def test_without_writable_history_nothing_is_sent(self):
        plan = self.preview()
        (self.root / "history" / ".lock").write_text("")
        self.assertEqual(self.execute(plan)[0], 1)
        self.assertEqual(self.fixture.posts, [])


if __name__ == "__main__":
    unittest.main()
