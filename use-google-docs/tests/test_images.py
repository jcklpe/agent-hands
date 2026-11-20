import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('images', Path(__file__).parents[1] / 'scripts/images.py')
images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(images)


def document(revision='r1', ident='object-one', suggested=False):
    part = {'startIndex': 3, 'endIndex': 4, 'inlineObjectElement': {'inlineObjectId': ident}}
    if suggested:
        part['suggestedInsertionIds'] = ['suggestion']
    return {'documentId': 'document-one', 'revisionId': revision, 'tabs': [{'tabProperties': {'tabId': 'tab-one'}, 'documentTab': {'inlineObjects': {ident: {'inlineObjectProperties': {'embeddedObject': {'size': {'width': {'magnitude': 1, 'unit': 'PT'}}, 'imageProperties': {'contentUri': 'https://example.googleusercontent.com/image'}}}}}, 'body': {'content': [{'paragraph': {'elements': [part]}}]}}}]}


def text_fn(doc):
    return [{'id': 'tab-one', 'text': doc.get('test_text', 'Original text\n')}]


def location(tab, index):
    return {'tabId': tab, 'index': index}


def range_fn(tab, start, end):
    return {'tabId': tab, 'startIndex': start, 'endIndex': end}


def folder():
    return {'id': 'folder-one', 'mimeType': 'application/vnd.google-apps.folder', 'ownedByMe': True, 'capabilities': {'canAddChildren': True}, 'permissions': [{'type': 'user', 'role': 'owner'}]}


class ImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.file = self.root / 'source.png'
        self.file.write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00'*8 + struct.pack('>II', 80, 40))
        self.raw = [{'object_id': 'object-one', 'image_file': str(self.file), 'width_pt': 400}]

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, doc=None, raw=None):
        return images.prepare(doc or document(), self.raw if raw is None else raw, 'example', 'folder-one', text_fn)

    def test_dimensions(self):
        self.assertEqual(images.dimensions(self.file.read_bytes()), ('png', 80, 40))
        self.assertEqual(images.dimensions(b'GIF89a'+struct.pack('<HH', 20, 30)), ('gif', 20, 30))
        with self.assertRaises(ValueError):
            images.dimensions(b'not an image')

    def test_inventory_tab_and_native_index(self):
        row = images.inline_images(document())[0]
        self.assertEqual((row['tab_id'], row['index'], row['object_id']), ('tab-one', 3, 'object-one'))

    def test_missing_or_ambiguous_targets_fail(self):
        self.raw[0]['object_id'] = 'absent'
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.prepare()

    def test_pending_suggestion_and_duplicate_target_fail(self):
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.prepare(document(suggested=True))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.prepare(raw=self.raw*2)

    def test_revision_width_and_unknown_fields_fail(self):
        d = document(); d.pop('revisionId')
        with self.assertRaisesRegex(ValueError, 'revision'):
            self.prepare(d)
        self.raw[0].pop('width_pt')
        with self.assertRaisesRegex(ValueError, 'width_pt'):
            self.prepare()
        self.raw[0]['arbitrary_request'] = {}
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            self.prepare()

    def test_source_changes_and_revision_change_fingerprint(self):
        _, a = self.prepare()
        _, b = self.prepare(document('r2'))
        self.assertNotEqual(a, b)
        self.file.write_bytes(self.file.read_bytes() + b'changed')
        _, c = self.prepare()
        self.assertNotEqual(a, c)

    def test_effects_and_symlink_sources_fail(self):
        d = document(); d['tabs'][0]['documentTab']['inlineObjects']['object-one']['inlineObjectProperties']['embeddedObject']['imageProperties']['angle'] = 1
        with self.assertRaisesRegex(ValueError, 'effects'):
            self.prepare(d)
        link = self.root / 'link.png'; link.symlink_to(self.file)
        self.raw[0]['image_file'] = str(link)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.prepare()

    def test_carrier_contains_only_selected_original_image(self):
        plan, _ = self.prepare()
        with zipfile.ZipFile(io.BytesIO(images.carrier_docx(plan['replacements']))) as z:
            self.assertEqual(z.read('word/media/image1.png'), self.file.read_bytes())
            self.assertIn(b'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', z.read('word/_rels/document.xml.rels'))
        self.file.write_bytes(self.file.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            images.carrier_docx(plan['replacements'])

    def test_reinsertion_uses_exact_single_character_range_and_explicit_size(self):
        plan, _ = self.prepare()
        requests = images.build_requests(plan['replacements'], ['https://example.googleusercontent.com/image'], location, range_fn)
        self.assertEqual(requests[0]['deleteContentRange']['range'], range_fn('tab-one', 3, 4))
        self.assertEqual(requests[1]['insertInlineImage']['objectSize']['height']['magnitude'], 200)

    def test_verification_rejects_text_or_unaffected_image_changes(self):
        before = {'text_sha256': 'same', 'images': [{'tab_id':'t','index':1,'sha256':'old','object_id':'a'}, {'tab_id':'t','index':4,'sha256':'untouched','object_id':'b'}]}
        after = copy.deepcopy(before); after['images'][0].update(sha256=images.digest(b'new'), object_id='new-object')
        plan=[{'tab_id':'t','index':1}]
        images.verify(before, after, plan, [b'new'])
        after['text_sha256']='changed'
        with self.assertRaisesRegex(RuntimeError, 'text'):
            images.verify(before, after, plan, [b'new'])
        after['text_sha256']='same'; after['images'][1]['sha256']='changed'
        with self.assertRaisesRegex(RuntimeError, 'byte'):
            images.verify(before, after, plan, [b'new'])

    def test_dry_run_and_stale_preview_never_create_import(self):
        source = self.root/'plan.json'; source.write_text(json.dumps(self.raw))
        args = argparse.Namespace(document_id='document-one', plan=str(source), temporary_folder='folder-one', execute=False, expect=None, record=None)
        api = {'access_token':lambda:'fake', 'document_id_from':lambda a:a.document_id, 'get_document':lambda i,t:document(), 'document_tabs':text_fn, 'api_json':lambda *a:folder()}
        with patch.object(images, 'import_carrier') as create, patch('sys.stdout', new=io.StringIO()):
            self.assertEqual(images.command_replace(args, api), 0); create.assert_not_called()
            args.execute=True; args.expect='stale'
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                images.command_replace(args, api)
            create.assert_not_called()

    def test_unavailable_image_is_explicit_not_a_broken_download(self):
        d = document()
        d['tabs'][0]['documentTab']['inlineObjects']['object-one']['inlineObjectProperties']['embeddedObject']['imageProperties'] = {}
        with patch.object(images, 'content_bytes') as fetch:
            state, blobs = images.snapshot(d, text_fn)
            self.assertTrue(state['images'][0]['unavailable'])
            self.assertIsNone(state['images'][0]['sha256'])
            self.assertIsNone(blobs[('tab-one', 3)])
            fetch.assert_not_called()

    def test_zero_crop_is_not_an_effect(self):
        d = document()
        d['tabs'][0]['documentTab']['inlineObjects']['object-one']['inlineObjectProperties']['embeddedObject']['imageProperties']['cropProperties'] = {'offsetLeft': 0, 'offsetRight': 0, 'angle': 0}
        self.prepare(d)

    def test_reencoded_target_requires_exact_source_identity_and_dimensions(self):
        before = {'text_sha256':'same','images':[{'tab_id':'t','index':1,'sha256':None,'object_id':'old'}]}
        after = {'text_sha256':'same','images':[{'tab_id':'t','index':1,'sha256':'reencoded','object_id':'new','source_uri_sha256':'exact-import','pixel_width':80,'pixel_height':40}]}
        plan=[{'tab_id':'t','index':1,'pixel_width':80,'pixel_height':40}]
        images.verify(before,after,plan,[b'import-bytes'],{('t',1):'exact-import'})
        with self.assertRaisesRegex(RuntimeError,'identity'):
            images.verify(before,after,plan,[b'import-bytes'],{('t',1):'other-import'})
        after['images'][0]['pixel_width']=40
        with self.assertRaisesRegex(RuntimeError,'identity'):
            images.verify(before,after,plan,[b'import-bytes'],{('t',1):'exact-import'})

    def test_content_uri_rejects_non_google_sources_without_request(self):
        with patch.object(images.urllib.request, 'build_opener') as fetch:
            for uri in ['http://example.googleusercontent.com/a','https://example.org/a','https://googleusercontent.com.example.org/a', 'https://name:secret@example.googleusercontent.com/a', 'https://example.googleusercontent.com:8443/a']:
                with self.assertRaises(ValueError):images.content_bytes(uri)
            fetch.assert_not_called()

    def test_content_redirects_cannot_leave_google_https(self):
        request = images.urllib.request.Request('https://example.googleusercontent.com/image')
        for url in ['https://example.org/secret', 'http://example.googleusercontent.com/image', 'http://127.0.0.1/']:
            with self.assertRaises(ValueError):
                images.ContentRedirect().redirect_request(request, None, 302, 'redirect', {}, url)
        redirect = images.ContentRedirect().redirect_request(request, None, 302, 'redirect', {}, 'https://other.googleusercontent.com/image')
        self.assertEqual(redirect.host, 'other.googleusercontent.com')

    def test_authenticated_import_redirect_is_refused(self):
        request = images.urllib.request.Request(images.DRIVE, headers={'Authorization': 'Bearer synthetic-token'})
        with self.assertRaisesRegex(ValueError, 'no credential'):
            images.NoRedirect().redirect_request(request, None, 302, 'redirect', {}, 'https://example.org/')

    def test_shared_or_unverifiable_import_folders_fail_before_writes(self):
        for change in [{'permissions': []}, {'permissions': [{'type': 'anyone', 'role': 'reader'}]}, {'permissions': [{'type': 'user', 'role': 'owner'}, {'type': 'user', 'role': 'reader'}]}, {'ownedByMe': False}, {'driveId': 'shared-drive'}]:
            result = folder(); result.update(change)
            with self.assertRaises(ValueError):
                images.private_folder('folder-one', 'fake', {'api_json': lambda *args: result})
        images.private_folder('folder-one', 'fake', {'api_json': lambda *args: folder()})

    def test_private_outputs_are_owner_only_and_never_overwritten(self):
        path = self.root / 'record.json'
        old_umask = os.umask(0)
        try:
            images.write_private(path, b'original')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(FileExistsError):
                images.write_private(path, b'replaced')
            images.save_record(path, {'status': 'dispatching'})
            self.assertEqual(json.loads(path.read_text())['status'], 'dispatching')
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        finally:
            os.umask(old_umask)

    def test_record_save_failure_preserves_prior_receipt(self):
        path = self.root / 'record.json'; images.write_private(path, b'prior receipt')
        with patch.object(images.os, 'replace', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                images.save_record(path, {'status': 'dispatching'})
        self.assertEqual(path.read_bytes(), b'prior receipt')
        self.assertEqual(list(self.root.glob('.image-record-*')), [])

    def test_private_outputs_refuse_public_modes_symlinks_and_repositories(self):
        self.root.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'owner-only'):
            images.private_directory(self.root)
        self.root.chmod(0o700)
        link = self.root / 'linked'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            images.private_directory(link)
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        with patch.dict(os.environ, {'GIT_DIR': str(self.root / 'missing')}), self.assertRaisesRegex(ValueError, 'Git checkouts'):
            images.private_directory(self.root)

    def test_image_source_reads_are_bounded(self):
        with patch.object(images, 'MAX_BYTES', 10):
            with self.assertRaisesRegex(ValueError, '20 MiB'):
                images.read_source(self.file)

    def test_command_preserves_dispatch_receipt_and_cleans_only_its_import(self):
        source = self.root / 'plan.json'; source.write_text(json.dumps(self.raw))
        with patch.dict(os.environ, {'GOOGLE_DOCS_ALIAS': 'example', 'GOOGLE_DOCS_IMAGE_IMPORT_ENABLED': 'true'}):
            _, fingerprint = self.prepare()
            args = argparse.Namespace(document_id='document-one', plan=str(source), temporary_folder='folder-one', execute=True, expect=fingerprint, record=str(self.root / 'operation.json'))
            writes = []
            def api_json(method, url, token, body=None):
                if method == 'GET': return folder()
                writes.append((method, url, body))
                record = json.loads(Path(args.record).read_text())
                if method == 'POST':
                    self.assertEqual(record['status'], 'dispatching')
                    self.assertEqual(body['writeControl'], {'requiredRevisionId': 'r1'})
                    raise RuntimeError('Uncertain save https://example.googleusercontent.com/signed-secret')
                return {'id': 'import-one', 'trashed': True}
            api = {'access_token': lambda: 'fake', 'document_id_from': lambda a: a.document_id, 'get_document': lambda i,t: document(), 'document_tabs': text_fn, 'api_json': api_json, '_location': location, '_range': range_fn}
            with patch.object(images, 'content_bytes', return_value=self.file.read_bytes()), patch.object(images, 'import_carrier', return_value='import-one') as create, patch('sys.stdout', new=io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, 'Uncertain save') as error:
                    images.command_replace(args, api)
                self.assertNotIn('signed-secret', str(error.exception))
                record = json.loads(Path(args.record).read_text())
                self.assertEqual(record['status'], 'dispatching')
                self.assertTrue(record['temporary_import_trashed'])
                self.assertNotIn('signed-secret', json.dumps(record))
                self.assertEqual(len([x for x in writes if x[0] == 'POST']), 1)
                self.assertEqual([x[1] for x in writes if x[0] == 'PATCH'], [images.DRIVE + '/import-one?supportsAllDrives=true&fields=id,trashed'])
                self.assertEqual(stat.S_IMODE(Path(args.record).stat().st_mode), 0o600)
                backup = Path(args.record + '.images')
                self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
                self.assertEqual((backup / 'image-1.bin').read_bytes(), self.file.read_bytes())
                with self.assertRaisesRegex(ValueError, 'new file'):
                    images.command_replace(args, api)
                self.assertEqual(create.call_count, 1)

    def test_verification_checks_display_size_and_complete_expected_images(self):
        row = {'tab_id': 't', 'index': 1, 'sha256': images.digest(b'image'), 'object_id': 'new', 'size': {'width': {'unit': 'PT', 'magnitude': 400}, 'height': {'unit': 'PT', 'magnitude': 200}}}
        state = {'text_sha256': 'same', 'images': [row]}
        plan = [{'tab_id': 't', 'index': 1, 'width_pt': 400, 'height_pt': 200}]
        images.verify(state, state, plan, [b'image'])
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            images.verify(state, state, plan, [])
        row['size']['height']['magnitude'] = 100
        with self.assertRaisesRegex(RuntimeError, 'display size'):
            images.verify(state, state, plan, [b'image'])


if __name__ == '__main__':
    unittest.main()
