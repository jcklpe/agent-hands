#!/usr/bin/env python3
"""Synthetic source/data-root separation checks; no real account files are read."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROVIDERS = {
    'google': ('setup-google-services', 'GOOGLE', '_google_config_dir', 'google-accounts.json'),
    'microsoft': ('setup-microsoft-services', 'M365', '_m365_config_dir', 'm365-accounts.json'),
    'github': ('setup-github', 'GITHUB', '_github_config_dir', 'github-repos.json'),
    'trello': ('setup-trello', 'TRELLO', '_trello_config_dir', '.env'),
    'odoo': ('setup-odoo', 'ODOO', '_odoo_config_dir', 'odoo-accounts.json'),
}

class DataRoots(unittest.TestCase):
    def test_shell_data_roots(self):
        for provider, (skill, prefix, function, marker) in PROVIDERS.items():
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                source = root / skill
                (source / 'scripts').mkdir(parents=True)
                client = source / 'scripts/client.sh'
                shutil.copyfile(ROOT / skill / 'scripts/client.sh', client)
                env = {'PATH': os.environ['PATH'], 'HOME': temp}
                command = f'. "$1"; {prefix}_AUTH_DIR="$2"; {function}'
                def selected(extra=None):
                    return subprocess.check_output(['bash', '-c', command, 'bash', str(client), str(source)], env={**env, **(extra or {})}, text=True).strip()
                self.assertEqual(selected(), str(source))
                previous = root / ('authorize-' + provider)
                previous.mkdir()
                self.assertEqual(selected(), str(source), 'An empty old directory must not select a data store')
                private = previous / marker
                private.write_text('synthetic private data; never parsed by path selection')
                before = private.stat()
                self.assertEqual(selected(), str(previous))
                override = root / 'explicit-data'
                self.assertEqual(selected({prefix + '_CONFIG_DIR': str(override)}), str(override))
                after = private.stat()
                self.assertEqual((before.st_ino, before.st_size, before.st_mtime_ns), (after.st_ino, after.st_size, after.st_mtime_ns))

    def test_slack_data_roots(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            root = Path(temp).resolve()
            source = root / 'setup-slack'
            (source / 'scripts').mkdir(parents=True)
            script = source / 'scripts/slack_auth.py'
            shutil.copyfile(ROOT / 'setup-slack/scripts/slack_auth.py', script)
            spec = importlib.util.spec_from_file_location('provider_path_test_slack', script)
            module = importlib.util.module_from_spec(spec)
            with patch.object(Path, 'read_text', side_effect=AssertionError('Import must not read private data')):
                spec.loader.exec_module(module)
                self.assertEqual(module.config_dir(), source)
                previous = root / 'authorize-slack'
                previous.mkdir()
                self.assertEqual(module.config_dir(), source)
                (previous / '.env').touch()
                self.assertEqual(module.config_dir(), previous)
                os.environ['SLACK_ENV_FILE'] = str(root / 'chosen' / 'private.env')
                self.assertEqual(module.config_dir(), root / 'chosen')

if __name__ == '__main__':
    unittest.main()
