import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/runtime_state.py'
spec = importlib.util.spec_from_file_location('runtime_state', SCRIPT)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); self.repo = self.root / 'repo'; self.repo.mkdir(); (self.repo / '.git').mkdir()
        self.env = patch.dict(os.environ, {'AGENT_HANDS_STATE_DIR': str(self.root / 'private')}, clear=True); self.env.start(); self.addCleanup(self.env.stop)
        self.owner = patch.object(m, 'ROOT', self.repo); self.owner.start(); self.addCleanup(self.owner.stop)
        for folder, names in m.GROUPS.values(): (self.repo / folder).mkdir()
        self.config = self.repo / 'setup-microsoft-services'
        (self.config / '.env').write_text('M365_ACCOUNTS_PATH=m365-accounts.json\n')
        (self.config / 'm365-accounts.json').write_text(json.dumps({'accounts':[{'alias':'demo','auth_provider':'msal','token_path':'token.json'}]}))
        (self.config / 'token.json').write_text('synthetic token cache')
        self.journals = self.repo / 'use-outlook-mail/.draft-state'; self.journals.mkdir(mode=0o700)
        (self.journals / 'uncertain.json').write_text('{"status":"uncertain"}')
        for file in self.repo.rglob('*'):
            if file.is_file(): file.chmod(0o600)

    def test_preview_then_complete_move_preserves_all_bytes_and_default_selection(self):
        self.assertEqual(m.migrate()['status'], 'microsoft_migration_preview')
        self.assertFalse(m.base().exists())
        with self.assertRaises(m.StateError): m.location('config')
        before = {u['destination']:u['hash'] for u in m.migration_plan()}
        self.assertEqual(m.migrate(True)['verified_units'], 4)
        for dest, digest in before.items(): self.assertEqual(m.fingerprint(Path(dest)),digest)
        self.assertFalse((self.journals / 'uncertain.json').exists())
        self.assertTrue((m.location('mail') / '.draft-state/uncertain.json').exists())
        self.assertEqual(m.location('config'), m.base() / 'config')
        self.assertFalse((m.base() / '.migration.json').exists())
        empty = m.location('files'); empty.rmdir()
        with self.assertRaises(m.StateError): m.location('files')

    def test_override_collision_symlink_and_checkout_refuse(self):
        with patch.dict(os.environ, {'M365_CONFIG_DIR': str(self.config)}):
            with self.assertRaises(m.StateError): m.migrate(True)
        with patch.dict(os.environ, {'AGENT_HANDS_STATE_DIR':str(self.repo / 'state')}):
            with self.assertRaises(m.StateError): m.base()
        (self.root / 'link').symlink_to(self.root / 'private')
        with patch.dict(os.environ, {'AGENT_HANDS_STATE_DIR':str(self.root / 'link')}):
            with self.assertRaises(m.StateError): m.base()
        (m.base() / 'config').mkdir(parents=True)
        (m.base() / 'config/.env').write_text('existing')
        with self.assertRaises(m.StateError): m.migrate(True)

    def test_failure_after_one_move_blocks_new_default_and_retains_recovery(self):
        rename = os.rename; count = 0
        def fail_second(source, dest):
            nonlocal count
            count += 1
            if count == 2: raise OSError('synthetic move failure')
            return rename(source, dest)
        with patch.object(m.os, 'rename', fail_second):
            with self.assertRaises(OSError): m.migrate(True)
        self.assertTrue((m.base() / '.migration.json').exists())
        with self.assertRaises(m.StateError): m.location('mail')
        with self.assertRaises(m.StateError): m.migrate(True)
        self.assertTrue((m.base() / 'config/.env').exists())
        self.assertTrue((self.config / 'm365-accounts.json').exists())

    def test_unsafe_relative_paths_and_locks_preserve_source(self):
        for token in ['', '.', '../escape', '/absolute']:
            (self.config / 'm365-accounts.json').write_text(json.dumps({'accounts':[{'alias':'demo','token_path':token}]}))
            with self.assertRaises(m.StateError): m.migration_plan()
        (self.config / 'm365-accounts.json').write_text('{"accounts":[]}')
        (self.journals / 'operation.lock').write_text('')
        (self.journals / 'operation.lock').chmod(0o600)
        with self.assertRaises(m.StateError): m.migrate(True)
        self.assertTrue((self.config / '.env').exists())


if __name__ == '__main__': unittest.main()
