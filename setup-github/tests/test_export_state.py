import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location('export_state',Path(__file__).resolve().parents[1]/'scripts/export_state.py')
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


class ExportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.dest=self.root/'output';self.dest.mkdir();(self.dest/'issues.md').write_text('old original')
        self.env=patch.dict(os.environ,{'AGENT_HANDS_STATE_DIR':str(self.root/'private')});self.env.start();self.addCleanup(self.env.stop)
        self.run=Path(m.begin(self.dest,os.getpid()));(self.run/'new/issues.md').write_text('new snapshot')
    def dead(self):return patch.object(m.os,'kill',side_effect=ProcessLookupError('synthetic stopped controller'))
    def test_complete_retains_original_and_failed_fetch_keeps_prior_output(self):
        m.publish(self.run,['issues.md']);self.assertEqual((self.dest/'issues.md').read_text(),'new snapshot')
        self.assertEqual((self.run/'previous/issues.md').read_text(),'old original')
        self.assertEqual(m.finish(self.run)['status'],'completed')
        record=m.read(self.run);record['status']='publishing';m.write(self.run/'publication.json',record)
        self.assertEqual(m.reconcile(self.run)['status'],'completed')
        with self.assertRaises(m.StorageError):m.publish(self.run,['issues.md'])
        other=Path(m.begin(self.dest,os.getpid()));m.finish(other)
        self.assertEqual(m.read(other)['status'],'retrieval_failed')
        self.assertTrue((self.dest/'issues.md').exists())
    def test_interruption_after_preimage_move_can_restore_only_missing_target(self):
        original=m.no_replace
        def stop(source,target):
            if Path(source)==self.run/'new/issues.md':raise OSError('simulated termination boundary')
            return original(source,target)
        with patch.object(m,'no_replace',side_effect=stop):
            with self.assertRaises(OSError):m.publish(self.run,['issues.md'])
        with self.assertRaises(m.StorageError):m.begin(self.dest,os.getpid())
        self.assertFalse((self.dest/'issues.md').exists());self.assertTrue((self.run/'previous/issues.md').exists())
        active=m.inspect(self.run)
        with self.assertRaises(m.StorageError):m.restore(self.run,active['hash'])
        with self.dead():
            view=m.inspect(self.run);self.assertTrue(view['entries'][0]['can_restore'])
            (self.dest/'issues.md').write_text('concurrent edit')
            with self.assertRaises(m.StorageError):m.restore(self.run,view['hash'])
            self.assertEqual((self.dest/'issues.md').read_text(),'concurrent edit')
            (self.dest/'issues.md').unlink()  # Synthetic fixture only.
            view=m.inspect(self.run);self.assertEqual(m.restore(self.run,view['hash'])['status'],'restored')
        self.assertEqual((self.dest/'issues.md').read_text(),'old original')
    def test_new_target_race_is_never_overwritten(self):
        source=self.root/'source';source.write_text('old source')
        target=self.root/'target';target.write_text('concurrent content')
        with self.assertRaises(FileExistsError):m.no_replace(source,target)
        self.assertEqual(target.read_text(),'concurrent content');self.assertTrue(source.exists())
        directory=self.root/'source-dir';directory.mkdir();(directory/'old').write_text('old')
        destination=self.root/'new-dir';destination.mkdir();(destination/'new').write_text('concurrent')
        with self.assertRaises(FileExistsError):m.no_replace(directory,destination)
        self.assertTrue((destination/'new').exists());self.assertTrue((directory/'old').exists())

    def test_retirement_never_expires_uncertain_or_live_records(self):
        record=m.read(self.run);record['created']=time.time()-8*86400;m.write(self.run/'publication.json',record)
        with self.dead():self.assertFalse(m.retirement(self.run)['eligible'])
        m.publish(self.run,['issues.md'])
        self.assertFalse(m.retirement(self.run)['eligible'])
        with self.dead():
            view=m.retirement(self.run);self.assertTrue(view['eligible'])
            with self.assertRaises(m.StorageError):m.retirement(self.run,True,'stale')
            self.assertEqual(m.retirement(self.run,True,view['hash'])['removed'],1)
        self.assertEqual((self.dest/'issues.md').read_text(),'new snapshot')
    def test_legacy_staging_blocks_new_export_without_discarding_it(self):
        legacy=self.dest/'.github-export.older';legacy.mkdir();(legacy/'original.md').write_text('retained original')
        with self.assertRaises(m.StorageError):m.begin(self.dest,os.getpid())
        self.assertEqual((legacy/'original.md').read_text(),'retained original')

    def test_symlink_and_escaping_artifact_refuse_without_touching_old_output(self):
        for name in ['../escape','/absolute']:
            with self.assertRaises(m.StorageError):m.publish(self.run,[name])
        (self.run/'new/issues.md').unlink();(self.run/'new/issues.md').symlink_to(self.dest/'issues.md')
        with self.assertRaises(m.StorageError):m.publish(self.run,['issues.md'])
        self.assertEqual((self.dest/'issues.md').read_text(),'old original')

if __name__=='__main__':unittest.main()
