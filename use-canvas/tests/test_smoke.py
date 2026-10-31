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
from canvas_write import run_write, Builder
from canvas_smoke import DELETE_PERMISSIONS, Session, Store, prepare, cleanup, verify_cleanup, verify_assignment, verify_file, verify_item_title, inspect_creation
import canvas


class SmokeFixture(WriteFixture):
    def __init__(self):
        super().__init__()
        self.data['course']['workflow_state'] = 'unpublished'
        self.permissions.update({k: True for k in DELETE_PERMISSIONS})
        self.deleted = set()
        self.deleted_objects = {}
        self.item_tombstones = False
        self.deleted_read_status = 404

    def send(self, method, url, headers, body=None, token=None):
        from urllib.parse import urlsplit
        path = urlsplit(url).path
        if method == 'GET' and path in self.deleted:
            if self.item_tombstones and '/items/' in path: return reply(self.deleted_objects[path])
            return reply({'message': 'missing'}, self.deleted_read_status)
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
                self.deleted_objects[path] = copy.deepcopy(next(r for r in self.items[tail[1]] if r['id']==tail[3]))
                self.items[tail[1]][:] = [r for r in self.items[tail[1]] if r['id'] != tail[3]]
                for index, row in enumerate(self.items[tail[1]], 1): row['position'] = index
            else:
                key = 'page_id' if tail[0] == 'pages' else 'id'
                self.data[tail[0]][:] = [r for r in self.data[tail[0]] if r[key] != tail[1].removeprefix('page_id:')]
                if tail[0] == 'modules':
                    for index, row in enumerate(self.data['modules'], 1): row['position'] = index
        return {'page_id': bits[-1].removeprefix('page_id:')} if '/pages/' in path else {'deleted': True}

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
        self.fixture.deleted_read_status = 403
        mutate = self.fixture.mutate
        def listed(method, target, fields):
            value = copy.deepcopy(self.fixture.data['pages'][-1])
            result = mutate(method, target, fields)
            if method == 'DELETE': self.fixture.data['pages'].append(value)
            return result
        self.fixture.mutate = listed
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertFalse(result['baseline_restored'])
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def test_page403_after_exact_delete_ack_requires_inventory_absence(self):
        self.create_page(); self.fixture.deleted_read_status = 403
        result = self.clean()
        self.assertTrue(result['baseline_restored'])
        row = Store(self.history, self.sid).load()['owned'][0]
        self.assertEqual(row['removal_evidence']['object_read_status'], 403)
        self.assertTrue(row['removal_evidence']['complete_inventory_absence'])

    def test_page403_with_unknown_edit_permission_stops_verification(self):
        self.create_page(); self.fixture.deleted_read_status = 403
        mutate = self.fixture.mutate
        def revoked(method, path, fields):
            result = mutate(method, path, fields)
            if method == 'DELETE': self.fixture.permissions.pop('manage_wiki_update')
            return result
        self.fixture.mutate = revoked
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertFalse(result['baseline_restored'])

    def pending_delete(self):
        pid = self.create_page(); self.fixture.deleted_read_status = 403
        self.fixture.fail_after.add('/api/v1/courses/123/pages/page_id:' + pid)
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = cleanup(self.reader, args, self.history)
        self.assertEqual(code, 3)
        return pid

    def verify_pending(self):
        args = canvas.parser().parse_args(['verify-smoke-cleanup', 'example', '--session', self.sid])
        return verify_cleanup(self.reader, args, self.history, self.fixture.download)

    def test_read_only_reconciliation_closes_pending_deleted_page(self):
        pid = self.pending_delete()
        before = len(self.fixture.writes)
        result, code = self.verify_pending()
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(result['verified_absent'], [{'kind': 'page', 'id': pid}])
        self.assertTrue(result['session_closed']); self.assertTrue(result['baseline_restored'])
        self.assertEqual(len(self.fixture.writes), before)
        receipt = Store(self.history, self.sid).load()
        self.assertIsNone(receipt['pending']); self.assertTrue(receipt['closed'])
        self.assertFalse(any(r['outcome'] == 'uncertain' for r in self.history.rows()))

    def test_reconciliation_never_adopts_pending_creation(self):
        self.fixture.fail_after.add('/api/v1/courses/123/pages')
        args = self.args('create-page', '--title', self.prefix + ' page')
        plan, _ = self.run_write(args); args.execute = True; args.expect = plan['preview_hash']
        self.assertEqual(self.run_write(args)[1], 3)
        before = len(self.fixture.writes)
        with self.assertRaises(CanvasError): self.verify_pending()
        self.assertEqual(len(self.fixture.writes), before)

    def test_reconciliation_requires_baseline_and_complete_inventory(self):
        self.pending_delete()
        self.fixture.data['folders'].append({'id': '100000', 'name': 'Foreign folder'})
        with self.assertRaises(CanvasError): self.verify_pending()
        self.fixture.data['folders'].pop()
        self.fixture.failures['/api/v1/courses/123/pages'] = (403, {})
        with self.assertRaises(CanvasError): self.verify_pending()
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def test_reconciliation_rejects_still_readable_target(self):
        self.fixture.fail_before['/api/v1/courses/123/pages/page_id:10001'] = 403
        self.create_page()
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        self.assertEqual(cleanup(self.reader, args, self.history)[1], 3)
        with self.assertRaises(CanvasError): self.verify_pending()
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def test_reconciliation_of_legacy_pending_marker_remains_exact(self):
        self.pending_delete()
        store = Store(self.history, self.sid); data = store.load()
        data['pending'].pop('record_id'); data['pending'].pop('operation_id')
        store.save(data)
        self.assertTrue(self.verify_pending()[0]['session_closed'])

    def test_reconciliation_does_not_claim_full_cleanup_with_live_targets(self):
        self.create_page()
        mid = self.write('create-module', '--name', self.prefix + ' module')['target_ids']['module.id']
        self.fixture.fail_after.add('/api/v1/courses/123/modules/' + mid)
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        self.assertEqual(cleanup(self.reader, args, self.history)[1], 3)
        before = len(self.fixture.writes)
        result, code = self.verify_pending()
        self.assertEqual(code, 0); self.assertEqual(len(self.fixture.writes), before)
        self.assertFalse(result['session_closed']); self.assertFalse(result['baseline_restored'])
        self.assertTrue(result['evidence']['original_inventory_preserved'])
        self.assertIsNone(Store(self.history, self.sid).load()['pending'])

    def test_page403_without_exact_ack_and_token_failure_stay_uncertain(self):
        self.create_page(); self.fixture.deleted_read_status = 403
        mutate = self.fixture.mutate
        def missing_ack(method, path, fields):
            value = mutate(method, path, fields)
            return {'deleted': True} if method == 'DELETE' else value
        self.fixture.mutate = missing_ack
        args = self.cleanup_args(); plan, _ = cleanup(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        self.assertEqual(cleanup(self.reader, args, self.history)[1], 3)
        self.fixture.deleted_read_status = 401
        with self.assertRaises(CanvasError): self.verify_pending()
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def acknowledged_legacy_assignment(self):
        from unittest.mock import patch
        body = self.root/'assignment.md'; body.write_text('Synthetic assignment body.\n')
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        original = Builder.assignments
        def legacy(builder):
            original(builder)
            builder.plan.pop('normalizations', None)
            check = builder.steps[-1]['readback']['fields']
            check.pop('grading_type', None); check['points_possible'] = 0.0
        args = self.args('create-assignment', '--name', self.prefix+' assignment', '--points', '0', '--submission-type', 'not_graded', '--assignment-group', group, '--body-file', str(body))
        with patch.object(Builder, 'assignments', legacy):
            plan, _ = self.run_write(args)
            args.execute = True; args.expect = plan['preview_hash']
            result, code = self.run_write(args)
        self.assertEqual(code, 3); self.assertEqual(result['error_kind'], 'readback_mismatch')
        path = self.root/'original-preview.json'; path.write_text(json.dumps(plan)); path.chmod(0o600)
        self.original_preview = path
        return result['target_ids']['assignment.id']

    def verify_assignment(self):
        args = canvas.parser().parse_args(['verify-smoke-assignment','example','--session',self.sid,'--preview-file',str(self.original_preview)])
        return verify_assignment(self.reader, args, self.history)

    def test_ungraded_point_normalization_is_explicit_and_verified(self):
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        args = self.args('create-assignment', '--name', self.prefix+' assignment', '--points', '0', '--submission-type', 'not_graded', '--assignment-group', group)
        plan, _ = self.run_write(args)
        self.assertEqual(plan['normalizations'][0]['stored'], None)
        self.assertIn('submission_types', plan['steps'][0]['readback']['fields'])
        args.execute = True; args.expect = plan['preview_hash']
        self.assertEqual(self.run_write(args)[1], 0)
        self.assertIsNone(self.fixture.data['assignments'][-1]['points_possible'])
        self.assertEqual(self.fixture.data['assignments'][-1]['grading_type'], 'points')

    def test_acknowledged_assignment_verification_binds_original_hash_without_writes(self):
        aid = self.acknowledged_legacy_assignment()
        before = len(self.fixture.writes)
        result, code = self.verify_assignment()
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(result['target_ids']['assignment.id'], aid)
        self.assertEqual(len(self.fixture.writes), before)
        self.assertIsNone(Store(self.history, self.sid).load()['pending'])
        self.assertIsNotNone(Store(self.history, self.sid).load()['owned'][0]['snapshot'])
        self.assertFalse(any(r['outcome']=='uncertain' for r in self.history.rows()))
        self.assertTrue(self.clean()['baseline_restored'])

    def test_acknowledged_assignment_verification_rejects_forged_body(self):
        self.acknowledged_legacy_assignment()
        plan = json.loads(self.original_preview.read_text())
        html = '<p>Changed outside the approved creation.</p>\n'
        change = next(c for c in plan['changes'] if c['field']=='description')
        change['converted_html'] = html
        facts = {'bytes':len(html.encode()),'sha256':hashlib.sha256(html.encode()).hexdigest()}
        change['after_sha256'] = facts['sha256']
        plan['steps'][0]['fields']['assignment[description]'] = facts
        self.original_preview.write_text(json.dumps(plan))
        self.fixture.data['assignments'][-1]['description'] = html
        with self.assertRaises(CanvasError): self.verify_assignment()
        self.assertIsNotNone(Store(self.history, self.sid).load()['pending'])

    def test_acknowledged_assignment_verification_refuses_lost_id_or_changed_target(self):
        self.acknowledged_legacy_assignment()
        store = Store(self.history, self.sid); original = store.load()
        lost = copy.deepcopy(original); lost['pending']['created_id'] = None; store.save(lost)
        with self.assertRaises(CanvasError): self.verify_assignment()
        store.save(original)
        row = self.fixture.data['assignments'][-1]
        row['updated_at'] = '2026-10-30T12:02:00Z'
        with self.assertRaises(CanvasError): self.verify_assignment()
        row['updated_at'] = row['created_at']; row['published'] = True
        with self.assertRaises(CanvasError): self.verify_assignment()

    def test_graded_null_points_are_not_accepted_as_zero(self):
        args = canvas.parser().parse_args(['create-assignment','example','--course','123','--name','Synthetic graded zero','--points','0','--submission-type','none'])
        plan, _ = self.run_write(args)
        mutate = self.fixture.mutate
        def null_points(method, path, fields):
            result = mutate(method, path, fields)
            result['points_possible'] = None; result['grading_type'] = 'points'
            return result
        self.fixture.mutate = null_points
        args.execute = True; args.expect = plan['preview_hash']
        result, code = self.run_write(args)
        self.assertEqual(code, 3); self.assertEqual(result['error_kind'], 'readback_mismatch')

    def test_ungraded_nonzero_points_refuse_before_writing(self):
        args = canvas.parser().parse_args(['create-assignment','example','--course','123','--name','Contradictory points','--points','5','--submission-type','not_graded'])
        with self.assertRaises(CanvasError): self.run_write(args)
        self.assertEqual(self.fixture.writes, [])

    def rotating_preview_urls(self):
        route = self.fixture.route
        self.preview_counter = 0
        def rotating(path, params):
            result = route(path, params)
            if path.startswith('/api/v1/files/'):
                self.preview_counter += 1
                result = dict(result, canvadoc_session_url='https://preview.example.net/session/'+str(self.preview_counter))
            return result
        self.fixture.route = rotating

    def acknowledged_legacy_file(self):
        from unittest.mock import patch
        import canvas_write
        self.rotating_preview_urls()
        folder = self.prepared['existing_containers']['folder'][0]['id']
        args = self.args('upload-file','--file',str(self.file),'--name',self.prefix+' file.txt','--folder',folder,'--verify-content')
        with patch.object(canvas_write,'VOLATILE',canvas_write.VOLATILE-{'canvadoc_session_url'}):
            plan, _ = self.run_write(args)
            args.execute = True; args.expect = plan['preview_hash']
            result, code = self.run_write(args)
        self.assertEqual(code, 3); self.assertEqual(result['error_kind'], 'smoke_refused')
        path = self.root/'upload-preview.json'; path.write_text(json.dumps(plan)); path.chmod(0o600)
        self.original_preview = path
        return result['target_ids']['file.id']

    def verify_file(self, downloader=None):
        args = canvas.parser().parse_args(['verify-smoke-file','example','--session',self.sid,'--preview-file',str(self.original_preview)])
        return verify_file(self.reader,args,self.history,downloader or self.fixture.download)

    def test_canvadoc_session_rotation_does_not_change_content_guard(self):
        self.rotating_preview_urls()
        folder = self.prepared['existing_containers']['folder'][0]['id']
        self.write('upload-file','--file',str(self.file),'--name',self.prefix+' file.txt','--folder',folder,'--verify-content')
        self.assertGreater(self.preview_counter, 2)
        self.assertTrue(self.clean()['baseline_restored'])

    def test_acknowledged_file_reverification_uses_original_digest_without_upload(self):
        fid = self.acknowledged_legacy_file(); before = len(self.fixture.writes)
        result, code = self.verify_file()
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(result['target_ids']['file.id'], fid)
        self.assertEqual(len(self.fixture.writes), before)
        self.assertIsNone(Store(self.history,self.sid).load()['pending'])
        self.assertTrue(self.clean()['baseline_restored'])

    def test_acknowledged_file_reverification_rejects_changed_content_or_metadata(self):
        fid = self.acknowledged_legacy_file()
        def changed(*args, **kwargs): return {'bytes': len(self.file.read_bytes()), 'sha256': '0'*64}
        with self.assertRaises(CanvasError): self.verify_file(changed)
        record = next(r for r in self.fixture.data['files'] if r['id']==fid)
        record['hidden'] = True
        with self.assertRaises(CanvasError): self.verify_file()
        self.assertIsNotNone(Store(self.history,self.sid).load()['pending'])

    def test_acknowledged_file_reverification_rejects_forged_preview_or_unknown_id(self):
        self.acknowledged_legacy_file()
        plan = json.loads(self.original_preview.read_text())
        plan['changes'][0]['file']['sha256'] = '0'*64
        self.original_preview.write_text(json.dumps(plan))
        with self.assertRaises(CanvasError): self.verify_file()
        store = Store(self.history,self.sid); data = store.load(); data['pending']['created_id'] = None; store.save(data)
        with self.assertRaises(CanvasError): self.verify_file()

    def test_creation_inspection_is_bounded_and_does_not_seal_or_leak_preview_urls(self):
        self.acknowledged_legacy_file(); before = len(self.fixture.writes)
        args = canvas.parser().parse_args(['inspect-smoke-creation','example','--session',self.sid])
        result, code = inspect_creation(self.reader,args,self.history,self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertNotIn('https://preview.example.net/',json.dumps(result))
        self.assertEqual(len(self.fixture.writes), before)
        self.assertIsNotNone(Store(self.history,self.sid).load()['pending'])

    def legacy_item_title_effect(self):
        import datetime
        from unittest.mock import patch
        actual_datetime=datetime.datetime
        clock={'value':actual_datetime(2026,10,30,12,1,tzinfo=datetime.timezone.utc)}
        class Frozen(actual_datetime):
            @classmethod
            def now(cls,tz=None): return clock['value'].astimezone(tz or datetime.timezone.utc)
        original=Builder.module_items
        def legacy(builder):
            original(builder)
            builder.steps[-1]['readback'].pop('linked_title',None)
            builder.plan['effects']=[e for e in builder.plan['effects'] if not isinstance(e,dict) or 'linked_content_rename' not in e]
        self.prior_name=self.prefix+' assignment'
        group=self.prepared['existing_containers']['assignment_group'][0]['id']
        with patch('canvas_write.dt.datetime',Frozen):
            aid=self.write('create-assignment','--name',self.prior_name,'--points','0','--submission-type','not_graded','--assignment-group',group)['target_ids']['assignment.id']
            mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
            iid=self.write('add-module-item','--module',mid,'--type','Assignment','--content-id',aid,'--title','Initial link')['target_ids']['item.id']
            clock['value']=actual_datetime(2026,10,30,12,2,tzinfo=datetime.timezone.utc)
            args=self.args('edit-module-item','--module',mid,'--item',iid,'--title','Verified link')
            with patch.object(Builder,'module_items',legacy):
                plan,_=self.run_write(args);args.execute=True;args.expect=plan['preview_hash']
                self.assertEqual(self.run_write(args)[1],0)
        self.title_preview=self.root/'item-title-preview.json';self.title_preview.write_text(json.dumps(plan));self.title_preview.chmod(0o600)
        return aid,iid

    def verify_item_title(self):
        args=canvas.parser().parse_args(['verify-smoke-item-title','example','--session',self.sid,'--preview-file',str(self.title_preview),'--before-name',self.prior_name])
        return verify_item_title(self.reader,args,self.history,self.fixture.download)

    def test_linked_title_effect_is_previewed_and_tracked_for_cleanup(self):
        group=self.prepared['existing_containers']['assignment_group'][0]['id']
        aid=self.write('create-assignment','--name',self.prefix+' assignment','--points','0','--submission-type','not_graded','--assignment-group',group)['target_ids']['assignment.id']
        mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
        iid=self.write('add-module-item','--module',mid,'--type','Assignment','--content-id',aid,'--title','Initial link')['target_ids']['item.id']
        args=self.args('edit-module-item','--module',mid,'--item',iid,'--title','Verified link')
        plan,_=self.run_write(args)
        self.assertTrue(any(isinstance(e,dict) and e.get('linked_content_rename',{}).get('id')==aid for e in plan['effects']))
        args.execute=True;args.expect=plan['preview_hash'];self.assertEqual(self.run_write(args)[1],0)
        self.assertTrue(self.clean()['baseline_restored'])

    def test_legacy_title_effect_requires_exact_prior_signed_fingerprint(self):
        aid,iid=self.legacy_item_title_effect()
        with self.assertRaises(CanvasError): self.clean()
        before=len(self.fixture.writes)
        result,code=self.verify_item_title()
        self.assertEqual(code,0);self.assertEqual(result['writes_sent'],0)
        self.assertEqual(result['target_ids'],{'item.id':iid,'assignment.id':aid})
        self.assertEqual(len(self.fixture.writes),before)
        self.assertTrue(result['prior_fingerprint_proved'])
        self.assertTrue(self.clean()['baseline_restored'])

    def test_legacy_title_effect_refuses_other_changes_and_wrong_prior_name(self):
        aid,_=self.legacy_item_title_effect()
        original_name=self.prior_name;self.prior_name=self.prefix+' incorrect name'
        with self.assertRaises(CanvasError): self.verify_item_title()
        self.prior_name=original_name
        source=next(r for r in self.fixture.data['assignments'] if r['id']==aid)
        source['description']='Unrelated content change'
        with self.assertRaises(CanvasError): self.verify_item_title()
        with self.assertRaises(CanvasError): self.clean()

    def test_readonly_title_verification_cannot_extend_original_write_window(self):
        import datetime
        aid,_=self.legacy_item_title_effect()
        store=Store(self.history,self.sid);original=store.load()
        self.history.now=datetime.datetime(2026,10,30,12,10,tzinfo=datetime.timezone.utc)
        self.assertEqual(self.verify_item_title()[1],0)
        store.save(original)
        source=next(r for r in self.fixture.data['assignments'] if r['id']==aid)
        source['updated_at']='2026-10-30T12:09:00Z'
        with self.assertRaises(CanvasError): self.verify_item_title()

    def test_readable_deleted_item_requires_complete_active_parent_absence(self):
        self.fixture.item_tombstones=True
        mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
        self.write('add-module-item','--module',mid,'--type','SubHeader','--title','Test heading')
        result=self.clean()
        self.assertTrue(result['baseline_restored'])
        receipt=Store(self.history,self.sid).load()
        item=next(r for r in receipt['owned'] if r['kind']=='item')
        self.assertEqual(item['removal_evidence']['object_read_status'],200)

    def test_readable_item_still_in_parent_refuses(self):
        self.fixture.item_tombstones=True
        mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
        self.write('add-module-item','--module',mid,'--type','SubHeader','--title','Test heading')
        mutate=self.fixture.mutate
        def still_active(method,path,fields):
            result=mutate(method,path,fields)
            if method=='DELETE' and '/items/' in path:
                self.fixture.items[mid].append(self.fixture.deleted_objects[path])
            return result
        self.fixture.mutate=still_active
        args=self.cleanup_args();plan,_=cleanup(self.reader,args,self.history)
        args.execute=True;args.expect=plan['preview_hash']
        result,code=cleanup(self.reader,args,self.history)
        self.assertEqual(code,3);self.assertFalse(result['baseline_restored'])

    def test_readable_item_without_explicit_edit_permission_refuses(self):
        self.fixture.item_tombstones=True
        mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
        self.write('add-module-item','--module',mid,'--type','SubHeader','--title','Test heading')
        mutate=self.fixture.mutate
        def revoked(method,path,fields):
            result=mutate(method,path,fields)
            if method=='DELETE': self.fixture.permissions.pop('manage_course_content_edit')
            return result
        self.fixture.mutate=revoked
        args=self.cleanup_args();plan,_=cleanup(self.reader,args,self.history)
        args.execute=True;args.expect=plan['preview_hash']
        result,code=cleanup(self.reader,args,self.history)
        self.assertEqual(code,3);self.assertEqual(result['writes_sent'],1)
        self.assertIsNotNone(Store(self.history,self.sid).load()['pending'])

    def test_readonly_reconciliation_of_acknowledged_item_tombstone_never_redeletes(self):
        from unittest.mock import patch
        self.fixture.item_tombstones=True
        mid=self.write('create-module','--name',self.prefix+' module')['target_ids']['module.id']
        self.write('add-module-item','--module',mid,'--type','SubHeader','--title','Test heading')
        args=self.cleanup_args();plan,_=cleanup(self.reader,args,self.history)
        args.execute=True;args.expect=plan['preview_hash']
        original=Session.confirm_absent
        def legacy(session,row,allow_page_denial=False,allow_item_tombstone=False):
            return original(session,row,allow_page_denial,False)
        with patch.object(Session,'confirm_absent',legacy):
            self.assertEqual(cleanup(self.reader,args,self.history)[1],3)
        before=len(self.fixture.writes)
        result,code=self.verify_pending()
        self.assertEqual(code,0);self.assertEqual(result['writes_sent'],0)
        self.assertFalse(result['baseline_restored']);self.assertEqual(len(self.fixture.writes),before)
        self.assertTrue(self.clean()['baseline_restored'])

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
