import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import collaboration as c
spec=importlib.util.spec_from_file_location('github_migration',SCRIPTS/'migrate-state.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.project=self.root/'project'
        subprocess.run(['git','init','-q',str(self.project)],check=True)
        subprocess.run(['git','-C',str(self.project),'remote','add','origin','https://github.com/example-owner/example-project.git'],check=True)
        (self.project/'.gitignore').write_text('/.github/project-collaboration/\n')
        self.env=patch.dict(os.environ,{'AGENT_HANDS_STATE_DIR':str(self.root/'private')});self.env.start();self.addCleanup(self.env.stop)
        self.source=self.project/'.github/project-collaboration/github.com_example-owner_example-project'
        self.source.mkdir(parents=True,mode=0o700);self.source.chmod(0o700)
        for p in [self.source.parent,self.source.parent.parent]:p.chmod(0o700)
        self.receipt=self.source/'operation.json';self.receipt.write_text('{"outcome":"uncertain","intent":"synthetic-digest"}');self.receipt.chmod(0o600)

    def test_move_preserves_uncertainty_and_default_route_with_old_writer_blocked(self):
        before=self.receipt.read_bytes()
        self.assertEqual(m.migrate(self.project,'example-owner/example-project')['status'],'github_journal_migration_preview')
        result=m.migrate(self.project,'example-owner/example-project',execute=True)
        self.assertTrue(result['contentsVerified'])
        target=c.default_journal_root()/self.source.name
        self.assertEqual((target/'operation.json').read_bytes(),before)
        ctx=SimpleNamespace(args=SimpleNamespace(project=str(self.project),state_dir=None),host='github.com',repo='example-owner/example-project')
        self.assertEqual(c.state_location(ctx),target)
        self.assertTrue((self.source/'lock').is_symlink())
        with self.assertRaises(OSError):os.open(self.source/'lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        with self.assertRaises(c.Refusal):m.migrate(self.project,'example-owner/example-project',execute=True)

    def test_active_lock_and_crash_preserve_records(self):
        import fcntl
        fd=os.open(self.source/'lock',os.O_RDWR|os.O_CREAT,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            with self.assertRaises(BlockingIOError):m.migrate(self.project,'example-owner/example-project',execute=True)
        finally:os.close(fd)
        with patch.object(m.os,'rename',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):m.migrate(self.project,'example-owner/example-project',execute=True)
        self.assertTrue(self.receipt.exists())
        self.assertTrue(list(c.default_journal_root().glob('.migration-*.json')))


if __name__=='__main__':unittest.main()
