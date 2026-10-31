import copy
import dataclasses
import datetime as dt
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from test_smoke import SmokeFixture
from canvas_write_fixture import NOW, reply
from canvas_fixture import ORIGIN, TOKEN
import canvas_auth as auth
import canvas
import canvas_sandbox as sandbox
from canvas_history import History
from canvas_read import Reader
from canvas_smoke import Store
from canvas_write import run_write

TEST_ORIGIN = 'https://example.test.instructure.com'


class SandboxFixture(SmokeFixture):
    def __init__(self):
        super().__init__()
        self.permissions['use_student_view'] = True
        self.sections = [{'id': '88', 'course_id': '123'}]
        self.learners = []; self.enrollments = []; self.personal_files = []
        self.topic_entries = {}; self.submissions = {}; self.submission_sequence = 30000; self.file_users = {}
        self.actor = None; self.learner_creation_requests = 0
        self.fail_learner_response = False
        self.fail_actor_identity = False
        self.fixture_origin = TEST_ORIGIN

    def client(self):
        with patch.dict(os.environ, {'CANVAS_TOKEN_EXAMPLE': TOKEN}):
            account = auth.Account('example', self.fixture_origin, '1001', 'CANVAS_TOKEN_EXAMPLE', None, ('123',))
            return auth.Client(account, transport=self, sleep=lambda _: None)

    def send(self, method, url, headers, body=None, token=None):
        self.actor = parse_qs(urlsplit(url).query).get('as_user_id', [None])[0]
        if self.actor and urlsplit(url).path == '/api/v1/users/self/profile': return reply({'message': 'Student View has no profile'}, 403)
        if self.actor and self.fail_actor_identity and urlsplit(url).path == '/api/v1/users/self': return reply({'message': 'Synthetic identity failure'}, 503)
        response = super().send(method, url.replace(self.fixture_origin, ORIGIN), headers, body, token)
        if response.header('link'):
            response.headers['link'] = response.header('link').replace(ORIGIN, self.fixture_origin)
        return response

    def route(self, path, params):
        base = '/api/v1/courses/123'
        if path == base + '/discussion_topics':
            return self.data['announcements'] if 'only_announcements' in params else self.data['discussions']
        if path == '/api/v1/users/self' and self.actor:
            return {'id': self.actor, 'name': 'Test Student'}
        if path == '/api/v1/users/self/files' and self.actor:
            return [r for r in self.data['files'] if r['id'] in self.personal_files and self.file_users.get(r['id'], self.actor) == self.actor]
        if path.startswith('/api/v1/users/') and path.rsplit('/', 1)[1].isdigit():
            return next(r for r in self.learners if r['id'] == path.rsplit('/', 1)[1])
        if path == base + '/users':
            assert params['enrollment_type[]'] == ['student_view']
            return [r for r in self.learners if any(e['user_id'] == r['id'] and e['enrollment_state'] == 'active' for e in self.enrollments)]
        if path == base + '/sections': return self.sections
        if path == base + '/enrollments':
            assert params['type[]'] == ['StudentViewEnrollment']
            return [r for r in self.enrollments if r['user_id'] == params['user_id'][0] and r['enrollment_state'] == 'active']
        if path == base + '/student_view_student':
            self.learner_creation_requests += 1
            user = {'id': '2001', 'name': 'Test Student'}; self.learners.append(user)
            self.enrollments.append({'id': self.new_id(), 'user_id': '2001', 'type': 'StudentViewEnrollment', 'course_id': '123', 'course_section_id': '88', 'enrollment_state': 'active'})
            if self.fail_learner_response: raise auth.CanvasError('network_error', 'Synthetic lost learner response')
            return user
        if '/assignments/' in path and path.endswith('/submissions'):
            aid = path.split('/')[6]
            return [s for (assignment, _), s in self.submissions.items() if assignment == aid]
        if '/assignments/' in path and '/submissions/' in path:
            bits = path.split('/'); aid = bits[6]; uid = self.actor if bits[8] == 'self' else bits[8]
            key = (aid, uid)
            if key not in self.submissions:
                self.submission_sequence += 1
                self.submissions[key] = {'id': str(self.submission_sequence), 'user_id': uid, 'assignment_id': aid, 'attempt': 0, 'submission_comments': [], 'score': None, 'grade': None, 'grader_id': None}
            return self.submissions[key]
        if '/discussion_topics/' in path:
            bits = path.split('/'); tid = bits[6]
            if path.endswith('/view'): return {'view': self.topic_entries.get(tid, []), 'new_entries': []}
            if path.endswith('/entry_list'): return [r for r in self.topic_entries.get(tid, []) if r['id'] in params['ids[]']]
        return super().route(path, params)

    def mutate(self, method, path, fields):
        if method == 'DELETE':
            bits = path.split('/')
            if '/enrollments/' in path:
                row = next(r for r in self.enrollments if r['id'] == bits[-1]); row['enrollment_state'] = 'deleted'; return row
            if '/comments/' in path:
                sub = next(s for s in self.submissions.values() if any(c['id'] == bits[-1] for c in s['submission_comments']))
                sub['submission_comments'][:] = [c for c in sub['submission_comments'] if c['id'] != bits[-1]]
                return {'id': bits[-1]}
            if '/entries/' in path:
                tid = bits[6]; entry = next(e for e in self.topic_entries[tid] if e['id'] == bits[-1]); entry['deleted'] = True
                topic = next(t for t in self.data['discussions'] if t['id'] == tid); topic['discussion_subentry_count'] -= 1
                return entry
            if '/discussion_topics/' in path:
                self.deleted.add(path)
                for key in ('announcements', 'discussions'): self.data[key][:] = [r for r in self.data[key] if r['id'] != bits[-1]]
                return {'id': bits[-1]}
            if path.startswith('/api/v1/files/'):
                self.personal_files[:] = [r for r in self.personal_files if r != bits[-1]]
            return super().mutate(method, path, fields)
        if '/assignments/' in path and '/submissions' in path:
            if path.endswith('/files'): return super().mutate(method, path, fields)
            bits = path.split('/'); aid = bits[6]; uid = self.actor
            sub = self.route('/api/v1/courses/123/assignments/' + aid + '/submissions/' + uid, {})
            if method == 'POST' and path.endswith('/submissions'):
                sub.update(fields['submission']); sub['attempt'] += 1
                sub.update(workflow_state='submitted', submitted_at=dt.datetime.now(dt.timezone.utc).isoformat())
                if 'file_ids' in fields['submission']:
                    sub['attachments'] = [next(f for f in self.data['files'] if f['id'] == fid) for fid in fields['submission']['file_ids']]
                assignment = next(a for a in self.data['assignments'] if a['id'] == aid)
                assignment.update(has_submitted_submissions=True, needs_grading_count=1, unpublishable=False)
            if fields.get('comment'):
                sub['submission_comments'].append({'id': self.new_id(), 'author_id': uid, 'comment': fields['comment']['text_comment']})
            return sub
        if path.endswith('/discussion_topics'):
            topic = {'id': self.new_id(), 'posted_at': None, 'locked': False, 'discussion_subentry_count': 0, **fields}
            self.data['announcements' if fields.get('is_announcement') else 'discussions'].append(topic)
            return topic
        if '/discussion_topics/' in path and ('/entries' in path):
            tid = path.split('/')[6]
            entry = {'id': self.new_id(), 'user_id': self.actor, 'message': fields['message']}
            self.topic_entries.setdefault(tid, []).append(entry)
            next(t for t in self.data['discussions'] if t['id'] == tid)['discussion_subentry_count'] += 1
            return entry
        record = super().mutate(method, path, fields)
        if method == 'POST' and path.endswith('/assignments'):
            record.update(unpublishable=True, has_submitted_submissions=False, needs_grading_count=0)
        return record

    def upload_sender(self, *args):
        response = super().upload_sender(*args)
        fid = str(self.sequence)
        self.personal_files.append(fid); self.file_context[fid] = ('users', 'self')
        self.file_users[fid] = self.actor
        response.headers['location'] = response.header('location').replace(ORIGIN, TEST_ORIGIN)
        return response


class SandboxTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve(); self.fixture = SandboxFixture(); self.reader = self.fixture.reader()
        self.history = History(self.root / 'history', now=NOW)
        args = canvas.parser().parse_args(['test-session', 'example', '--course', '123'])
        self.prepared, _ = sandbox.prepare(self.reader, args, self.history)
        self.sid = self.prepared['session']; self.prefix = self.prepared['prefix']
        self.body = self.root / 'body.html'; self.body.write_text('<p>Synthetic test content.</p>')
        self.comment = self.root / 'comment.txt'; self.comment.write_text('Synthetic test comment.')

    def learner(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']
        result, code = sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(code, 0, result); return result

    def write(self, command, *options):
        args = canvas.parser().parse_args([command, 'example', '--course', '123', '--test-session', self.sid, *options])
        plan, code = run_write(self.reader, args, self.history, NOW, self.fixture.upload_sender, self.fixture.download)
        self.assertEqual(code, 0); args.execute = True; args.expect = plan['preview_hash']
        result, code = run_write(self.reader, args, self.history, NOW, self.fixture.upload_sender, self.fixture.download)
        self.assertEqual(code, 0, result); return result

    def cleanup(self):
        args = canvas.parser().parse_args(['cleanup-test', 'example', '--session', self.sid])
        plan, _ = sandbox.cleanup(self.reader, args, self.history, self.fixture.download)
        args.execute = True; args.expect = plan['preview_hash']
        return sandbox.cleanup(self.reader, args, self.history, self.fixture.download)

    def test_learner_preview_sends_no_mutation_and_creation_runs_once(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(plan['writes_sent'], 0); self.assertEqual(self.fixture.learner_creation_requests, 0)
        result = self.learner(); self.assertTrue(result['learner_identity_verified']); self.assertEqual(self.fixture.learner_creation_requests, 1)
        result, code = self.cleanup(); self.assertEqual(code, 0, result); self.assertTrue(result['baseline_restored'])

    def test_announcements_pages_submissions_comments_replies_cleanup(self):
        self.learner()
        page = self.write('create-page', '--title', self.prefix + ' page', '--body-file', str(self.body))['target_ids']['page.id']
        initial = Store(self.history, self.sid).load()['owned'][-1]['revisions'][0]
        self.body.write_text('<p>Edited test content.</p>')
        self.write('edit-page', '--page', page, '--body-file', str(self.body))
        self.write('revert-page', '--page', page, '--revision', initial)
        notice = self.write('create-announcement', '--title', self.prefix + ' notice', '--body-file', str(self.body), '--delayed-post-at', '2026-12-01T12:00:00Z', '--notify-course')['target_ids']['announcement.id']
        self.write('edit-announcement', '--topic', notice, '--title', self.prefix + ' edited notice')
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        assignment = self.write('create-assignment', '--name', self.prefix + ' assignment', '--points', '0', '--submission-type', 'online_text_entry', '--submission-type', 'online_url', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        self.write('submit-assignment', '--assignment', assignment, '--body-file', str(self.body))
        self.write('submit-assignment', '--assignment', assignment, '--url', 'https://example.com/')
        self.write('comment-submission', '--assignment', assignment, '--comment-file', str(self.comment))
        topic = self.write('create-test-discussion', '--title', self.prefix + ' discussion', '--body-file', str(self.body))['target_ids']['discussion.id']
        entry = self.write('reply-discussion', '--topic', topic, '--body-file', str(self.body))['target_ids']['entry.id']
        self.body.write_text('<p>Nested synthetic reply.</p>')
        self.write('reply-discussion', '--topic', topic, '--entry', entry, '--body-file', str(self.body))
        result, code = self.cleanup(); self.assertEqual(code, 0, result)
        self.assertTrue(result['baseline_restored']); self.assertTrue(Store(self.history, self.sid).load()['closed'])
        self.assertEqual(len([r for r in self.fixture.enrollments if r['enrollment_state'] == 'active']), 0)

    def test_production_beta_wrong_course_and_actor_override_refuse(self):
        for origin in (ORIGIN, 'https://example.beta.instructure.com', 'https://example.test.instructure.com.evil.invalid'):
            reader = self.fixture.reader(); reader.client.origin = origin
            with self.assertRaises(auth.CanvasError): sandbox.Session(reader, self.history, self.sid)
        self.learner(); session = sandbox.Session(self.reader, self.history, self.sid)
        actor = session.learner_reader().client
        for path in ('/api/v1/courses/999', '/api/v1/users/1001', '/api/v1/files/900', '/api/v1/users/self?as_user_id=1001'):
            with self.assertRaises(auth.CanvasError): actor.get(path)

    def test_lost_learner_response_is_never_retried_or_adopted(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        self.fixture.fail_learner_response = True; args.execute = True; args.expect = plan['preview_hash']
        result, code = sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertEqual(self.fixture.learner_creation_requests, 1)
        self.assertIsNone(Store(self.history, self.sid).load()['pending']['created_id'])
        with self.assertRaises(auth.CanvasError): self.cleanup()

    def test_changed_content_or_foreign_reply_blocks_all_deletions(self):
        self.learner()
        topic = self.write('create-test-discussion', '--title', self.prefix + ' discussion', '--body-file', str(self.body))['target_ids']['discussion.id']
        self.fixture.topic_entries[topic] = [{'id': '888', 'user_id': '1002', 'message': 'Unowned reply'}]
        before = len(self.fixture.writes)
        with self.assertRaises(auth.CanvasError): self.cleanup()
        self.assertEqual(len(self.fixture.writes), before)

    def test_new_learner_permission_and_session_fingerprint_are_required(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        self.fixture.permissions['use_student_view'] = False
        with self.assertRaises(auth.CanvasError): sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(self.fixture.learner_creation_requests, 0)
        self.fixture.permissions['use_student_view'] = True
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        args.execute = True; args.expect = '0' * 64
        with self.assertRaises(auth.CanvasError): sandbox.prepare_learner(self.reader, args, self.history)

    def test_file_submission_attachment_is_deleted_and_original_personal_files_preserved(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' upload assignment', '--points', '0', '--submission-type', 'online_upload', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        file = self.root / (self.prefix + ' upload.txt'); file.write_bytes(b'synthetic smoke file')
        self.write('submit-assignment', '--assignment', aid, '--file', str(file))
        self.assertEqual(len(self.fixture.personal_files), 1)
        result, code = self.cleanup(); self.assertEqual(code, 0, result)
        self.assertEqual(self.fixture.personal_files, [])
        self.assertTrue(any(r['kind'] == 'attachment' for r in result['removed']))

    def test_existing_test_learner_and_personal_files_are_never_removed(self):
        self.learner()
        # Prepare a second session after learner creation; the original enrollment belongs to the first session.
        args = canvas.parser().parse_args(['test-session', 'example', '--course', '123'])
        prepared, _ = sandbox.prepare(self.reader, args, self.history)
        self.sid = prepared['session']; self.prefix = prepared['prefix']
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        result, code = sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertTrue(result['existing_enrollment_preserved'])
        result, code = self.cleanup(); self.assertEqual(code, 0, result)
        self.assertEqual(len([r for r in self.fixture.enrollments if r['enrollment_state'] == 'active']), 1)

    def test_interrupted_delete_is_reconciled_readonly_without_a_second_delete(self):
        self.learner()
        pid = self.write('create-page', '--title', self.prefix + ' page', '--body-file', str(self.body))['target_ids']['page.id']
        path = '/api/v1/courses/123/pages/page_id:' + pid
        self.fixture.fail_after.add(path)
        result, code = self.cleanup(); self.assertEqual(code, 3)
        args = canvas.parser().parse_args(['verify-test-cleanup', 'example', '--session', self.sid])
        before = len(self.fixture.writes)
        result, code = sandbox.verify_cleanup(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), before)
        result, code = self.cleanup(); self.assertEqual(code, 0, result)
        self.assertEqual(len([w for w in self.fixture.writes if w[0] == 'DELETE' and w[1] == path]), 1)

    def test_unowned_student_activity_or_grading_prevents_assignment_cleanup(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_text_entry', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        self.write('submit-assignment', '--assignment', aid, '--body-file', str(self.body))
        self.fixture.submissions[(aid, '3001')] = {'id': '99001', 'user_id': '3001', 'attempt': 1}
        with self.assertRaises(auth.CanvasError): self.cleanup()
        del self.fixture.submissions[(aid, '3001')]
        self.fixture.submissions[(aid, '2001')]['score'] = 5
        with self.assertRaises(auth.CanvasError): self.cleanup()

    def test_multiple_new_section_enrollments_are_removed_once_each(self):
        # The fixture's creation endpoint models one section; add the second signed receipt after creation to exercise cleanup sequencing.
        self.learner()
        store = Store(self.history, self.sid); data = store.load()
        second = dict(self.fixture.enrollments[0], id='9999')
        self.fixture.enrollments.append(second)
        data['learner']['enrollments'].append('9999')
        receipt = {'kind': 'enrollment', 'id': '9999', 'path': '/api/v1/courses/123/enrollments/9999', 'user': '2001', 'snapshot': None}
        data['owned'].append(receipt); store.save(data)
        session = sandbox.Session(self.reader, self.history, self.sid); session.data['owned'][-1]['snapshot'] = session.snapshot(receipt); session.store.save(session.data)
        result, code = self.cleanup(); self.assertEqual(code, 0, result)
        self.assertEqual(len(result['removed']), 2)

    def test_profile_denial_is_supported_and_known_setup_reconciliation_sends_no_mutations(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']; self.fixture.fail_actor_identity = True
        result, code = sandbox.prepare_learner(self.reader, args, self.history)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 1)
        self.fixture.fail_actor_identity = False
        args = canvas.parser().parse_args(['verify-test-learner', 'example', '--session', self.sid])
        result, code = sandbox.verify_learner(self.reader, args, self.history)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0)
        self.assertEqual(self.fixture.learner_creation_requests, 1)
        self.assertFalse(any(r['outcome'] == 'uncertain' for r in self.history.rows()))
        result, code = self.cleanup(); self.assertEqual(code, 0, result)

    def test_new_entry_tombstone_overrides_stale_cached_topic_view(self):
        self.learner()
        session = sandbox.Session(self.reader, self.history, self.sid)
        original = self.fixture.route
        def cached(path, params):
            if path.endswith('/view'):
                return {'view': [{'id': '555', 'user_id': '2001', 'message': 'Cached body'}], 'new_entries': [{'id': '555', 'deleted': True}]}
            return original(path, params)
        self.fixture.route = cached
        self.assertEqual(session.entries('333'), {})

    def test_test_session_rejects_legacy_session_production_and_unsigned_revision_targets(self):
        self.learner()
        args = canvas.parser().parse_args(['revert-page', 'example', '--course', '123', '--page', '789', '--revision', '11', '--test-session', self.sid])
        with self.assertRaises(auth.CanvasError): run_write(self.reader, args, self.history, NOW)
        before = len(self.fixture.writes)
        args = canvas.parser().parse_args(['create-announcement', 'example', '--course', '123', '--title', self.prefix + ' notice', '--body-file', str(self.body), '--test-session', self.sid])
        with self.assertRaises(auth.CanvasError): run_write(self.reader, args, self.history, NOW)
        self.assertEqual(len(self.fixture.writes), before)

    def test_learner_verification_refuses_missing_response_or_unrecorded_files(self):
        args = canvas.parser().parse_args(['prepare-test-learner', 'example', '--session', self.sid])
        plan, _ = sandbox.prepare_learner(self.reader, args, self.history)
        args.execute = True; args.expect = plan['preview_hash']; self.fixture.fail_actor_identity = True
        self.assertEqual(sandbox.prepare_learner(self.reader, args, self.history)[1], 3)
        self.fixture.fail_actor_identity = False
        args = canvas.parser().parse_args(['verify-test-learner', 'example', '--session', self.sid])
        self.fixture.personal_files.append('900')
        with self.assertRaises(auth.CanvasError): sandbox.verify_learner(self.reader, args, self.history)
        self.fixture.personal_files.clear()
        store = Store(self.history, self.sid); data = store.load(); data['pending']['created_id'] = None; store.save(data)
        with self.assertRaises(auth.CanvasError): sandbox.verify_learner(self.reader, args, self.history)

    def test_missing_topic_permission_and_non_deletion_enrollment_response_refuse(self):
        self.learner()
        self.fixture.permissions.pop('moderate_forum')
        before = len(self.fixture.writes)
        with self.assertRaises(auth.CanvasError): self.cleanup()
        self.assertEqual(len(self.fixture.writes), before)
        self.fixture.permissions['moderate_forum'] = True
        mutate = self.fixture.mutate
        def deactivate(method, path, fields):
            record = mutate(method, path, fields)
            if method == 'DELETE' and '/enrollments/' in path: record['enrollment_state'] = 'inactive'
            return record
        self.fixture.mutate = deactivate
        result, code = self.cleanup()
        self.assertEqual(code, 3); self.assertFalse(result['baseline_restored'])
        args = canvas.parser().parse_args(['verify-test-cleanup', 'example', '--session', self.sid])
        with self.assertRaises(auth.CanvasError): sandbox.verify_cleanup(self.reader, args, self.history)

    def test_owned_future_announcement_accepts_creation_posted_at_without_relaxing_other_guards(self):
        self.learner()
        mutate = self.fixture.mutate
        def created_posted_at(method, path, fields):
            record = mutate(method, path, fields)
            if method == 'POST' and path.endswith('/discussion_topics') and fields.get('is_announcement'):
                record['posted_at'] = NOW.isoformat()
            return record
        self.fixture.mutate = created_posted_at
        aid = self.write('create-announcement', '--title', self.prefix + ' notice', '--body-file', str(self.body), '--delayed-post-at', '2026-12-01T12:00:00Z', '--notify-course')['target_ids']['announcement.id']
        self.write('edit-announcement', '--topic', aid, '--title', self.prefix + ' edited notice')
        ordinary = canvas.parser().parse_args(['edit-announcement', 'example', '--course', '123', '--topic', aid, '--title', 'Ordinary edit'])
        with self.assertRaises(auth.CanvasError): run_write(self.reader, ordinary, self.history, NOW)
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_owned_submission_inspection_is_readonly_and_omits_content(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_text_entry', '--assignment-group', group, '--published')
        args = canvas.parser().parse_args(['test-status', 'example', '--session', self.sid, '--inspect-owned'])
        before = len(self.fixture.writes)
        result, code = sandbox.status(self.reader, args, self.history)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), before)
        assignment = next(r for r in result['owned'] if r['kind'] == 'assignment')
        self.assertEqual(assignment['learner_submission']['attempt'], 0)
        self.assertNotIn('body', assignment['learner_submission'])
        self.assertNotIn('Synthetic test content', json.dumps(result))

    def test_first_text_receipt_reconciliation_proves_preview_and_parent_without_resubmitting(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_text_entry', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        args = canvas.parser().parse_args(['submit-assignment', 'example', '--course', '123', '--test-session', self.sid, '--assignment', aid, '--body-file', str(self.body)])
        plan, _ = run_write(self.reader, args, self.history, NOW)
        source = self.root / 'preview.json'; source.write_text(json.dumps(plan))
        original = sandbox.Session.begin
        def legacy_begin(session, operation):
            original(session, operation)
            session.data['pending']['parent']['fields'].pop('unpublishable')
            session.store.save(session.data)
        args.execute = True; args.expect = plan['preview_hash']
        with patch.object(sandbox.Session, 'begin', legacy_begin):
            result, code = run_write(self.reader, args, self.history, NOW)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 1)
        verify = canvas.parser().parse_args(['verify-test-submission', 'example', '--session', self.sid, '--preview-file', str(source)])
        writes = len(self.fixture.writes)
        bad = copy.deepcopy(plan); bad['changes'][0]['converted_html'] = '<p>Different content</p>'; source.write_text(json.dumps(bad))
        with self.assertRaises(auth.CanvasError): sandbox.verify_submission(self.reader, verify, self.history)
        source.write_text(json.dumps(plan))
        assignment = next(r for r in self.fixture.data['assignments'] if r['id'] == aid)
        assignment['name'] = 'Changed elsewhere'
        with self.assertRaises(auth.CanvasError): sandbox.verify_submission(self.reader, verify, self.history)
        assignment['name'] = self.prefix + ' task'
        sub = self.fixture.submissions[(aid, '2001')]; sub['attempt'] = 2
        with self.assertRaises(auth.CanvasError): sandbox.verify_submission(self.reader, verify, self.history)
        sub['attempt'] = 1
        result, code = sandbox.verify_submission(self.reader, verify, self.history)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), writes)
        self.assertIsNone(Store(self.history, self.sid).load()['pending'])
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_interrupted_direct_file_confirmation_reconciles_bytes_and_reuses_upload_once(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_text_entry', '--submission-type', 'online_upload', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        self.write('submit-assignment', '--assignment', aid, '--body-file', str(self.body))
        upload = self.root / (self.prefix + ' dummy.txt'); upload.write_bytes(b'synthetic smoke file')
        args = canvas.parser().parse_args(['submit-assignment', 'example', '--course', '123', '--test-session', self.sid, '--assignment', aid, '--file', str(upload)])
        plan, _ = run_write(self.reader, args, self.history, NOW)
        source = self.root / 'upload-preview.json'; source.write_text(json.dumps(plan))
        sender = self.fixture.upload_sender
        def direct_location(*argv):
            response = sender(*argv)
            response.headers['location'] = response.header('location').replace('/create_success', '')
            file = self.fixture.data['files'][-1]
            file.update(created_at=dt.datetime.now(dt.timezone.utc).isoformat(), updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
            return response
        args.execute = True; args.expect = plan['preview_hash']
        with patch.object(sandbox.Session, 'upload_location', lambda *args: None):
            result, code = run_write(self.reader, args, self.history, NOW, direct_location, self.fixture.download)
        self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 2)
        verify = canvas.parser().parse_args(['verify-test-upload', 'example', '--session', self.sid, '--preview-file', str(source)])
        writes = len(self.fixture.writes)
        self.fixture.personal_files.append('99999')
        self.fixture.data['files'].append({'id': '99999'})
        with self.assertRaises(auth.CanvasError): sandbox.verify_upload(self.reader, verify, self.history, self.fixture.download)
        self.fixture.personal_files.remove('99999'); self.fixture.data['files'].pop()
        sub = self.fixture.submissions[(aid, '2001')]; sub['attempt'] += 1
        with self.assertRaises(auth.CanvasError): sandbox.verify_upload(self.reader, verify, self.history, self.fixture.download)
        sub['attempt'] -= 1
        result, code = sandbox.verify_upload(self.reader, verify, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), writes)
        fid = result['target_ids']['attachment.id']
        result = self.write('submit-assignment', '--assignment', aid, '--test-attachment', fid)
        self.assertEqual(result['writes_sent'], 1); self.assertEqual(sub['attempt'], 2)
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_direct_file_confirmation_records_response_identity_before_readback(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_upload', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        upload = self.root / (self.prefix + ' dummy.txt'); upload.write_bytes(b'synthetic smoke file')
        sender = self.fixture.upload_sender
        def direct_location(*argv):
            response = sender(*argv)
            response.headers['location'] = response.header('location').replace('/create_success', '')
            return response
        self.fixture.upload_sender = direct_location
        self.assertEqual(self.write('submit-assignment', '--assignment', aid, '--file', str(upload))['writes_sent'], 4)
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_file_timestamp_touch_preserves_content_guards_and_reconciles_legacy_receipts(self):
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_upload', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        upload = self.root / (self.prefix + ' dummy.txt'); upload.write_bytes(b'synthetic smoke file')
        self.write('submit-assignment', '--assignment', aid, '--file', str(upload))
        session = sandbox.Session(self.reader, self.history, self.sid, self.fixture.download)
        file = next(r for r in session.data['owned'] if r['kind'] == 'attachment')
        subrow = next(r for r in session.data['owned'] if r['kind'] == 'submission')
        metadata = next(r for r in self.fixture.data['files'] if r['id'] == file['id'])
        metadata['updated_at'] = '2026-10-30T12:01:00Z'
        old = sandbox.stable(session.record(file)); old['content'] = file['sha256']; file['snapshot'] = sandbox.digest(old)
        sub = session.record(subrow); subrow['snapshot'] = sandbox.digest(sandbox.stable(sub))
        subrow['metadata_hash'] = sandbox.digest(sandbox.stable({k: v for k, v in sub.items() if k not in {'updated_at', 'submission_comments', 'submission_comments_count'}}))
        session.store.save(session.data)
        metadata['updated_at'] = '2026-10-30T12:02:00Z'
        args = canvas.parser().parse_args(['verify-test-file-touch', 'example', '--session', self.sid, '--before-updated-at', '2026-10-30T12:01:00Z'])
        writes = len(self.fixture.writes)
        metadata['display_name'] += ' changed'
        with self.assertRaises(auth.CanvasError): sandbox.verify_file_touch(self.reader, args, self.history, self.fixture.download)
        metadata['display_name'] = upload.name
        result, code = sandbox.verify_file_touch(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), writes)
        metadata['updated_at'] = '2026-10-30T12:03:00Z'
        self.write('comment-submission', '--assignment', aid, '--comment-file', str(self.comment))
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_reply_delete_accepts_204_and_legacy_lost_ack_requires_exact_tombstone(self):
        self.learner()
        topic = self.write('create-test-discussion', '--title', self.prefix + ' discussion', '--body-file', str(self.body))['target_ids']['discussion.id']
        entry = self.write('reply-discussion', '--topic', topic, '--body-file', str(self.body))['target_ids']['entry.id']
        send = self.fixture.send
        def lost_ack(method, url, headers, body=None, token=None):
            response = send(method, url, headers, body, token)
            if method == 'DELETE' and '/entries/' in url: raise RuntimeError('Synthetic legacy empty response handling failure')
            return response
        self.fixture.send = lost_ack
        result, code = self.cleanup(); self.assertEqual(code, 3); self.assertEqual(result['writes_sent'], 1)
        self.fixture.send = send
        args = canvas.parser().parse_args(['verify-test-cleanup', 'example', '--session', self.sid])
        writes = len(self.fixture.writes)
        self.fixture.topic_entries[topic][0]['deleted'] = False
        with self.assertRaises(auth.CanvasError): sandbox.verify_cleanup(self.reader, args, self.history)
        self.fixture.topic_entries[topic][0]['deleted'] = True
        result, code = sandbox.verify_cleanup(self.reader, args, self.history)
        self.assertEqual(code, 0); self.assertEqual(result['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), writes)
        self.body.write_text('<p>Another synthetic reply.</p>')
        self.write('reply-discussion', '--topic', topic, '--body-file', str(self.body))
        def no_content(method, url, headers, body=None, token=None):
            response = send(method, url, headers, body, token)
            if method == 'DELETE' and '/entries/' in url: return auth.Response(204, {}, b'')
            return response
        self.fixture.send = no_content
        self.assertTrue(self.cleanup()[0]['baseline_restored'])

    def test_submitted_attachment_refusal_is_resolved_as_not_removed_and_blocks_retries(self):
        self.fixture.data['assignments'] = []; self.fixture.data['discussions'] = []
        self.prepared, _ = sandbox.prepare(self.reader, canvas.parser().parse_args(['test-session', 'example', '--course', '123']), self.history)
        self.sid = self.prepared['session']; self.prefix = self.prepared['prefix']
        self.learner()
        group = self.prepared['existing_containers']['assignment_group'][0]['id']
        aid = self.write('create-assignment', '--name', self.prefix + ' task', '--points', '0', '--submission-type', 'online_upload', '--assignment-group', group, '--published')['target_ids']['assignment.id']
        upload = self.root / (self.prefix + ' dummy.txt'); upload.write_bytes(b'synthetic smoke file')
        self.write('submit-assignment', '--assignment', aid, '--file', str(upload))
        send = self.fixture.send
        def protected(method, url, headers, body=None, token=None):
            if method == 'DELETE' and '/api/v1/files/' in url: raise auth.CanvasError('denied', 'Synthetic submitted attachment protection', status=403)
            return send(method, url, headers, body, token)
        self.fixture.send = protected
        result, code = self.cleanup(); self.assertEqual(code, 3); self.assertEqual(result['error_status'], 403)
        source = self.root / 'refusal.json'; source.write_text(json.dumps(result))
        args = canvas.parser().parse_args(['verify-test-cleanup-refusal', 'example', '--session', self.sid, '--execution-file', str(source)])
        writes = len(self.fixture.writes)
        bad = dict(result, error_status=503); source.write_text(json.dumps(bad))
        with self.assertRaises(auth.CanvasError): sandbox.verify_cleanup_refusal(self.reader, args, self.history, self.fixture.download)
        source.write_text(json.dumps(result))
        value, code = sandbox.verify_cleanup_refusal(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertFalse(value['full_cleanup_complete']); self.assertTrue(value['course_content_baseline_restored'])
        self.assertEqual(value['writes_sent'], 0); self.assertEqual(len(self.fixture.writes), writes)
        self.assertIsNone(Store(self.history, self.sid).load()['pending'])
        self.assertFalse(any(r['outcome'] == 'uncertain' for r in self.history.rows()))
        with self.assertRaises(auth.CanvasError): self.cleanup()
        self.assertTrue(self.fixture.personal_files)
        args = canvas.parser().parse_args(['prepare-test-reset', 'example', '--session', self.sid])
        plan, code = sandbox.prepare_reset(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertEqual(plan['writes_sent'], 0)
        args.execute = True; args.expect = plan['preview_hash']
        armed, code = sandbox.prepare_reset(self.reader, args, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertTrue(armed['browser_action_still_required']); self.assertEqual(len(self.fixture.writes), writes)
        inspect = canvas.parser().parse_args(['inspect-test-reset', 'example', '--session', self.sid])
        with self.assertRaises(auth.CanvasError): sandbox.inspect_reset(self.reader, inspect, self.history)
        self.fixture.enrollments[0]['enrollment_state'] = 'deleted'
        self.fixture.learners.append({'id': '2002', 'name': 'Test Student'})
        self.fixture.enrollments.append({'id': '90001', 'user_id': '2002', 'type': 'StudentViewEnrollment', 'course_id': '123', 'course_section_id': '88', 'enrollment_state': 'active'})
        inspected, code = sandbox.inspect_reset(self.reader, inspect, self.history)
        self.assertEqual(code, 0); self.assertEqual(inspected['replacement']['id'], '2002'); self.assertEqual(inspected['writes_sent'], 0)
        self.assertEqual(len(self.fixture.writes), writes)
        verify = canvas.parser().parse_args(['verify-test-reset', 'example', '--session', self.sid])
        with self.assertRaises(auth.CanvasError): sandbox.verify_reset(self.reader, verify, self.history, self.fixture.download)
        file_id = self.fixture.personal_files[0]
        def retired_owner(method, url, headers, body=None, token=None):
            parts = urlsplit(url); actor = parse_qs(parts.query).get('as_user_id', [None])[0]
            if actor == '2001': return reply({'message': 'Retired test identity'}, 401)
            if parts.path == '/api/v1/users/2001': return reply({'message': 'Missing'}, 404)
            if parts.path == '/api/v1/files/' + file_id: return reply({'message': 'Retired owner file'}, 403)
            return protected(method, url, headers, body, token)
        self.fixture.send = retired_owner
        verified, code = sandbox.verify_reset(self.reader, verify, self.history, self.fixture.download)
        self.assertEqual(code, 0); self.assertFalse(verified['content_purge_verified']); self.assertEqual(len(self.fixture.writes), writes)
        final, code = self.cleanup(); self.assertEqual(code, 0, final); self.assertEqual(final['writes_sent'], 1); self.assertTrue(final['baseline_restored'])
        self.assertTrue(Store(self.history, self.sid).load()['closed'])


if __name__ == '__main__': unittest.main()
