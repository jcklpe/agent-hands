import copy
import datetime as dt
import hashlib
import json
import re
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from canvas_fixture import CanvasFixture, FileOpener, FileResponse, IMAGE, ORIGIN, TOKEN
from canvas_auth import CanvasError
from canvas_export import download, export


def tree(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name != 'run.json'}


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / 'snapshot'

    def run_export(self, fixture=None, **options):
        fixture = fixture or CanvasFixture()
        return export(fixture.reader(), ['123'], self.output, downloader=fixture.download, **options)

    def test_determinism_across_clock_paging_order_and_volatile_fields(self):
        first_fixture = CanvasFixture(page_size=1)
        first = self.run_export(first_fixture, now=dt.datetime(2026,10,1,tzinfo=dt.timezone.utc))
        self.assertTrue(first['published'])
        before = tree(self.output)
        old_run = (self.output / 'run.json').read_bytes()
        second_fixture = CanvasFixture(reverse=True)
        second_fixture.data['files'][0]['url'] += '-changed'
        second_fixture.data['files'][0]['thumbnail_url'] = 'https://other.example.net/thumb'
        second_fixture.data['discussions'][0]['read_state'] = 'read'
        self.run_export(second_fixture, now=dt.datetime(2026,10,2,tzinfo=dt.timezone.utc))
        self.assertEqual(before, tree(self.output))
        self.assertNotEqual(old_run, (self.output / 'run.json').read_bytes())
        self.assertEqual(first_fixture.downloads, ['900'])
        self.assertEqual((self.output / 'courses/course-123/images/file-900.png').read_bytes(), IMAGE)
        page = (self.output / 'courses/course-123/pages/page-789.md').read_text()
        self.assertIn('../images/file-900.png', page)
        self.assertIn('2026-11-01T01:30:00-06:00', (self.output / 'courses/course-123/assignments/assignment-456.md').read_text())
        self.assertNotIn(TOKEN, str(before))
        self.assertNotIn('?verifier=', str(before))
        for document in self.output.rglob('*.md'):
            for href in re.findall(r'\]\(([^)]+)\)',document.read_text()):
                if '://' not in href:
                    self.assertTrue((document.parent/href).is_file(),f'Broken local export link: {href}')


    def test_failed_assignment_listing_preserves_every_byte(self):
        self.run_export()
        before = {str(p):p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        fixture = CanvasFixture()
        fixture.failures['/api/v1/courses/123/assignments'] = (500,{})
        result = self.run_export(fixture)
        self.assertFalse(result['published'])
        self.assertEqual(before, {str(p):p.read_bytes() for p in self.output.rglob('*') if p.is_file()})
        self.assertEqual(result['coverage'][0]['coverage']['assignments']['status'], 'failed')
        self.assertFalse(list(self.root.glob('.canvas-*')))
        self.assertTrue(self.run_export(fixture, allow_partial=True)['published'])
        coverage = json.loads((self.output / 'courses/course-123/coverage.json').read_text())
        self.assertEqual(coverage['assignments']['status'], 'failed')

    def test_image_failure_blocks_and_allow_partial_records_it(self):
        fixture = CanvasFixture()
        fixture.download = lambda *args, **kwargs: (_ for _ in ()).throw(CanvasError('network_error', 'synthetic'))
        self.assertFalse(self.run_export(fixture)['published'])
        self.assertFalse(self.output.exists())
        self.assertTrue(self.run_export(fixture, allow_partial=True)['published'])
        cov = json.loads((self.output / 'courses/course-123/coverage.json').read_text())
        self.assertEqual(cov['images']['status'], 'partial')
        self.assertEqual(cov['images']['missing'], ['file:900'])

    def test_external_and_decorative_images_are_not_downloaded_and_shared_image_is_once(self):
        fixture = CanvasFixture()
        fixture.data['pages'].append(dict(fixture.data['pages'][0], page_id='791', url='second'))
        fixture.data['pages'][0]['body'] += '<img src="https://assets.example.net/other.png" alt="External"><img src="/files/901" alt=""><img src="/files/902" width="20" height="20">'
        self.run_export(fixture)
        self.assertEqual(fixture.downloads, ['900'])
        self.assertIn('external_image', (self.output / 'courses/course-123/course.md').read_text())

    def test_arbitrary_existing_directory_and_symlinks_are_refused(self):
        self.output.mkdir()
        (self.output/'precious.txt').write_text('keep')
        with self.assertRaises(CanvasError):
            self.run_export()
        self.assertEqual((self.output/'precious.txt').read_text(), 'keep')
        link = self.root/'symlink'
        link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaises(CanvasError):
            export(CanvasFixture().reader(), ['123'], link)

    def test_swap_failure_restores_previous_export(self):
        self.run_export()
        before = tree(self.output)
        import os
        original = os.rename
        def rename(src, dst):
            if Path(src).name.startswith('.canvas-export-'):
                raise OSError('synthetic rename failure')
            return original(src,dst)
        with patch('canvas_export.os.rename', side_effect=rename), self.assertRaises(OSError):
            self.run_export()
        self.assertEqual(before, tree(self.output))

    def test_denied_course_still_exports_course_coverage(self):
        fixture = CanvasFixture()
        fixture.failures['/api/v1/courses/123'] = (403, {})
        self.assertTrue(self.run_export(fixture)['published'])
        self.assertTrue((self.output/'courses/course-123/course.json').exists())
        coverage = json.loads((self.output/'courses/course-123/coverage.json').read_text())
        self.assertEqual(coverage['course']['status'], 'denied')
        self.assertEqual(coverage['pages']['status'], 'not_requested')


class DownloadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root/'file.png'
        self.meta = {'id':'900','size':len(IMAGE),'url':ORIGIN+'/files/900/download?verifier=ephemeral'}
        self.client = CanvasFixture().client()

    def test_streamed_download_size_digest_and_overwrite(self):
        result = download(self.client,self.meta,self.output,opener=FileOpener(FileResponse(IMAGE)))
        self.assertEqual(result['sha256'], hashlib.sha256(IMAGE).hexdigest())
        self.assertEqual(self.output.read_bytes(), IMAGE)
        with self.assertRaises(CanvasError):
            download(self.client,self.meta,self.output,opener=FileOpener())
        download(self.client,self.meta,self.output,force=True,opener=FileOpener(FileResponse(IMAGE)))

    def test_redirect_to_storage_never_gets_token_even_on_return(self):
        opener = FileOpener(FileResponse(status=302,headers={'Location':'https://storage.example.net/signed-file'}),FileResponse(status=302,headers={'Location':ORIGIN+'/files/900/download'}),FileResponse(IMAGE))
        download(self.client,self.meta,self.output,opener=opener)
        self.assertEqual(opener.sent[0].get_header('Authorization'), 'Bearer '+TOKEN)
        self.assertIsNone(opener.sent[1].get_header('Authorization'))
        self.assertIsNone(opener.sent[2].get_header('Authorization'))
        self.meta['url'] = 'https://storage.example.net/signed-file'
        opener = FileOpener(FileResponse(IMAGE))
        download(self.client,self.meta,self.root/'second',opener=opener)
        self.assertIsNone(opener.sent[0].get_header('Authorization'))

    def test_size_mismatch_and_limit_leave_no_partial_file(self):
        with self.assertRaises(CanvasError) as raised:
            download(self.client,self.meta,self.output,opener=FileOpener(FileResponse(b'short')))
        self.assertEqual(raised.exception.kind, 'download_size_mismatch')
        self.assertEqual(list(self.root.iterdir()), [])
        opener = FileOpener()
        with self.assertRaises(CanvasError):
            download(self.client,self.meta,self.output,max_bytes=1,opener=opener)
        self.assertEqual(opener.sent, [])
        self.meta['size']=1
        with self.assertRaises(CanvasError):
            download(self.client,self.meta,self.output,max_bytes=2,opener=FileOpener(FileResponse(IMAGE)))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsafe_redirect_and_network_error_are_bounded(self):
        for opener in (FileOpener(FileResponse(status=302,headers={'Location':'http://storage.example.net/file'})), FileOpener(urllib.error.URLError('secret URL must not be echoed'))):
            with self.assertRaises(CanvasError) as raised:
                download(self.client,self.meta,self.output,opener=opener)
            self.assertNotIn('secret URL',str(raised.exception))
            self.assertNotIn(TOKEN,str(raised.exception))
            self.assertFalse(self.output.exists())

    def test_large_download_reads_bounded_chunks(self):
        content = b'x' * (3 * 1024 * 1024)
        self.meta['size'] = len(content)
        class BoundedResponse(FileResponse):
            def read(self, n=-1):
                if not 0 < n <= 1024 * 1024:
                    raise AssertionError('Download must stream bounded chunks')
                return super().read(n)
        download(self.client,self.meta,self.output,opener=FileOpener(BoundedResponse(content)))
        self.assertEqual(self.output.stat().st_size,len(content))


if __name__ == '__main__':
    unittest.main()
