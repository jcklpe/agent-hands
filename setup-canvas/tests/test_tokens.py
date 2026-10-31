#!/usr/bin/env python3
"""Synthetic checks for token metadata selection and credential-safe diagnostics."""
import json
import datetime as dt
import os
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import canvas_auth as auth
import canvas_tokens as renewal
from test_transport import ACCOUNT, FakeTransport, TOKEN, reply


class TokenStatusTest(unittest.TestCase):
    def client(self, rows, token=TOKEN, user_id="1001"):
        environment = patch.dict(os.environ, {"CANVAS_TOKEN_EXAMPLE": token}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        transport = FakeTransport(reply(body={"id": user_id}), reply(body=rows))
        return auth.Client(ACCOUNT, transport), transport

    def record(self, **changes):
        return {"id": "42", "user_id": "1001", "visible_token": TOKEN[:5] + "...", "expires_at": "2027-01-28T00:00:00Z", "workflow_state": "active", "can_manually_regenerate": True, **changes}

    def test_reports_only_current_token_metadata_and_sends_only_gets(self):
        client, transport = self.client([self.record(id="99", visible_token="other...", purpose="private other token"), self.record(token=TOKEN)])
        result = auth.token_status(client)
        self.assertEqual(result["token_id"], "42")
        self.assertEqual(result["renewal_write_access"], "not_checked")
        text = json.dumps(result)
        for private in (TOKEN, TOKEN[:5], "private other token", "visible_token", '"token"'):
            self.assertNotIn(private, text)
        self.assertEqual([r["method"] for r in transport.sent], ["GET", "GET"])

    def test_sharded_tokens_and_explicit_hints_are_supported(self):
        client, _ = self.client([self.record(token_hint=TOKEN[:5], visible_token=None)], token="123~" + TOKEN)
        self.assertEqual(auth.token_status(client)["token_id"], "42")
        client, _ = self.client([self.record(visible_token="123~" + TOKEN[:5] + "...")], token="123~" + TOKEN)
        self.assertEqual(auth.token_status(client)["token_id"], "42")

    def test_ambiguous_missing_and_malformed_metadata_refuse(self):
        for rows, kind in (([], "token_metadata_unavailable"), ([self.record(), self.record(id="43")], "token_metadata_unavailable"), ([self.record(user_id="2002")], "identity_mismatch"), ([None], "malformed")):
            with self.subTest(kind=kind):
                client, _ = self.client(rows)
                with self.assertRaises(auth.CanvasError) as raised:
                    auth.token_status(client)
                self.assertEqual(raised.exception.kind, kind)
                self.assertNotIn(TOKEN, str(raised.exception))

    def test_identity_mismatch_stops_before_token_listing(self):
        client, transport = self.client([self.record()], user_id="2002")
        with self.assertRaises(auth.CanvasError) as raised:
            auth.token_status(client)
        self.assertEqual(raised.exception.kind, "identity_mismatch")
        self.assertEqual(len(transport.sent), 1)


NOW = dt.datetime(2026, 10, 30, 12, tzinfo=dt.timezone.utc)
NEW_TOKEN = "replacement-synthetic-token-d73b"


class StatefulTokens:
    def __init__(self):
        self.records = {TOKEN: {"id": "42", "user_id": "1001", "visible_token": TOKEN[:5] + "...", "created_at": "2026-10-30T12:00:00Z", "expires_at": "2027-01-28T06:00:00Z", "workflow_state": "active", "can_manually_regenerate": True, "scopes": ["url:GET|/api/v1/courses"]}}
        self.sent = []
        self.lose_create_response = False
        self.deny_create = False
        self.fail_new_read = False

    def send(self, method, url, headers, body=None, token=None):
        self.sent.append((method, urlsplit(url).path))
        if token not in self.records:
            return reply(status=401, body={"error": "invalid access token"})
        path = urlsplit(url).path
        if method == "GET" and path == "/api/v1/users/self":
            if token == NEW_TOKEN and self.fail_new_read:
                raise auth.CanvasError("network_error", "Synthetic read failed")
            return reply(body={"id": "1001"})
        if method == "GET" and path == "/api/v1/users/self/user_generated_tokens":
            return reply(body=list(self.records.values()))
        if method == "POST" and path == "/api/v1/users/self/tokens":
            if self.deny_create:
                return reply(status=403, body={"errors": "forbidden"})
            fields = parse_qs(body.decode())
            self.records[NEW_TOKEN] = {**self.records[TOKEN], "id": "43", "visible_token": NEW_TOKEN[:5] + "...", "purpose": fields["token[purpose]"][0], "expires_at": fields["token[expires_at]"][0], "scopes": fields.get("token[scopes][]", [])}
            if self.lose_create_response:
                raise auth.CanvasError("network_error", "Synthetic response lost after creation")
            return reply(body={**self.records[NEW_TOKEN], "visible_token": NEW_TOKEN})
        raise AssertionError("Unexpected mutation or endpoint")


class RenewalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.env = self.root / ".env"
        self.config = self.root / "canvas-accounts.json"
        self.env.write_text(f"# Keep this comment\nCANVAS_TOKEN_EXAMPLE={TOKEN}\nCANVAS_OTHER=preserved\n")
        self.env.chmod(0o600)
        self.entry = {"alias": "example", "base_url": ACCOUNT.base_url, "user_id": "1001", "token_env": "CANVAS_TOKEN_EXAMPLE", "token_expires": "2027-01-28", "courses": ["123"]}
        self.config.write_text(json.dumps({"accounts": [self.entry]}))
        self.config.chmod(0o600)
        env = patch.dict(os.environ, {"CANVAS_CONFIG_DIR": str(self.root)}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(auth._file_settings.clear)
        auth.load_env()
        self.transport = StatefulTokens()
        self.client = auth.Client(auth.account("example"), self.transport)

    def plan(self, **kwargs):
        return renewal.make_plan(self.client, now=NOW, **kwargs)[0]

    def execute(self, plan=None, **kwargs):
        return renewal.execute(self.client, (plan or self.plan(**kwargs))["preview_hash"], now=NOW, **kwargs)

    def assert_kind(self, kind, action):
        with self.assertRaises(auth.CanvasError) as raised:
            action()
        self.assertEqual(raised.exception.kind, kind)
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertNotIn(NEW_TOKEN, str(raised.exception))

    def test_preview_is_read_only_and_execution_preserves_old_access_and_other_settings(self):
        other = {"alias": "other", "base_url": "https://other.example.edu", "user_id": "2002", "token_env": "CANVAS_TOKEN_OTHER", "courses": ["999"]}
        self.config.write_text(json.dumps({"accounts": [self.entry, other]}))
        old_env = self.env.read_bytes()
        plan = self.plan(enable=True)
        self.assertEqual(self.env.read_bytes(), old_env)
        self.assertFalse(any(method != "GET" for method, _ in self.transport.sent))
        result = self.execute(plan, enable=True)
        self.assertEqual(result["token_id"], "43")
        self.assertEqual(sum(method == "POST" for method, _ in self.transport.sent), 1)
        self.assertFalse(any(method in {"DELETE", "PUT"} for method, _ in self.transport.sent))
        self.assertIn(TOKEN, self.transport.records)
        self.assertIn("# Keep this comment", self.env.read_text())
        self.assertIn("CANVAS_OTHER=preserved", self.env.read_text())
        self.assertEqual(auth.token_for(auth.account("example")), NEW_TOKEN)
        self.assertTrue(auth.account("example").token_renewal["enabled"])
        self.assertEqual(json.loads(self.config.read_text())["accounts"][1], other)
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(NEW_TOKEN, json.dumps(result))
        self.assertNotIn(TOKEN, json.dumps(plan))
        self.assertFalse(renewal.state_path(self.client.account).exists())

    def test_stale_file_hash_and_exported_override_block_before_mutation(self):
        plan = self.plan()
        self.env.write_text(self.env.read_text() + "# Changed\n")
        self.assert_kind("preview_changed", lambda: self.execute(plan))
        self.assertFalse(any(method == "POST" for method, _ in self.transport.sent))
        os.environ["CANVAS_TOKEN_EXAMPLE"] = TOKEN
        self.assert_kind("config_invalid", self.plan)

    def test_lost_creation_response_is_not_retried_and_old_credential_stays_usable(self):
        old = self.env.read_bytes()
        self.transport.lose_create_response = True
        self.assert_kind("renewal_uncertain", self.execute)
        self.assertEqual(self.env.read_bytes(), old)
        self.assertTrue(renewal.state_path(self.client.account).exists())
        self.assert_kind("renewal_uncertain", self.execute)
        self.assertEqual(sum(method == "POST" for method, _ in self.transport.sent), 1)

    def test_verified_replacement_can_resume_without_creating_another_token(self):
        old = self.env.read_bytes()
        self.transport.fail_new_read = True
        self.assert_kind("renewal_uncertain", self.execute)
        pending = renewal.state_path(self.client.account)
        self.assertEqual(pending.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.env.read_bytes(), old)
        self.transport.fail_new_read = False
        result = renewal.recover(self.client, now=NOW)
        self.assertTrue(result["verified"])
        self.assertEqual(sum(method == "POST" for method, _ in self.transport.sent), 1)
        self.assertIn(NEW_TOKEN, self.env.read_text())

    def test_refusal_does_not_change_local_configuration_or_leave_uncertainty(self):
        old = self.env.read_bytes()
        self.transport.deny_create = True
        self.assert_kind("denied", self.execute)
        self.assertEqual(self.env.read_bytes(), old)
        self.assertFalse(renewal.state_path(self.client.account).exists())

    def test_auto_renewal_is_opt_in_and_skips_a_token_that_is_not_due(self):
        self.assertIsNone(renewal.maintain(self.client, NOW))
        self.assertEqual(self.transport.sent, [])
        self.entry["token_renewal"] = {"enabled": True, "lifetime_days": 90, "before_days": 14}
        self.config.write_text(json.dumps({"accounts": [self.entry]}))
        self.client.account = auth.account("example")
        self.assertIsNone(renewal.maintain(self.client, NOW))
        self.assertEqual(self.transport.sent, [])

    def test_auto_renewal_runs_once_when_due_and_then_skips(self):
        self.entry.update(token_expires="2026-11-04", token_renewal={"enabled": True, "lifetime_days": 90, "before_days": 14})
        self.config.write_text(json.dumps({"accounts": [self.entry]}))
        self.client.account = auth.account("example")
        result = renewal.maintain(self.client, NOW)
        self.assertTrue(result["verified"])
        self.assertIsNone(renewal.maintain(self.client, NOW))
        self.assertEqual(sum(method == "POST" for method, _ in self.transport.sent), 1)

    def test_changed_scopes_on_successor_block_switching_credentials(self):
        original = self.transport.send
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == "POST":
                self.transport.records[NEW_TOKEN]["scopes"] = []
            return result
        self.transport.send = changed
        self.assert_kind("renewal_uncertain", self.execute)
        self.assertEqual(auth.token_for(auth.account("example")), TOKEN)
        self.assertTrue(renewal.state_path(self.client.account).exists())

    def test_malformed_successor_scopes_leave_a_recoverable_pending_record(self):
        original = self.transport.send
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            if args[0] == "POST":
                self.transport.records[NEW_TOKEN]["scopes"] = None
            return result
        self.transport.send = changed
        self.assert_kind("renewal_uncertain", self.execute)
        self.assertEqual(auth.token_for(auth.account("example")), TOKEN)
        self.assertIn(NEW_TOKEN, renewal.state_path(self.client.account).read_text())

    def test_concurrent_renewal_is_refused_before_sending(self):
        with renewal.locked(self.client.account):
            self.assert_kind("renewal_busy", self.execute)
        self.assertFalse(any(method == "POST" for method, _ in self.transport.sent))

    def test_crash_between_env_and_config_replacement_can_resume(self):
        original = renewal.atomic
        failed = False
        def interrupted(path, value):
            nonlocal failed
            if path == self.config and not failed:
                failed = True
                raise OSError("Synthetic interruption")
            return original(path, value)
        with patch.object(renewal, "atomic", side_effect=interrupted):
            self.assert_kind("renewal_uncertain", lambda: self.execute(self.plan(enable=True), enable=True))
        self.assertIn(NEW_TOKEN, self.env.read_text())
        self.assertIsNone(auth.account("example").token_renewal)
        result = renewal.recover(self.client, now=NOW)
        self.assertTrue(result["verified"])
        self.assertTrue(auth.account("example").token_renewal["enabled"])
        self.assertEqual(sum(method == "POST" for method, _ in self.transport.sent), 1)

    def test_invalid_policy_and_symlink_inputs_are_refused(self):
        self.assert_kind("config_invalid", lambda: self.plan(lifetime=91))
        self.entry["token_renewal"] = {"enabled": True, "lifetime_days": 90, "before_days": 90}
        self.config.write_text(json.dumps({"accounts": [self.entry]}))
        self.assert_kind("config_invalid", lambda: auth.account("example"))
        self.config.write_text(json.dumps({"accounts": [{k:v for k,v in self.entry.items() if k != 'token_renewal'}]}))
        original = self.root / "original.env"
        self.env.rename(original)
        self.env.symlink_to(original)
        self.assert_kind("config_insecure", self.plan)


if __name__ == "__main__":
    unittest.main()
