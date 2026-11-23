import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('private_settings',Path(__file__).resolve().parents[1]/'scripts/private_settings.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.source=self.root/'checkout/setup-demo';self.source.mkdir(parents=True);(self.source.parent/'.git').mkdir()
        self.env=patch.dict(os.environ,{'AGENT_HANDS_STATE_DIR':str(self.root/'private')},clear=True);self.env.start();self.addCleanup(self.env.stop)
        (self.source/'.env').write_text('DEMO_ACCOUNTS_PATH=accounts.json\n')
        (self.source/'accounts.json').write_text(json.dumps({'accounts':[{'token_path':'tokens/demo.json'}]}))
        (self.source/'tokens').mkdir();(self.source/'tokens/demo.json').write_text('synthetic refresh cache')
        self.settings=m.Settings('demo',self.source,'DEMO','accounts.json','DEMO_ACCOUNTS_PATH',fields=(('token_path',None),),patterns=('renew-*.json','renew-*.lock'))
    def test_move_preserves_signin_and_pending_records_and_refuses_lost_destination(self):
        (self.source/'renew-demo.json').write_text('{"status":"uncertain"}')
        units=self.settings.units();self.assertEqual(self.settings.migrate()['units'],4)
        self.assertFalse(self.settings.target.exists())
        with self.assertRaises(m.StorageError):self.settings.selection()
        self.settings.migrate(True)
        for unit in units:self.assertEqual(m.fingerprint(Path(unit['destination'])),unit['hash'])
        self.assertEqual((self.settings.selection()/'tokens/demo.json').read_text(),'synthetic refresh cache')
        self.assertIn('uncertain',(self.settings.target/'renew-demo.json').read_text())
        self.settings.target.rename(self.settings.target.with_name('preserved'))
        with self.assertRaises(m.StorageError):self.settings.selection()
    def test_active_renewal_lock_refuses_and_existing_files_survive(self):
        file=self.source/'renew-demo.lock';fd=os.open(file,os.O_RDWR|os.O_CREAT,0o600);fcntl.flock(fd,fcntl.LOCK_EX)
        try:
            with self.assertRaises(BlockingIOError):self.settings.migrate(True)
            self.assertTrue((self.source/'tokens/demo.json').exists())
        finally:os.close(fd)
    def test_failure_after_dispatch_preserves_blocking_record_without_retry(self):
        original=os.rename;calls=0
        def fail(source,dest):
            nonlocal calls
            calls+=1
            if calls==2:raise OSError('injected')
            original(source,dest)
        with patch.object(m.os,'rename',side_effect=fail):
            with self.assertRaises(OSError):self.settings.migrate(True)
        self.assertTrue(self.settings.pending.exists())
        with self.assertRaises(m.StorageError):self.settings.selection()
        with self.assertRaises(m.StorageError):self.settings.migrate(True)
        self.assertTrue((self.settings.target/'.env').exists())
        self.assertTrue((self.source/'accounts.json').exists())
    def test_overrides_escaping_paths_collisions_and_unsafe_roots_refuse(self):
        with patch.dict(os.environ,{'DEMO_CONFIG_DIR':str(self.source)}):
            with self.assertRaises(m.StorageError):self.settings.migrate(True)
        for bad in ['../escape','/absolute','']:
            (self.source/'accounts.json').write_text(json.dumps({'accounts':[{'token_path':bad}]}))
            with self.assertRaises(m.StorageError):self.settings.units()
        with patch.dict(os.environ,{'AGENT_HANDS_STATE_DIR':str(self.source/'private')}):
            with self.assertRaises(m.StorageError):self.settings.selection()

if __name__=='__main__':unittest.main()
