import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('chat_journal', Path(__file__).resolve().parents[1] / 'scripts/chat_journal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class JournalTests(unittest.TestCase):
    def test_failed_sync_preserves_prior_receipt_and_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            receipt = root / 'receipt.json'
            module.write_journal(receipt, 'pending', 'comment', 'a' * 64, '')
            original = receipt.read_bytes()
            with patch.object(module.os, 'fsync', side_effect=OSError('synthetic sync failure')):
                with self.assertRaises(OSError):
                    module.write_journal(receipt, 'verified', 'comment', 'a' * 64, 'message-1')
            self.assertEqual(receipt.read_bytes(), original)
            self.assertEqual(list(root.iterdir()), [receipt])
            module.write_journal(receipt, 'verified', 'comment', 'a' * 64, 'message-1')
            self.assertEqual(json.loads(receipt.read_text())['state'], 'verified')
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)

    def test_unsafe_state_refuses_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / 'original'
            original.write_text('preserve')
            receipt = root / 'receipt'
            receipt.symlink_to(original)
            with self.assertRaises(ValueError):
                module.write_journal(receipt, 'pending', 'comment', 'a' * 64, '')
            self.assertEqual(original.read_text(), 'preserve')
            receipt.unlink()
            root.chmod(0o755)
            with self.assertRaises(ValueError):
                module.write_journal(receipt, 'pending', 'comment', 'a' * 64, '')
            self.assertFalse(receipt.exists())
            root.chmod(0o700)
