#!/usr/bin/env python3
"""Synthetic configuration-root checks; no real account files are read."""
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
    'google': ('setup-google-services', 'GOOGLE', '_google_config_dir'),
    'microsoft': ('setup-microsoft-services', 'M365', '_m365_config_dir'),
    'github': ('setup-github', 'GITHUB', '_github_config_dir'),
    'trello': ('setup-trello', 'TRELLO', '_trello_config_dir'),
    'odoo': ('setup-odoo', 'ODOO', '_odoo_config_dir'),
}

class DataRoots(unittest.TestCase):
    def test_shell_data_roots(self):
        for provider, (skill, prefix, function) in PROVIDERS.items():
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
                override = root / 'explicit-data'
                self.assertEqual(selected({prefix + '_CONFIG_DIR': str(override)}), str(override))

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
                os.environ['SLACK_ENV_FILE'] = str(root / 'chosen' / 'private.env')
                self.assertEqual(module.config_dir(), root / 'chosen')

if __name__ == '__main__':
    unittest.main()
