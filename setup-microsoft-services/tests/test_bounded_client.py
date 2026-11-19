"""Exercise the Python-to-Bash provider boundary with a fake PowerShell executable."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("bounded_client", Path(__file__).parents[1] / "scripts/bounded_client.py")
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


class Boundary(unittest.TestCase):
    def test_actual_shell_bridge_keeps_json_literal_and_uses_selected_identity_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = root / "accounts.json"; log = root / "request.json"; executable = root / "pwsh"
            config.write_text(json.dumps({"accounts": [{"alias": "example", "auth_provider": "graph-powershell", "expected_account": "me@example.com", "files": {"enabled": True, "write_enabled": True}}]}))
            executable.write_text('''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if '-RequestPath' not in sys.argv: sys.exit(0)
request = json.loads(Path(sys.argv[sys.argv.index('-RequestPath')+1]).read_text())
Path(os.environ['TEST_BOUNDED_LOG']).write_text(json.dumps(request))
print(json.dumps({'id':'synthetic','name':'ok','mail':'me@example.com'}))
'''); executable.chmod(0o700)
            env = {"M365_CONFIG_DIR": str(root), "M365_ACCOUNTS_PATH": str(config), "M365_PWSH_BIN": str(executable), "TEST_BOUNDED_LOG": str(log)}
            with patch.dict(os.environ, env):
                client = mod.Client("example", "files"); client.require_write()
                body = {"name": "literal `no-command` $(no-command) Unicode 😀"}
                result = client.request("PATCH", "/drives/drive/items/item?@microsoft.graph.conflictBehavior=fail", body, {"If-Match": '"version"'})
            request = json.loads(log.read_text())
            self.assertEqual(result["id"], "synthetic")
            self.assertEqual(json.loads(request["body"]), body)
            self.assertEqual(request["expected_account"], "me@example.com")
            self.assertEqual(request["headers"], {"If-Match": '"version"'})
            self.assertEqual(request["uri"], "https://graph.microsoft.com/v1.0/drives/drive/items/item?@microsoft.graph.conflictBehavior=fail")
            # macOS Bash 3.2 treats an empty array as unset under nounset; exercise the real bridge's header-free identity request too.
            with patch.dict(os.environ, env):
                self.assertEqual(client.identity()["mail"], "me@example.com")
            read = json.loads(log.read_text())
            self.assertEqual(read["method"], "GET")
            self.assertEqual(read["headers"], {})
            self.assertEqual(read["uri"], "https://graph.microsoft.com/v1.0/me?$select=id,mail,userPrincipalName")

    def test_invalid_account_host_header_and_cross_capability_fail_before_transport(self):
        with self.assertRaises(ValueError): mod.Client("../other", "files")
        c = mod.Client("example", "files")
        with patch.object(c, "_call") as call:
            for path, headers in [("https://evil.example", {}), ("/me/messages/message", {}), ("/drives/d/items/i", {"Authorization": "anything"}), ("/drives/d/items/i", {"If-Match": "x\r\ny"})]:
                with self.assertRaises(ValueError): c.request("PATCH", path, {}, headers)
            call.assert_not_called()

    def test_transport_refuses_send_purge_permission_changes_and_unguarded_writes(self):
        cases = [("mail", "POST", "/me/messages/id/send", {}), ("mail", "DELETE", "/me/messages/id", None), ("files", "POST", "/drives/d/items/i/permanentDelete", {}), ("files", "PATCH", "/drives/d/items/i/permissions/p", {}), ("files", "PATCH", "/drives/d/items/i", {"name": "new"})]
        for service, method, path, body in cases:
            c = mod.Client("example", service)
            with patch.object(c, "_call") as call, self.assertRaises(ValueError): c.request(method, path, body)
            call.assert_not_called()

    def test_provider_diagnostics_are_not_reemitted(self):
        result = subprocess.CompletedProcess([], 1, "SECRET RESPONSE", "SECRET URL")
        with patch.object(mod.subprocess, "run", return_value=result):
            with self.assertRaises(mod.ProviderError) as error: mod.Client("example", "mail").identity()
        self.assertNotIn("SECRET", str(error.exception))

    def test_draft_attachment_metadata_is_bounded_and_body_updates_cannot_edit_recipients(self):
        client = mod.Client("example", "mail")
        with patch.object(client, "_call", return_value={"value": []}) as call:
            client.request("GET", "/me/messages/id/attachments?$select=id,name,contentType,size,isInline&$top=100")
            self.assertEqual(call.call_count, 1)
            call.reset_mock()
            for path in ("/me/messages/id/attachments", "/me/messages/id/attachments?$select=contentBytes", "/me/messages/id/attachments/attachment"):
                with self.assertRaises(ValueError): client.request("GET", path)
            with self.assertRaises(ValueError): client.request("PATCH", "/me/messages/id", {"toRecipients": []}, {"If-Match": "version"})
            call.assert_not_called()


if __name__ == "__main__": unittest.main()
