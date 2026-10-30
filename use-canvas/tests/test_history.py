import datetime as dt
import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from canvas_fixture import TOKEN
from canvas_auth import CanvasError
from canvas_history import History

UTC = dt.timezone.utc


class HistoryTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root/'history'
        self.now = dt.datetime(2026,10,30,12,tzinfo=UTC)
        self.history = History(self.path,now=self.now)

    def record(self, **kwargs):
        return self.history.record(command='export', account='example',kind='export',course_ids=['123'],outcome='published',**kwargs)

    def test_schema_sorted_keys_owner_only_and_filters(self):
        row = self.record(counts={'pages':3})
        file = self.path/'2026-10.jsonl'
        self.assertEqual(file.read_bytes(),(json.dumps(row,sort_keys=True,ensure_ascii=False)+'\n').encode())
        self.assertEqual(row['schema_version'],1)
        self.assertEqual(len(list(self.history.rows(account='example',course='123',kind='export',since='2026-10-30',until='2026-10-30'))),1)
        self.assertEqual(list(self.history.rows(course='999')),[])
        if os.name!='nt':
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            self.assertEqual(self.path.stat().st_mode & 0o777,0o700)
        self.assertNotIn(TOKEN,file.read_text())
        with self.assertRaises(CanvasError):
            self.record(body='must not be allowed')

    def test_query_opens_only_requested_months(self):
        self.record()
        (self.path/'2026-09.jsonl').write_text('deliberately malformed older month')
        self.assertEqual(len(list(self.history.rows(since='2026-10-01',until='2026-10-31'))),1)
        with self.assertRaises(CanvasError):
            list(self.history.rows(since='not a date'))

    def test_compression_is_byte_stable_and_query_reads_gzip(self):
        old = History(self.path,now=dt.datetime(2026,6,1,tzinfo=UTC))
        old.record(command='courses',account='example',kind='read',course_ids=[],outcome='complete')
        old_bytes=(self.path/'2026-06.jsonl').read_bytes()
        self.record()
        compressed=(self.path/'2026-06.jsonl.gz').read_bytes()
        self.assertEqual(gzip.decompress(compressed),old_bytes)
        self.assertFalse((self.path/'2026-06.jsonl').exists())
        self.record()
        self.assertEqual((self.path/'2026-06.jsonl.gz').read_bytes(),compressed)
        self.assertEqual(len(list(self.history.rows(since='2026-06-01',until='2026-06-30'))),1)
        # Recompress identical monthly bytes in another directory.
        other=self.root/'other'
        other.mkdir(mode=0o700)
        (other/'2026-06.jsonl').write_bytes(old_bytes)
        History(other,now=self.now).record(command='courses',account='example',kind='read',course_ids=[])
        self.assertEqual((other/'2026-06.jsonl.gz').read_bytes(),compressed)

    def test_prune_preview_and_explicit_execute(self):
        old=History(self.path,now=dt.datetime(2026,6,1,tzinfo=UTC))
        old.record(command='courses',account='example',kind='read',course_ids=[])
        result=self.history.prune('example','2026-07')
        self.assertEqual(result['mode'],'preview')
        self.assertTrue((self.path/'2026-06.jsonl').exists())
        self.history.prune('example','2026-07',execute=True)
        self.assertFalse((self.path/'2026-06.jsonl').exists())

    def test_uncertain_write_blocks_prune_until_resolution(self):
        old=History(self.path,now=dt.datetime(2026,6,1,tzinfo=UTC))
        row=old.record(command='edit-page',account='example',kind='write',course_ids=['123'],outcome='uncertain')
        with self.assertRaises(CanvasError):
            self.history.prune('example','2026-07',True)
        self.history.resolve('example',row['record_id'],True)
        self.history.prune('example','2026-07',True)
        self.assertFalse((self.path/'2026-06.jsonl.gz').exists())
        self.assertEqual(list(self.history.rows())[-1]['outcome'],'landed')

    def test_symlink_directories_and_month_files_refused(self):
        self.path.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(CanvasError):
            History(self.path)
        self.path.unlink()
        self.path.mkdir(mode=0o700)
        target=self.root/'target'
        target.write_text('preserve')
        (self.path/'2026-10.jsonl').symlink_to(target)
        with self.assertRaises(CanvasError):
            self.record()
        self.assertEqual(target.read_text(),'preserve')

    def test_directory_precedence_and_invalid_retention(self):
        with patch.dict(os.environ,{'CANVAS_HISTORY_DIR':str(self.path)}):
            self.assertEqual(History().path,self.path)
            self.assertEqual(History(self.root/'explicit').path,self.root/'explicit')
        with self.assertRaises(CanvasError):
            History(self.path,plain_months=0)

    def test_failed_compression_preserves_plain_month_and_can_retry(self):
        old = History(self.path,now=dt.datetime(2026,6,1,tzinfo=UTC))
        old.record(command='courses',account='example',kind='read',course_ids=[])
        original = (self.path/'2026-06.jsonl').read_bytes()
        with patch('canvas_history.gzip.GzipFile',side_effect=OSError('synthetic failure')), self.assertRaises(OSError):
            self.record()
        self.assertEqual((self.path/'2026-06.jsonl').read_bytes(),original)
        self.assertFalse((self.path/'2026-06.jsonl.gz').exists())
        self.assertFalse(list(self.path.glob('.compress-*')))
        self.record()
        self.assertEqual(gzip.decompress((self.path/'2026-06.jsonl.gz').read_bytes()),original)


if __name__=='__main__':
    unittest.main()
