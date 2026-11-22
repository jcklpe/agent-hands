import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import temporary
from runtime_state import write


class TemporaryTests(unittest.TestCase):
    def test_private_cleanup_requires_age_registration_identity_and_dead_owner(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()
            fresh=temporary.create(root,os.getpid())
            record=__import__('json').loads((fresh/temporary.MARKER).read_text())
            self.assertEqual(temporary.candidates(root),[])
            record['created']=time.time()-90000
            write(fresh/temporary.MARKER,record)
            self.assertEqual(temporary.candidates(root),[])  # Old but live owner.
            with patch.object(temporary.os,'kill',side_effect=ProcessLookupError(3,'absent')):
                self.assertEqual(temporary.candidates(root),[fresh])
                (fresh/'linked').symlink_to(root)
                self.assertEqual(temporary.candidates(root),[])
                (fresh/'linked').unlink()
                record['inode']+=1;write(fresh/temporary.MARKER,record)
                self.assertEqual(temporary.candidates(root),[])
                record['inode']-=1;write(fresh/temporary.MARKER,record)
                raw_unregistered=root/(temporary.PREFIX+'old');raw_unregistered.mkdir(mode=0o700)
                self.assertEqual(temporary.cleanup(root),1)
                self.assertTrue(raw_unregistered.exists())

    def test_temp_refuses_checkout_and_unknown_liveness(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve();(root/'.git').mkdir()
            with self.assertRaises(ValueError): temporary.root_path(root)
            (root/'.git').rmdir()
            folder=temporary.create(root,os.getpid())
            record=__import__('json').loads((folder/temporary.MARKER).read_text());record['created']=time.time()-90000;write(folder/temporary.MARKER,record)
            with patch.object(temporary.os,'kill',side_effect=PermissionError(1,'denied')):
                self.assertEqual(temporary.candidates(root),[])

if __name__=='__main__': unittest.main()
