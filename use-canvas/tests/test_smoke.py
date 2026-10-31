import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from canvas_write_fixture import WriteFixture, NOW, reply
from canvas_auth import CanvasError
from canvas_history import History
from canvas_write import run_write
from canvas_smoke import DELETE_PERMISSIONS, Session, Store, prepare, cleanup
import canvas


class SmokeFixture(WriteFixture):
    def __init__(self):
        super().__init__()
        self.data['course']['workflow_state'] = 'unpublished'
        self.permissions.update({k: True for k in DELETE_PERMISSIONS})
        self.deleted = set()

    def send(self, method, url, headers, body=None, token=None):
        from urllib.parse import urlsplit
        path = urlsplit(url).path
        if method == 'GET' and path in self.deleted: return reply({'message': 'missing'}, 404)
        return super().send(method, url, headers, body, token)

    def mutate(self, method, path, fields):
        if method != 'DELETE': return super().mutate(method, path, fields)
        self.deleted.add(path)
        bits = path.split('/')
        if bits[3] == 'files':
            self.data['files'][:] = [r for r in self.data['files'] if r['id'] != bits[4]]
        else:
            tail = bits[5:]
            if tail[0] == 'modules' and len(tail) == 4:
                self.items[tail[1]][:] = [r for r in self.items[tail[1]] if r['id'] != tail[3]]
                for index, row in enumerate(self.items[tail[1]], 1): row['position'] = index
            else:
                key = 'page_id' if tail[0] == 'pages' else 'id'
                self.data[tail[0]][:] = [r for r in self.data[tail[0]] if r[key] != tail[1].removeprefix('page_id:')]
                if tail[0] == 'modules':
                    for index, row in enumerate(self.data['modules'], 1): row['position'] = index
        return {'deleted': True}

    def download(self, client, meta, output, **kwargs):
        value = b'synthetic smoke file'
        Path(output).write_bytes(value)
        return {'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}


class SmokeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture = SmokeFixture()
        self.reader = self.fixture.reader()
        self.history = History(self.root / 'history', now=NOW)
        self.file = self.root / 'file.txt'; self.file.write_bytes(b'synthetic smoke file')
        self.prepared = self.prepare()
        self.sid, self.prefix = self.prepared['session'], self.prepared['prefix']

    def prepare(self):
        args = canvas.parser().parse_args(['smoke-session', 'example', '--course', '123'])
        return prepare(self.reader, args, self.history)[0]

    def args(self, command, *options):
        return canvas.parser().parse_args([command, 'example', '--course', '123', '--smoke-session', self.sid, *options])

    def run_write(self, args):
        return run_write(self.reader, args, self.history, NOW, self.fixture.upload_sender, self.fixture.download)

    def write(self, command, *options):
        args = self.args(command, *options)
        plan, code = self.run_write(args)
        self.assertEqual(code, 0, plan); self.assertEqual(plan['writes_sent'], 0)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = self.run_write(args)
        self.assertEqual(code, 0, result)
        return result

    def cleanup_args(self):
        return canvas.parser().parse_args(['cleanup-smoke', 'example', '--session', self.sid])

    def clean(self):
        args = self.cleanup_args()
        plan, code = cleanup(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(plan['writes_sent'], 0)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0, result)
        return result

    def create_page(self):
        return self.write('create-page', '--title', self.prefix + ' page')['target_ids']['page.id']

    def test_session_preflight_is_read_only_and_requires_delete_permissions(self):
        self.assertEqual(self.prepared['writes_sent'], 0)
        self.assertEqual(self.fixture.writes, [])
        self.fixture.permissions.pop(DELETE_PERMISSIONS[0])
        with self.assertRaises(CanvasError): self.prepare()
        self.fixture.permissions[DELETE_PERMISSIONS[0]] = False
        with self.assertRaises(CanvasError): self.prepare()

    def test_create_edit_and_cleanup_every_supported_kind(self):
        original = copy.deepcopy({k: self.fixture.data[k] for k in ('pages', 'assignments', 'modules', 'files', 'folders', 'assignment_groups')})
        pid = self.create_page()
        self.write('edit-page', '--page', pid, '--title', self.prefix + ' edited page')
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' assignment', '--points', '0', '--submission-type', 'not_graded', '--assignment-group', group)['target_ids']['assignment.id']
        self.write('edit-assignment', '--assignment', aid, '--name', self.prefix + ' edited assignment')
        mid = self.write('create-module', '--name', self.prefix + ' module')['target_ids']['module.id']
        self.write('edit-module', '--module', mid, '--name', self.prefix + ' edited module')
        folder = self.prepared['existing_containers']['folder'][0]['id']
        fid = self.write('upload-file', '--file', str(self.file), '--name', self.prefix + ' file.txt', '--folder', folder, '--verify-content')['target_ids']['file.id']
        for kind, flag, rid in (('Page', '--page', pid), ('Assignment', '--content-id', aid), ('File', '--content-id', fid)):
            iid = self.write('add-module-item', '--module', mid, '--type', kind, flag, rid)['target_ids']['item.id']
            self.write('edit-module-item', '--module', mid, '--item', iid, '--title', 'Verified test item')
        result = self.clean()
        self.assertTrue(result['baseline_restored']); self.assertEqual(len(result['removed']), 7)
        for key, expected in original.items(): self.assertEqual(self.fixture.data[key], expected, key)
        with self.assertRaises(CanvasError): self.run_write(self.args('create-page', '--title', self.prefix + ' closed'))

    def test_preexisting_target_and_unsafe_write_options_refuse(self):
        cases = [('edit-page', '--page', '789', '--title', self.prefix + ' existing'), ('create-page', '--title', self.prefix + ' page', '--published'), ('create-page', '--title', self.prefix + ' page', '--notify'), ('create-page', '--title', 'Wrong prefix'), ('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'not_graded'), ('upload-file', '--file', str(self.file)), ('add-module-item', '--module', '10', '--type', 'SubHeader', '--title', 'Test')]
        for options in cases:
            with self.subTest(options=options), self.assertRaises(CanvasError): self.run_write(self.args(*options))
        self.assertEqual(self.fixture.writes, [])

    def test_tamper_wrong_context_permissions_and_symlinks_refuse(self):
        store = Store(self.history, self.sid)
        original = store.path.read_bytes()
        packet = json.loads(original); packet['data']['owned'].append({'id': '789', 'kind': 'page'})
        store.path.write_text(json.dumps(packet))
        with self.assertRaises(CanvasError): self.clean()
        store.path.write_bytes(original)
        data = store.load(); data['binding']['origin'] = 'https://other.example.net'; store.save(data)
        with self.assertRaises(CanvasError): self.clean()
        store.path.write_bytes(original)
        store.path.chmod(0o644)
        with self.assertRaises(CanvasError): self.clean()
        store.path.chmod(0o600)
        moved = self.root / 'moved'; moved.write_bytes(original)
        store.path.unlink(); store.path.symlink_to(moved)
        with self.assertRaises(CanvasError): self.clean()
        self.assertEqual(self.fixture.writes, [])

    def test_changed_or_published_object_refuses_entire_cleanup(self):
        pid = self.create_page()
        page = next(r for r in self.fixture.data['pages'] if r['page_id'] == pid)
        baseline = copy.deepcopy(page)
        for mutation in ({'body': 'Somebody else edited this'}, {'published': True}, {'front_page': True}):
            page.update(mutation)
            before = len(self.fixture.writes)
            with self.assertRaises(CanvasError): self.clean()
            self.assertEqual(len(self.fixture.writes), before)
            page.clear(); page.update(baseline)
        self.clean()

    def test_foreign_reference_new_object_and_original_order_refuse(self):
        pid = self.create_page()
        original = copy.deepcopy(self.fixture.items['10'])
        page = next(r for r in self.fixture.data['pages'] if r['page_id'] == pid)
        self.fixture.items['10'].append({'id': '999', 'type': 'Page', 'page_url': page['url']})
        with self.assertRaises(CanvasError): self.clean()
        self.fixture.items['10'][:] = original
        self.fixture.data['pages'].append({'page_id': '100000', 'url': 'foreign', 'published': False})
        with self.assertRaises(CanvasError): self.clean()
        self.fixture.data['pages'].pop()
        self.fixture.data['modules'][0]['position'], self.fixture.data['modules'][1]['position'] = 2, 1
        with self.assertRaises(CanvasError): self.clean()
        self.assertFalse(any(m == 'DELETE' for m, _, _ in self.fixture.writes))

    def test_unrecorded_child_prevents_module_deletion(self):
        mid = self.write('create-module', '--name', self.prefix + ' module')['target_ids']['module.id']
        self.fixture.items[mid].append({'id': '987', 'type': 'SubHeader', 'title': 'Foreign'})
        with self.assertRaises(CanvasError): self.clean()
        self.assertFalse(any(m == 'DELETE' for m, _, _ in self.fixture.writes))

    def test_uncertain_create_keeps_pending_and_never_guesses_ownership(self):
        self.fixture.fail_after.add('/api/v1/courses/123/pages')
        args = self.args('create-page', '--title', self.prefix + ' page')
        plan, _ = self.run_write(args); args.execute = True; args.expect = plan['preview_hash']
        result, code = self.run_write(args)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 1)
        data = Store(self.history, self.sid).load()
        self.assertIsNotNone(data['pending']); self.assertEqual(data['owned'], [])
        with self.assertRaises(CanvasError): self.clean()
        self.assertEqual(len(self.fixture.writes), 1)

    def test_readback_failure_records_known_id_but_blocks_cleanup(self):
        self.fixture.sanitize = True
        self.fixture.failures['/api/v1/courses/123/pages/page_id:10001'] = (503, {})
        args = self.args('create-page', '--title', self.prefix + ' page')
        plan, _ = self.run_write(args); args.execute = True; args.expect = plan['preview_hash']
        _, code = self.run_write(args)
        self.assertEqual(code, 3)
        data = Store(self.history, self.sid).load()
        self.assertEqual(data['owned'][0]['id'], '10001'); self.assertIsNone(data['owned'][0]['snapshot'])
        with self.assertRaises(CanvasError): self.clean()

    def test_known_first_refusal_leaves_session_usable(self):
        self.fixture.fail_before['/api/v1/courses/123/pages'] = 403
        args = self.args('create-page', '--title', self.prefix + ' page')
        plan, _ = self.run_write(args); args.execute = True; args.expect = plan['preview_hash']
        _, code = self.run_write(args)
        self.assertEqual(code, 1); self.assertIsNone(Store(self.history, self.sid).load()['pending'])
        self.fixture.fail_before.clear(); self.create_page(); self.clean()

    def test_cleanup_hash_and_changed_session_refuse_before_delete(self):
        self.create_page(); args = self.cleanup_args(); args.execute = True
        with self.assertRaises(CanvasError): cleanup(self.reader, args, self.history)
        args.execute = False; plan, _ = cleanup(self.reader, args, self.history)
        self.write('create-page', '--title', self.prefix + ' second page')
        args.execute = True; args.expect = plan['preview_hash']
        with self.assertRaises(CanvasError): cleanup(self.reader, args, self.history)
        self.assertFalse(any(m == 'DELETE' for m, _, _ in self.fixture.writes))

    def test_uncertain_delete_is_not_retried_and_preserves_pending(self):
        pid = self.create_page(); path = '/api/v1/courses/123/pages/page_id:' + pid
        self.fixture.fail_after.add(path)
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 1)
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])
        with self.assertRaises(CanvasError): self.clean()
        self.assertEqual(sum(m == 'DELETE' for m, _, _ in self.fixture.writes), 1)

    def test_file_bytes_changed_and_non404_absence_refuse(self):
        folder = self.prepared['existing_containers']['folder'][0]['id']
        self.write('upload-file', '--file', str(self.file), '--name', self.prefix + ' file.txt', '--folder', folder, '--verify-content')
        def changed(*args, **kwargs): return {'sha256': '0' * 64}
        with self.assertRaises(CanvasError): cleanup(self.reader, self.cleanup_args(), self.history, changed)
        self.assertFalse(any(m == 'DELETE' for m, _, _ in self.fixture.writes))

    def test_delete_readback_denied_is_not_treated_as_absent(self):
        pid = self.create_page(); path = '/api/v1/courses/123/pages/page_id:' + pid
        sender = self.fixture.send
        def denied(method, url, headers, body=None, token=None):
            if method == 'GET' and path in self.fixture.deleted and path in url:
                return reply({'message': 'denied'}, 403)
            return sender(method, url, headers, body, token)
        self.fixture.send = denied
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertFalse(result['baseline_restored'])
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def test_missing_from_course_collection_and_folder_side_effect_refuse(self):
        pid = self.create_page()
        route = self.fixture.route
        def hidden(path, params):
            rows = route(path, params)
            return [r for r in rows if r['page_id'] != pid] if path.endswith('/pages') else rows
        self.fixture.route = hidden
        with self.assertRaises(CanvasError): self.clean()
        self.fixture.route = route
        self.fixture.data['folders'].append({'id': '100000', 'name': 'Foreign folder'})
        with self.assertRaises(CanvasError): self.clean()
        self.assertFalse(any(m == 'DELETE' for m, _, _ in self.fixture.writes))

    def test_partial_cleanup_preserves_prior_removals_and_never_retries(self):
        pid = self.create_page()
        self.write('create-module', '--name', self.prefix + ' module')
        self.fixture.fail_before['/api/v1/courses/123/pages/page_id:' + pid] = 403
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 2)
        self.assertEqual([r['kind'] for r in result['removed']], ['module'])
        self.assertTrue(Store(self.history, self.sid).load()['owned'][1]['deleted'])
        with self.assertRaises(CanvasError): self.clean()

    def test_multiple_modules_cleanup_preserves_remaining_positions(self):
        for name in ('first', 'second', 'third'):
            self.write('create-module', '--name', self.prefix + ' ' + name)
        self.assertTrue(self.clean()['baseline_restored'])

    def test_change_between_readback_and_receipt_blocks_adoption(self):
        original = Session.snapshot
        def changed(session, row, expected=None):
            if expected is not None:
                self.fixture.data['pages'][-1]['body'] = 'Concurrent change'
            return original(session, row, expected)
        from unittest.mock import patch
        args = self.args('create-page', '--title', self.prefix + ' page')
        plan, _ = self.run_write(args); args.execute = True; args.expect = plan['preview_hash']
        with patch.object(Session, 'snapshot', changed):
            _, code = self.run_write(args)
        self.assertEqual(code, 3)
        with self.assertRaises(CanvasError): self.clean()


if __name__ == '__main__': unittest.main()
