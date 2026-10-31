"""Test-cluster-only learner access and provenance for disposable Canvas smoke fixtures."""
import dataclasses
import copy
import datetime as dt
import hashlib
import json
import re
import tempfile
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import canvas_auth as auth
from canvas_smoke import Store, binding, context, inventory, listing, refuse
from canvas_write import digest, stable

COMMANDS = ('test-session', 'prepare-test-learner', 'verify-test-learner', 'verify-test-submission', 'verify-test-upload', 'verify-test-file-touch', 'verify-test-cleanup-refusal', 'prepare-test-reset', 'inspect-test-reset', 'verify-test-reset', 'cleanup-test', 'verify-test-cleanup', 'test-status')
LEARNER_COMMANDS = {'submit-assignment', 'comment-submission', 'reply-discussion'}


def add_commands(commands, canvas_id):
    for name in COMMANDS:
        p = commands.add_parser(name, help='bounded test-cluster smoke preparation or cleanup')
        p.add_argument('alias'); p.add_argument('--history-dir', type=Path); p.add_argument('--json', action='store_true')
        if name == 'test-session': p.add_argument('--course', type=canvas_id, required=True)
        else: p.add_argument('--session', required=True)
        if name in {'prepare-test-learner', 'cleanup-test', 'prepare-test-reset'}:
            p.add_argument('--execute', action='store_true'); p.add_argument('--expect')
        if name == 'test-status': p.add_argument('--inspect-owned', action='store_true')
        if name in {'verify-test-submission', 'verify-test-upload'}: p.add_argument('--preview-file', type=Path, required=True)
        if name == 'verify-test-file-touch': p.add_argument('--before-updated-at', required=True)
        if name == 'verify-test-cleanup-refusal': p.add_argument('--execution-file', type=Path, required=True)


def test_origin(reader):
    parts = urlsplit(reader.client.origin)
    if parts.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.test\.instructure\.com', parts.netloc):
        refuse('This workflow requires an exact hosted Canvas test-cluster origin')


def test_context(reader, data):
    base, course, permissions = context(reader, data)
    required = ('moderate_forum', 'use_student_view', 'manage_wiki_update')
    extra = reader.object(base + '/permissions', {'permissions[]': list(required)})
    if any(extra.get(key) is not True for key in required): refuse('Test-topic deletion, Student View and page verification permissions must be explicitly true')
    return base, course, {**permissions, **extra}


def fake_enrollments(reader, base, uid, allow_empty=False):
    rows = reader.client.paginate(base + '/enrollments', {'user_id': uid, 'type[]': ['StudentViewEnrollment'], 'state[]': ['active']}).items
    if (not rows and not allow_empty) or any(str(r.get('user_id')) != uid or r.get('type') != 'StudentViewEnrollment' or str(r.get('course_id')) != base.rsplit('/', 1)[1] for r in rows):
        refuse('Learner must have only explicitly returned StudentViewEnrollment records in this course')
    return rows


def access(reader, base):
    users = reader.client.paginate(base + '/users', {'enrollment_type[]': ['student_view'], 'enrollment_state[]': ['active']}).items
    if len(users) > 1: refuse('More than one Test Student was returned')
    enrollments = []
    for user in users: enrollments.extend(fake_enrollments(reader, base, auth.id_string(user.get('id'))))
    sections = listing(reader, base + '/sections')
    if not sections: refuse('An existing course section is required; implicit section creation is excluded')
    return {'learners': [auth.id_string(r['id']) for r in users], 'enrollments': sorted(auth.id_string(r['id']) for r in enrollments), 'sections': sorted(auth.id_string(r['id']) for r in sections)}


def extra_inventory(reader, base, owned=()):
    result = access(reader, base)
    for kind, announce in (('announcement', True), ('discussion', False)):
        rows = reader.client.paginate(base + '/discussion_topics', {'only_announcements': True} if announce else None).items
        excluded = {r['id'] for r in owned if r['kind'] == kind}
        ids = {auth.id_string(r['id']) for r in rows}
        for row in owned:
            if row['kind'] == kind and ((row['id'] in ids) == bool(row.get('deleted'))): refuse('Recorded topic presence differs from the active inventory')
        result[kind] = sorted(ids - excluded)
    return result


def prepare(reader, args, history):
    test_origin(reader)
    sid = uuid.uuid4().hex
    data = {'schema_version': 1, 'mode': 'test-cluster', 'session': sid, 'binding': binding(reader, args.course), 'prefix': 'TEMP Canvas test ' + sid[:12], 'owned': [], 'pending': None, 'closed': False, 'learner': None}
    base, course, permissions = test_context(reader, data)
    data['baseline'], choices = inventory(reader, base)
    data['baseline_extra'] = extra_inventory(reader, base)
    with history.locked(): Store(history, sid).save(data, create=True)
    return {'mode': 'prepared', 'session': sid, 'prefix': data['prefix'], 'course': {k: course.get(k) for k in ('id', 'name', 'workflow_state')}, 'delete_permissions': permissions, 'existing_containers': choices, 'learner_access': data['baseline_extra'], 'writes_sent': 0}, 0


class ActorClient(auth.Client):
    """Use only the signed course Test Student; no arbitrary user or course switch is exposed."""
    def __init__(self, teacher, session):
        self.session = session
        learner = session.data.get('learner')
        if not learner: refuse('Test Student access has not been verified')
        self.account = dataclasses.replace(teacher.account, user_id=learner['id'])
        self.origin, self._token, self.transport, self.sleep = teacher.origin, teacher._token, teacher.transport, teacher.sleep
        self.requests_sent = 0

    def check_api_url(self, url):
        auth.Client.check_api_url(self, url)
        parts = urlsplit(url); path = parts.path; base = self.session.base
        owned = self.session.data['owned']
        allowed = path in {'/api/v1/users/self', '/api/v1/users/self/profile', '/api/v1/users/self/files', base, base + '/permissions'}
        for row in owned:
            if row.get('deleted'): continue
            if row['kind'] in {'assignment', 'discussion'} and (path == row['path'] or path.startswith(row['path'] + '/')): allowed = True
            if row['kind'] == 'attachment' and (path == row['path'] or path == row['path'] + '/create_success'): allowed = True
        # The storage response's exact returned file ID is signed before confirmation.
        pending = self.session.data.get('pending') or {}
        if pending.get('upload_id') and path in {'/api/v1/files/' + pending['upload_id'], '/api/v1/files/' + pending['upload_id'] + '/create_success'}: allowed = True
        if not allowed: refuse('Test Student request is outside the signed course and recorded fixtures')
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        actors = [v for k, v in pairs if k == 'as_user_id']
        if actors and actors != [self.account.user_id]: refuse('Test Student identity override differs')
        if not actors: pairs.append(('as_user_id', self.account.user_id))
        return urlunsplit(parts._replace(query=urlencode(pairs)))

    def url_for(self, target, params=None):
        return self.check_api_url(auth.Client.url_for(self, target, params))


class Session:
    def __init__(self, reader, history, sid, downloader=None):
        test_origin(reader)
        self.reader, self.history, self.downloader = reader, history, downloader
        self.store = Store(history, sid); self.data = self.store.load()
        if self.data.get('mode') != 'test-cluster': refuse('A test-cluster session is required')
        self.base, _, _ = test_context(reader, self.data)

    def own(self, kind, rid):
        rows = [r for r in self.data['owned'] if r['kind'] == kind and r['id'] == rid and not r.get('deleted')]
        if len(rows) != 1: refuse('Target is not one exact recorded live test creation')
        return rows[0]

    def scheduled_announcement(self, rid, current, now):
        self.check()
        row = self.own('announcement', rid)
        if digest(stable(current)) != row['snapshot']: refuse('Announcement scheduling metadata differs from its signed receipt')
        delay = current.get('delayed_post_at')
        return bool(delay and dt.datetime.fromisoformat(delay) > now + dt.timedelta(days=1))

    def learner_reader(self):
        from canvas_read import Reader
        current = access(self.reader, self.base)
        learner = self.data.get('learner')
        removed = {r['id'] for r in self.data['owned'] if r['kind'] == 'enrollment' and r.get('deleted')}
        if not learner or current['learners'] != [learner['id']] or current['enrollments'] != sorted(set(learner['enrollments']) - removed): refuse('Test Student enrollment identity changed')
        reader = Reader(ActorClient(self.reader.client, self))
        reader.user = auth.verify_identity(reader.client)
        course = reader.object(self.base)
        if str(course.get('id')) != self.data['binding']['course_id']: refuse('Learner course identity differs')
        # Canvas Student View has no profile. Its verified identity and course supply the required context.
        reader.user_zone = course.get('time_zone') or self.reader.user_zone
        return reader

    def record(self, row):
        kind = row['kind']
        if kind == 'attachment': return self.learner_reader().object(row['path'])
        if kind == 'entry':
            records = self.reader.client.paginate(self.base + '/discussion_topics/' + row['topic'] + '/entry_list', {'ids[]': row['id']}).items
            found = [r for r in records if str(r.get('id')) == row['id'] and not r.get('deleted')]
            if len(found) != 1: refuse('Recorded reply is missing or ambiguous')
            return found[0]
        if kind == 'comment':
            sub = self.reader.object(row['submission_path'], {'include[]': 'submission_comments'})
            found = [r for r in sub.get('submission_comments', []) if str(r.get('id')) == row['id']]
            if len(found) != 1: refuse('Recorded comment is missing or ambiguous')
            return found[0]
        if kind == 'enrollment':
            found = [r for r in fake_enrollments(self.reader, self.base, row['user'], True) if str(r['id']) == row['id']]
            if len(found) != 1: refuse('Recorded Test Student enrollment changed')
            return {k: v for k, v in found[0].items() if k not in {'last_activity_at', 'last_attended_at', 'total_activity_time', 'grades', 'html_url'}}
        return self.reader.object(row['path'], {'include[]': 'submission_comments'} if kind == 'submission' else None)

    def snapshot(self, row, expected=None):
        record = self.record(row)
        if expected is not None and (stable(record) != stable(expected) or row['kind'] == 'page' and record.get('url') != expected.get('url')): refuse('Test object changed between readback and receipt')
        value = self.normalized(record)
        kind = row['kind']
        if kind == 'page':
            if record.get('published') is not False or record.get('front_page'): refuse('Test page must remain unpublished and cannot be a front page')
            value['page_slug'] = record.get('url')
            value['latest_revision'] = auth.id_string(self.reader.object(row['path'] + '/revisions/latest')['revision_id'])
        if kind == 'assignment':
            if record.get('points_possible') != 0 or record.get('published') is not True: refuse('Learner fixture must be published with zero points')
            submissions = self.reader.client.paginate(row['path'] + '/submissions', {'include[]': 'submission_comments'}).items
            learner = (self.data.get('learner') or {}).get('id')
            if any(str(s.get('user_id')) != learner and (s.get('attempt') or s.get('submission_type') or s.get('submission_comments')) for s in submissions): refuse('Another learner interacted with the test assignment')
        if kind in {'submission', 'comment', 'entry'}:
            owner = record.get('author_id') if kind == 'comment' else record.get('user_id')
            if str(owner) != self.data['learner']['id']: refuse('Learner object has the wrong author')
        if kind == 'submission':
            if any(record.get(k) is not None for k in ('score', 'grade', 'grader_id')): refuse('A test submission was graded')
            expected_comments = {r['id'] for r in self.data['owned'] if r['kind'] == 'comment' and r['assignment'] == row['assignment'] and not r.get('deleted')}
            if {str(r['id']) for r in record.get('submission_comments', [])} != expected_comments: refuse('Submission contains an unrecorded comment')
        if kind == 'discussion':
            entries = self.entries(row['id'])
            expected_ids = {r['id'] for r in self.data['owned'] if r['kind'] == 'entry' and r['topic'] == row['id'] and not r.get('deleted')}
            if set(entries) != expected_ids: refuse('Test topic contains an unrecorded reply')
            value['active_entries'] = entries
        if kind == 'attachment':
            value.pop('updated_at', None)
            from canvas_export import download
            with tempfile.TemporaryDirectory() as folder:
                content = (self.downloader or download)(self.learner_reader().client, record, Path(folder).resolve() / 'content')
            if content['sha256'] != row['sha256'] or content['bytes'] != row['bytes']: refuse('Test submission attachment content differs')
            value['content'] = content['sha256']
        return digest(value)

    def normalized(self, record):
        value = stable(record)
        owned = {r['id'] for r in self.data['owned'] if r['kind'] == 'attachment' and not r.get('deleted')}
        for file in value.get('attachments') or []:
            if str(file.get('id')) in owned: file.pop('updated_at', None)
        return value

    def submission_metadata(self, record):
        return digest(self.normalized({k: v for k, v in record.items() if k not in {'updated_at', 'submission_comments', 'submission_comments_count'}}))

    def entries(self, topic):
        view = self.reader.object(self.base + '/discussion_topics/' + topic + '/view', {'include_new_entries': True})
        result = {}
        # The flat new_entries list is authoritative over the eventually consistent cached view, including deletions.
        for source in (view.get('view') or [], view.get('new_entries') or []):
            todo = list(source)
            while todo:
                row = todo.pop(); todo.extend(row.get('replies') or [])
                result[auth.id_string(row['id'])] = stable({k: v for k, v in row.items() if k != 'replies'})
        return {key: row for key, row in result.items() if not row.get('deleted')}

    def check(self):
        if self.data['pending'] or self.data['closed']: refuse('Test session is pending or closed')
        self.check_state()

    def check_state(self):
        test_context(self.reader, self.data)
        # Personal submission attachments are checked separately from course file inventory.
        current, _ = inventory(self.reader, self.base, self.data['owned'])
        if current != self.data['baseline']: refuse('Original course inventory or order changed')
        extra = extra_inventory(self.reader, self.base, self.data['owned'])
        learner = self.data.get('learner')
        enrollments = [r for r in self.data['owned'] if r['kind'] == 'enrollment']
        for row in enrollments:
            if ((row['id'] in extra['enrollments']) == bool(row.get('deleted'))): refuse('Test enrollment presence differs')
        extra['enrollments'] = sorted(set(extra['enrollments']) - {r['id'] for r in enrollments})
        if learner and not learner['preexisting']: extra['learners'] = [r for r in extra['learners'] if r != learner['id']]
        if extra != self.data['baseline_extra']: refuse('Original topics, sections or Test Student enrollments changed')
        for row in self.data['owned']:
            if not row.get('deleted') and (not row.get('snapshot') or self.snapshot(row) != row['snapshot']): refuse('Recorded test ' + row['kind'] + ' changed or lacks a verified receipt')
        removed_enrollments = {r['id'] for r in enrollments if r.get('deleted')}
        enrollment_cleanup_started = bool(learner and set(learner['enrollments']) & removed_enrollments)
        if enrollment_cleanup_started and (not learner.get('files_restored') or any(r['kind'] == 'attachment' and not r.get('deleted') for r in self.data['owned'])): refuse('Learner enrollment cleanup requires verified file restoration first')
        if learner and not enrollment_cleanup_started:
            files = self.learner_reader().client.paginate('/api/v1/users/self/files').items
            owned = [r for r in self.data['owned'] if r['kind'] == 'attachment']
            ids = {auth.id_string(r['id']) for r in files}
            if any((r['id'] in ids) == bool(r.get('deleted')) for r in owned): refuse('Test attachment presence differs from the personal file inventory')
            if sorted(ids - {r['id'] for r in owned}) != learner['baseline_files']: refuse('Original Test Student files changed')

    def attach(self, builder):
        a = builder.args; command = a.command
        if self.data.get('cleanup_blocker'): refuse('Resolve the recorded cleanup blocker before adding more test content')
        self.check()
        if getattr(a, 'course', None) != self.data['binding']['course_id']: refuse('Write course differs from the signed test course')
        if any(getattr(a, k, None) for k in ('notify', 'front_page', 'allow_duplicate', 'replace', 'rename_on_conflict', 'move_to_module', 'group', 'personal')): refuse('Unsafe test-write option')
        mapping = {'create-page': 'page', 'edit-page': 'page', 'revert-page': 'page', 'create-announcement': 'announcement', 'edit-announcement': 'announcement', 'create-test-discussion': 'discussion', 'create-assignment': 'assignment', 'submit-assignment': 'submission', 'comment-submission': 'comment', 'reply-discussion': 'entry'}
        if command not in mapping: refuse('Command is outside the bounded test workflow')
        self.kind, self.creates, self.builder = mapping[command], command.startswith('create-') or command == 'reply-discussion', builder
        if command.startswith('create-'):
            name = getattr(a, 'title', None) or getattr(a, 'name', None)
            if not name or not name.startswith(self.data['prefix'] + ' '): refuse('Test fixture name must use the signed prefix')
        if self.kind == 'page':
            if getattr(a, 'published', None): refuse('Test pages remain unpublished')
            if not self.creates:
                row = self.own('page', a.page)
                if command == 'revert-page' and a.revision not in row['revisions']: refuse('Revert can target only a revision recorded for this test page')
        if self.kind == 'announcement':
            if not self.creates: self.own('announcement', a.topic)
            delay = builder.steps[0]['fields'].get('delayed_post_at')
            if delay is None and not self.creates: delay = self.record(self.own('announcement', a.topic)).get('delayed_post_at')
            if not delay or dt.datetime.fromisoformat(delay) <= builder.now + dt.timedelta(days=1): refuse('Test announcements must remain scheduled more than one day ahead')
        if self.kind == 'assignment':
            if a.points != 0 or a.published is not True or not a.submission_type or set(a.submission_type) - {'online_text_entry', 'online_url', 'online_upload'} or a.assignment_group not in self.data['baseline']['assignment_group'] or any(getattr(a, k, None) for k in ('due_at', 'lock_at', 'unlock_at')): refuse('Use a new zero-point test assignment with explicit existing group, supported submissions and no dates')
        if command in LEARNER_COMMANDS:
            if builder.client.account.user_id != self.data['learner']['id']: refuse('Learner writes must run as the verified Test Student')
            if command == 'reply-discussion':
                self.own('discussion', a.topic)
                if a.entry:
                    parent = self.own('entry', a.entry)
                    if parent['topic'] != a.topic: refuse('Reply parent belongs to another topic')
            else: self.own('assignment', a.assignment)
            for step in builder.steps:
                if 'upload' in step and not step['upload']['name'].startswith(self.data['prefix'] + ' '): refuse('Test submission filenames must use the signed prefix')
        builder.plan.pop('preview_hash', None)
        builder.plan['test_session'] = {'id': self.data['session'], 'state_hash': digest(self.data), 'origin': self.data['binding']['origin'], 'learner_id': (self.data.get('learner') or {}).get('id')}
        builder.plan['effects'].append('Test cluster only; clean only exact recorded creations and preserve original content and existing learner work')
        builder.plan['preview_hash'] = digest({'plan': builder.plan, 'steps': builder.steps})

    def begin(self, operation):
        if self.store.load() != self.data: refuse('Test session changed since preview')
        self.check()
        a = self.builder.args
        pending = {'operation': operation, 'command': a.command, 'created_id': None}
        if a.command in LEARNER_COMMANDS:
            parent = self.own('discussion' if a.command == 'reply-discussion' else 'assignment', a.topic if a.command == 'reply-discussion' else a.assignment)
            before = self.record(parent)
            keys = ('updated_at', 'discussion_subentry_count', 'last_reply_at') if a.command == 'reply-discussion' else ('updated_at', 'has_submitted_submissions', 'needs_grading_count', 'unpublishable')
            pending['parent'] = {'kind': parent['kind'], 'id': parent['id'], 'hash': digest(stable(before)), 'fields': {k: before[k] for k in keys if k in before}, 'absent': [k for k in keys if k not in before]}
            if a.command == 'comment-submission' or getattr(a, 'comment_file', None):
                sub = self.reader.object(parent['path'] + '/submissions/' + self.data['learner']['id'], {'include[]': 'submission_comments'})
                pending['comment_ids'] = [str(r['id']) for r in sub.get('submission_comments', [])]
        self.data['pending'] = pending; self.store.save(self.data)

    def learned(self, rid, path):
        if path.startswith('/api/v1/files/'):
            kind = 'attachment'
            if rid in self.data['learner']['baseline_files']: refuse('Upload returned a pre-existing file')
            facts = [s['upload'] for s in self.builder.steps if 'upload' in s]
            if len(facts) != 1: refuse('The smoke fixture supports one explicitly tracked submission attachment per action')
            row = {'kind': kind, 'id': rid, 'path': '/api/v1/files/' + rid, 'snapshot': None, 'sha256': facts[0]['sha256'], 'bytes': facts[0]['size']}
        elif self.creates:
            kind = self.kind
            if rid in self.data['baseline'].get(kind, []) or rid in self.data['baseline_extra'].get(kind, []): refuse('Creation returned a pre-existing resource')
            row = {'kind': kind, 'id': rid, 'path': path, 'snapshot': None}
            if kind == 'entry': row.update(topic=self.builder.args.topic, path=self.base + '/discussion_topics/' + self.builder.args.topic + '/entries/' + rid)
        else: return
        if any(r['kind'] == kind and r['id'] == rid for r in self.data['owned']): refuse('Response ID was already recorded')
        self.data['owned'].append(row); self.data['pending']['created_id'] = rid; self.store.save(self.data)

    def upload_location(self, location):
        url = self.reader.client.check_api_url(location)
        match = re.fullmatch(r'/api/v1/files/(\d+)(?:/create_success)?', urlsplit(url).path)
        pending = self.data.get('pending') or {}
        if not match or pending.get('command') != 'submit-assignment' or match[1] in self.data['learner']['baseline_files'] or any(r['kind'] == 'attachment' and r['id'] == match[1] for r in self.data['owned']): refuse('Upload confirmation must name one new file from the pending learner upload')
        pending['upload_id'] = match[1]; self.store.save(self.data)

    def refresh_parent(self, proof):
        row = self.own(proof['kind'], proof['id']); current = self.record(row); inverse = stable(current)
        inverse.update(proof['fields'])
        for key in proof['absent']: inverse.pop(key, None)
        if digest(stable(inverse)) != proof['hash']: refuse('Parent changed beyond the documented learner activity metadata')
        row['snapshot'] = self.snapshot(row)

    def complete(self, variables, record):
        a = self.builder.args; command = a.command
        pending = self.data['pending']
        if command == 'submit-assignment' and 'content-type' in record:
            for child in self.data['owned']:
                if child['kind'] == 'attachment' and not child.get('snapshot'): child['snapshot'] = self.snapshot(child, record)
            self.store.save(self.data)
            return
        if command in {'submit-assignment', 'comment-submission'}:
            path = self.base + '/assignments/' + a.assignment + '/submissions/' + self.data['learner']['id']
            sub = self.reader.object(path, {'include[]': 'submission_comments'})
            if any(stable(sub.get(key)) != stable(record.get(key)) for key in ('id', 'user_id', 'assignment_id', 'attempt', 'submission_type', 'body', 'url', 'attachments')): refuse('Submission changed between learner readback and teacher receipt')
            sid = auth.id_string(sub['id'])
            rows = [r for r in self.data['owned'] if r['kind'] == 'submission' and r['id'] == sid]
            row = rows[0] if rows else {'kind': 'submission', 'id': sid, 'path': path, 'assignment': a.assignment}
            if not rows: self.data['owned'].append(row)
            if getattr(a, 'comment_file', None):
                new = [c for c in sub.get('submission_comments', []) if str(c['id']) not in pending['comment_ids']]
                text = a.comment_file.read_text(encoding='utf-8')
                if len(new) != 1 or str(new[0].get('author_id')) != self.data['learner']['id'] or new[0].get('comment') != text: refuse('Exactly one new owned submission comment was not established')
                cid = auth.id_string(new[0]['id'])
                self.data['owned'].append({'kind': 'comment', 'id': cid, 'path': path + '/comments/' + cid, 'submission_path': path, 'assignment': a.assignment, 'snapshot': None})
            for child in self.data['owned']:
                if child['kind'] in {'submission', 'comment'} and child.get('assignment') == a.assignment and not child.get('deleted'):
                    child['snapshot'] = self.snapshot(child)
                    if child['kind'] == 'submission': child['metadata_hash'] = self.submission_metadata(sub)
        elif self.kind in {'page', 'announcement', 'discussion', 'assignment', 'entry'}:
            rid = variables['topic.id'] if self.kind == 'announcement' and not self.creates else variables[self.kind + '.id']
            row = self.own(self.kind, rid)
            expected = record
            if self.kind == 'entry':
                expected = self.record(row)
                if any(stable(expected.get(key)) != stable(record.get(key)) for key in ('id', 'user_id', 'message', 'parent_id')): refuse('Reply changed between learner readback and teacher receipt')
            row['snapshot'] = self.snapshot(row, expected)
            if self.kind == 'page':
                latest = auth.id_string(self.reader.object(row['path'] + '/revisions/latest')['revision_id'])
                row['revisions'] = sorted(set(row.get('revisions', []) + [latest]))
        for row in self.data['owned']:
            if row['kind'] == 'attachment' and not row.get('snapshot'): row['snapshot'] = self.snapshot(row)
        if pending.get('parent'): self.refresh_parent(pending['parent'])
        self.data['pending'] = None; self.store.save(self.data)

    def refused_before_change(self):
        if self.data['pending'].get('created_id'): refuse('A returned identity prevents clearing a pending creation')
        self.data['pending'] = None; self.store.save(self.data)


def prepare_learner(reader, args, history):
    with history.locked():
        session = Session(reader, history, args.session)
        if session.data['pending'] or session.data['closed'] or session.data['owned']: refuse('Prepare learner access before creating test content')
        current = access(reader, session.base)
        if current != {k: session.data['baseline_extra'][k] for k in ('learners', 'enrollments', 'sections')}: refuse('Test Student access changed since session preparation')
        if not current['learners']:
            permissions = reader.object(session.base + '/permissions', {'permissions[]': ['use_student_view']})
            if permissions.get('use_student_view') is not True: refuse('Explicit Student View permission is required to create and remove its enrollments')
            plan = {'command': 'prepare-test-learner', 'session': args.session, 'binding': session.data['binding'], 'state_hash': digest(session.data), 'request': {'method': 'GET', 'path': session.base + '/student_view_student'}, 'effects': ['Create the built-in Test Student in the existing sections; record exact enrollment IDs for later deletion', 'This GET mutates enrollment state, is journaled as a write, and is never retried']}
            plan['preview_hash'] = digest(plan)
            if not args.execute: return {'mode': 'preview', **plan, 'writes_sent': 0}, 0
            if args.expect != plan['preview_hash']: refuse('Learner preparation requires the fresh reviewed preview hash')
            operation = uuid.uuid4().hex
            session.data['pending'] = {'command': 'prepare-test-learner', 'operation': operation, 'created_id': None}; session.store.save(session.data)
            marker = journal(session, 'prepare-test-learner', operation, 'uncertain', plan['preview_hash'])
            try:
                url = reader.client.url_for(session.base + '/student_view_student')
                # This nominal GET creates a user/enrollments; do not use the transport's ordinary read retries.
                response = auth.parse_json(reader.client.transport.send('GET', url, {'Accept': auth.ACCEPT}, token=reader.client._token))
                uid = auth.id_string(response['id'])
                session.data['pending']['created_id'] = uid; session.store.save(session.data)
                after = access(reader, session.base)
                if after['learners'] != [uid] or after['sections'] != current['sections']: refuse('Test Student creation returned unexpected course/section effects')
                records = fake_enrollments(reader, session.base, uid)
                if sorted(str(r['course_section_id']) for r in records) != current['sections']: refuse('Test Student section enrollments differ')
                for row in records:
                    receipt = {'kind': 'enrollment', 'id': auth.id_string(row['id']), 'path': session.base + '/enrollments/' + str(row['id']), 'user': uid, 'snapshot': None}
                    session.data['owned'].append(receipt)
                    receipt['snapshot'] = session.snapshot(receipt)
                session.data['learner'] = {'id': uid, 'enrollments': after['enrollments'], 'preexisting': False}
                session.store.save(session.data)
            except Exception as error:
                return {'mode': 'executed', 'outcome': 'PARTIAL or uncertain', 'writes_sent': 1, 'session': args.session, 'error_kind': getattr(error, 'kind', 'transport_or_history_error')}, 3
        else:
            operation = None
            session.data['learner'] = {'id': current['learners'][0], 'enrollments': current['enrollments'], 'preexisting': True}
        try:
            actor = session.learner_reader()
            files = actor.client.paginate('/api/v1/users/self/files').items
            session.data['learner']['baseline_files'] = sorted(auth.id_string(r['id']) for r in files)
            session.check_state()
            if operation:
                session.data['pending'] = None
                journal(session, 'prepare-test-learner', operation, 'verified', plan['preview_hash'], resolves=marker)
            session.store.save(session.data)
        except Exception as error:
            if operation: return {'mode': 'executed', 'outcome': 'PARTIAL or uncertain', 'writes_sent': 1, 'session': args.session, 'error_kind': getattr(error, 'kind', 'transport_or_history_error')}, 3
            raise
        return {'mode': 'prepared', 'session': args.session, 'learner_id': actor.client.account.user_id, 'existing_enrollment_preserved': session.data['learner']['preexisting'], 'learner_identity_verified': True, 'writes_sent': 1 if operation else 0}, 0


def verify_learner(reader, args, history):
    with history.locked():
        session = Session(reader, history, args.session)
        pending = session.data['pending']; learner = session.data.get('learner')
        if not pending or pending.get('command') != 'prepare-test-learner' or not pending.get('created_id') or not learner or learner['preexisting'] or learner['id'] != pending['created_id'] or session.data['baseline_extra']['learners'] or any(r['kind'] != 'enrollment' for r in session.data['owned']): refuse('Verification requires the signed new Test Student response and exact recorded enrollments, before content writes')
        rows = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r.get('operation_id') == pending['operation'] and r.get('command') == 'prepare-test-learner' and (r.get('outcome') == 'uncertain' or r.get('recorded_outcome') == 'uncertain')]
        if len(rows) != 1 or sorted(r['id'] for r in session.data['owned']) != learner['enrollments']: refuse('Learner preparation lacks one durable marker or its exact enrollment identities')
        actor = session.learner_reader()
        if actor.client.paginate('/api/v1/users/self/files').items: refuse('An unverified new Test Student already has files; do not adopt its work')
        learner['baseline_files'] = []
        session.check_state()
        journal(session, 'verify-test-learner', pending['operation'], 'verified', rows[0]['preview_hash'], resolves=rows[0]['record_id'], target_ids=[learner['id']])
        session.data['pending'] = None; session.store.save(session.data)
        return {'mode': 'verified', 'learner_identity_verified': True, 'learner_id': learner['id'], 'session': args.session, 'writes_sent': 0}, 0


def journal(session, command, operation, outcome, fingerprint, **extra):
    row = {'schema_version': 1, 'record_id': uuid.uuid4().hex, 'operation_id': operation, 'time': dt.datetime.now(dt.timezone.utc).isoformat(), 'account': session.reader.client.account.alias, 'kind': 'write', 'command': command, 'course_ids': [session.data['binding']['course_id']], 'outcome': outcome, 'preview_hash': fingerprint, **extra}
    session.history._append(row)
    return row['record_id']


def verify_submission(reader, args, history):
    """Reconcile only a verified first text POST whose signed parent predates the unpublishable field."""
    from canvas_history import safe_path
    with history.locked():
        session = Session(reader, history, args.session)
        pending = session.data['pending']; learner = session.data.get('learner')
        if not pending or pending.get('command') != 'submit-assignment' or pending.get('created_id') or not learner or session.data['closed']: refuse('A known first text submission receipt must be pending')
        proof = pending.get('parent') or {}
        if proof.get('kind') != 'assignment' or 'unpublishable' in proof.get('fields', {}) or 'unpublishable' in proof.get('absent', []): refuse('Only the legacy assignment parent proof can be reconciled')
        parent = session.own('assignment', proof['id'])
        if parent['snapshot'] != proof['hash'] or any(r['kind'] in {'submission', 'comment', 'attachment'} for r in session.data['owned']): refuse('The first submission must have no earlier learner receipts')
        preview = json.loads(safe_path(args.preview_file).read_text(encoding='utf-8'))
        before = copy.deepcopy(session.data); before['pending'] = None
        binding = session.data['binding']; aid = parent['id']; path = parent['path'] + '/submissions'
        expected_context = {'id': args.session, 'state_hash': digest(before), 'origin': binding['origin'], 'learner_id': learner['id']}
        if preview.get('mode') != 'preview' or preview.get('writes_sent') != 0 or preview.get('command') != 'submit-assignment' or preview.get('account') != {'alias': binding['alias'], 'origin': binding['origin'], 'user_id': learner['id']} or preview.get('context', {}).get('course_id') != binding['course_id'] or preview.get('test_session') != expected_context: refuse('Preview does not match the signed pending session and learner')
        if preview.get('submission', {}).get('attempts_used') != 0 or preview.get('submission', {}).get('submission_type') != 'online_text_entry' or len(preview.get('steps', [])) != 1 or len(preview.get('changes', [])) != 1: refuse('Only one first text submission without comments or uploads can be reconciled')
        change = preview['changes'][0]; body = change.get('converted_html')
        if change.get('field') != 'body' or not isinstance(body, str) or not body: refuse('The reviewed text body is required')
        public = preview['steps'][0]
        fields = {'submission[submission_type]': 'online_text_entry', 'submission[body]': {'bytes': len(body.encode()), 'sha256': hashlib.sha256(body.encode()).hexdigest()}}
        readback = {'path': path + '/self', 'fields': ['submission_type', 'attempt', 'body'], 'resource': 'id', 'comment': 'verify own comment text'}
        if public != {'method': 'POST', 'path': path, 'fields': fields, 'readback': readback}: refuse('Preview is not the single supported text POST')
        step = copy.deepcopy(public); step['fields']['submission[body]'] = body
        step['readback'].update(fields={'submission_type': 'online_text_entry', 'attempt': 1, 'body': body}, comment=None)
        plan = {k: v for k, v in preview.items() if k not in {'mode', 'writes_sent', 'preview_hash'}}
        if digest({'plan': plan, 'steps': [step]}) != preview.get('preview_hash'): refuse('Reviewed preview fingerprint cannot be reconstructed')
        rows = [r for r in history.rows(account=binding['alias'], course=binding['course_id'], kind='write') if r.get('operation_id') == pending['operation'] and r.get('command') == 'submit-assignment']
        markers = [r for r in rows if r.get('recorded_outcome') == 'uncertain' or r.get('outcome') == 'uncertain']
        if len(markers) != 1 or markers[0]['outcome'] != 'verified' or any(r.get('preview_hash') != preview['preview_hash'] for r in rows) or markers[0].get('steps') != [{'step': 1, 'method': 'POST', 'path': path}]: refuse('One durably verified original POST is required; no write is repeated')
        actor = session.learner_reader()
        sub = actor.object(path + '/self', {'include[]': 'submission_comments'})
        teacher = reader.object(path + '/' + learner['id'], {'include[]': 'submission_comments'})
        if stable(sub) != stable(teacher) or str(sub.get('assignment_id')) != aid or str(sub.get('user_id')) != learner['id'] or sub.get('attempt') != 1 or sub.get('submission_type') != 'online_text_entry' or sub.get('workflow_state') != 'submitted' or sub.get('body') != body or sub.get('url') or sub.get('attachments') or sub.get('submission_comments') or any(sub.get(k) is not None for k in ('score', 'grade', 'grader_id')): refuse('The current submission differs from the one reviewed first attempt')
        submitted = dt.datetime.fromisoformat(sub['submitted_at'])
        if not dt.datetime.fromisoformat(markers[0]['time']) - dt.timedelta(seconds=1) <= submitted <= max(dt.datetime.fromisoformat(r['time']) for r in rows) + dt.timedelta(seconds=1): refuse('Submission timestamp is outside the original operation')
        current = session.record(parent); inverse = stable(current)
        if current.get('unpublishable') is not False or current.get('has_submitted_submissions') is not True or proof['fields'].get('has_submitted_submissions') is not False: refuse('Expected first-submission assignment transition is absent')
        inverse.update(proof['fields']); inverse['unpublishable'] = True
        for key in proof['absent']: inverse.pop(key, None)
        if digest(inverse) != proof['hash']: refuse('Assignment changed beyond the exact first-submission metadata transition')
        sid = auth.id_string(sub['id'])
        row = {'kind': 'submission', 'id': sid, 'path': path + '/' + learner['id'], 'assignment': aid}
        session.data['owned'].append(row)
        row['snapshot'] = session.snapshot(row)
        row['metadata_hash'] = session.submission_metadata(teacher)
        parent['snapshot'] = session.snapshot(parent)
        session.check_state()
        journal(session, 'verify-test-submission', pending['operation'], 'verified', preview['preview_hash'], target_ids=[aid, sid])
        session.data['pending'] = None; session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified', 'session': args.session, 'writes_sent': 0, 'target_ids': {'assignment.id': aid, 'submission.id': sid}, 'original_post_verified': True, 'warnings': []}, 0


def verify_upload(reader, args, history, downloader=None):
    """Prove one interrupted upload in a newly created, initially empty Test Student file area."""
    from canvas_history import safe_path
    from canvas_write import file_facts
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending']; learner = session.data.get('learner')
        if not pending or pending.get('command') != 'submit-assignment' or pending.get('created_id') or not learner or learner['preexisting'] or learner['baseline_files'] or session.data['closed'] or any(r['kind'] == 'attachment' for r in session.data['owned']): refuse('Recovery requires the first interrupted upload in a new empty Test Student file area')
        proof = pending.get('parent') or {}
        if proof.get('kind') != 'assignment': refuse('The signed assignment parent is required')
        parent = session.own('assignment', proof['id']); aid = parent['id']; path = parent['path'] + '/submissions'
        if parent['snapshot'] != proof['hash'] or session.snapshot(parent) != proof['hash']: refuse('Assignment changed since upload began')
        preview = json.loads(safe_path(args.preview_file).read_text(encoding='utf-8'))
        before = copy.deepcopy(session.data); before['pending'] = None
        binding = session.data['binding']
        expected_context = {'id': args.session, 'state_hash': digest(before), 'origin': binding['origin'], 'learner_id': learner['id']}
        if preview.get('mode') != 'preview' or preview.get('writes_sent') != 0 or preview.get('command') != 'submit-assignment' or preview.get('account') != {'alias': binding['alias'], 'origin': binding['origin'], 'user_id': learner['id']} or preview.get('context', {}).get('course_id') != binding['course_id'] or preview.get('test_session') != expected_context or len(preview.get('steps', [])) != 2 or len(preview.get('changes', [])) != 1: refuse('Original upload preview does not match the signed pending state')
        change = preview['changes'][0]
        if change.get('field') != 'submission_files' or len(change.get('files', [])) != 1: refuse('Only one reviewed dummy upload can be reconciled')
        facts = change['files'][0]
        if not facts['name'].startswith(session.data['prefix'] + ' ') or file_facts(facts['path'], facts['name']) != facts: refuse('The original local upload bytes changed')
        first, second = copy.deepcopy(preview['steps'])
        expected_first = {'method': 'POST', 'path': path + '/self/files', 'fields': {'name': facts['name'], 'size': facts['size'], 'content_type': facts['content_type'], 'on_duplicate': 'rename'}, 'out': 'attachment0', 'replace': None, 'rename': False, 'verify_content': False, 'readback': {'path': '/api/v1/files/$attachment0.id', 'fields': ['size', 'content-type'], 'resource': 'id'}}
        expected_second = {'method': 'POST', 'path': path, 'fields': {'submission[submission_type]': 'online_upload', 'submission[file_ids][]': ['$attachment0.id']}, 'readback': {'path': path + '/self', 'fields': ['submission_type', 'attempt', 'attachments'], 'resource': 'id', 'comment': 'verify own comment text'}}
        if first != expected_first or second != expected_second: refuse('Preview contains an unsupported upload or submission action')
        first['upload'] = facts; first['readback']['fields'] = {'size': facts['size'], 'content-type': facts['content_type']}
        second['readback'].update(fields={'submission_type': 'online_upload', 'attempt': preview['submission']['attempts_used'] + 1, 'attachments': [{'id': '$attachment0.id', 'display_name': facts['name'], 'size': facts['size']}]}, comment=None)
        plan = {k: v for k, v in preview.items() if k not in {'mode', 'writes_sent', 'preview_hash'}}
        if digest({'plan': plan, 'steps': [first, second]}) != preview.get('preview_hash'): refuse('Original upload fingerprint cannot be reconstructed')
        rows = [r for r in history.rows(account=binding['alias'], course=binding['course_id'], kind='write') if r.get('operation_id') == pending['operation'] and r.get('command') == 'submit-assignment']
        markers = [r for r in rows if r.get('recorded_outcome') == 'uncertain' or r.get('outcome') == 'uncertain']
        if len(markers) != 2 or any(r.get('preview_hash') != preview['preview_hash'] for r in rows): refuse('Exactly registration and storage markers are required; no submission or confirmation may have been sent')
        registration, storage = markers
        if registration['outcome'] != 'verified' or registration['steps'] != [{'step': 1, 'method': 'POST', 'path': path + '/self/files'}] or storage['outcome'] != 'uncertain' or storage['steps'] != [{'step': 2, 'method': 'POST', 'path': 'upload-storage'}]: refuse('Upload protocol history differs from the interrupted storage boundary')
        actor = session.learner_reader(); files = actor.client.paginate('/api/v1/users/self/files').items
        if len(files) != 1: refuse('A complete unique new learner file inventory is required')
        metadata = files[0]; fid = auth.id_string(metadata['id'])
        if pending.get('upload_id') not in {None, fid} or metadata.get('display_name') != facts['name'] or metadata.get('size') != facts['size'] or metadata.get('content-type') != facts['content_type']: refuse('The only new learner file differs from the reviewed upload')
        lower = dt.datetime.fromisoformat(registration['time']) - dt.timedelta(seconds=1)
        upper = dt.datetime.fromisoformat(storage['time']) + dt.timedelta(seconds=auth.TIMEOUT_SECONDS + 1)
        if any(not lower <= dt.datetime.fromisoformat(metadata[k]) <= upper for k in ('created_at', 'updated_at')): refuse('File timestamps are outside the original upload interval')
        current = actor.object(path + '/self', {'include[]': 'submission_comments'})
        sub = session.own('submission', auth.id_string(current['id']))
        if current.get('attempt') != preview['submission']['attempts_used'] or session.snapshot(sub) != sub['snapshot']: refuse('The submission changed after the upload began')
        row = {'kind': 'attachment', 'id': fid, 'path': '/api/v1/files/' + fid, 'snapshot': None, 'sha256': facts['sha256'], 'bytes': facts['size']}
        session.data['owned'].append(row)
        row['snapshot'] = session.snapshot(row, metadata)
        session.check_state()
        journal(session, 'verify-test-upload', pending['operation'], 'verified', preview['preview_hash'], resolves=storage['record_id'], target_ids=[fid])
        session.data['pending'] = None; session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified', 'session': args.session, 'writes_sent': 0, 'target_ids': {'attachment.id': fid}, 'submission_sent': False, 'content_sha256': facts['sha256'], 'warnings': []}, 0


def verify_file_touch(reader, args, history, downloader=None):
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        if session.data['pending'] or session.data['closed']: refuse('File touch reconciliation requires no pending mutation')
        files = [r for r in session.data['owned'] if r['kind'] == 'attachment' and not r.get('deleted')]
        if len(files) != 1: refuse('Exactly one recorded test attachment is required')
        file = files[0]; record = session.record(file)
        prior = dt.datetime.fromisoformat(args.before_updated_at)
        if prior.tzinfo is None or prior >= dt.datetime.fromisoformat(record['updated_at']): refuse('The supplied original file timestamp must precede its current timestamp')
        current = session.snapshot(file)
        inverse = stable(record); inverse['updated_at'] = args.before_updated_at; inverse['content'] = file['sha256']
        if digest(inverse) != file['snapshot']: refuse('File changed beyond the exact timestamp and unchanged downloaded bytes')
        submissions = [r for r in session.data['owned'] if r['kind'] == 'submission' and not r.get('deleted')]
        if len(submissions) != 1: refuse('One recorded submission is required')
        subrow = submissions[0]; sub = session.record(subrow)
        attachments = sub.get('attachments') or []
        if sub.get('submission_type') != 'online_upload' or len(attachments) != 1 or str(attachments[0].get('id')) != file['id']: refuse('The recorded file must be the exact current upload submission')
        inverse = stable(sub); inverse['attachments'][0]['updated_at'] = args.before_updated_at
        old_metadata = digest(stable({k: v for k, v in inverse.items() if k not in {'updated_at', 'submission_comments', 'submission_comments_count'}}))
        if digest(inverse) != subrow['snapshot'] or old_metadata != subrow['metadata_hash']: refuse('Submission changed beyond its exact attachment timestamp')
        file['snapshot'] = current; subrow['snapshot'] = session.snapshot(subrow); subrow['metadata_hash'] = session.submission_metadata(sub)
        session.check_state()
        journal(session, 'verify-test-file-touch', uuid.uuid4().hex, 'verified', digest({'session': args.session, 'file': file['id'], 'before_updated_at': args.before_updated_at}), target_ids=[file['id'], subrow['id']])
        session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified', 'writes_sent': 0, 'target_ids': [file['id'], subrow['id']], 'only_attachment_updated_at_changed': True}, 0


def verify_cleanup_refusal(reader, args, history, downloader=None):
    """Resolve a known refused attachment DELETE while preserving the file and cleanup blocker."""
    from canvas_history import safe_path
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending'] or {}
        if pending.get('command') != 'cleanup-test' or pending.get('kind') != 'attachment' or pending.get('acknowledged') or not pending.get('marker') or session.data['closed']: refuse('One unacknowledged attachment cleanup refusal must be pending')
        result = json.loads(safe_path(args.execution_file).read_text(encoding='utf-8'))
        if result.get('session') != args.session or result.get('mode') != 'executed' or result.get('outcome') != 'PARTIAL or uncertain' or result.get('error_kind') != 'denied' or result.get('error_status') != 403 or not result.get('writes_sent'): refuse('The original native cleanup output must report its explicit HTTP 403 refusal')
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r['record_id'] == pending['marker'] and r.get('command') == 'cleanup-test' and r.get('operation_id') == pending['operation'] and r.get('target_ids') == [pending['id']] and r['outcome'] == 'uncertain']
        if len(markers) != 1: refuse('One exact unresolved attachment deletion marker is required')
        row = session.own('attachment', pending['id'])
        if any(not r.get('deleted') and r['kind'] not in {'attachment', 'enrollment'} for r in session.data['owned']): refuse('Resolve this protection only after other recorded course content is removed')
        session.check_state()
        if session.snapshot(row) != row['snapshot']: refuse('The refused file must still exist with its unchanged bytes and metadata')
        journal(session, 'verify-test-cleanup-refusal', pending['operation'], 'not_landed', markers[0]['preview_hash'], resolves=pending['marker'], target_ids=[row['id']])
        session.data['cleanup_blocker'] = {'kind': 'submitted_attachment_delete_refused', 'id': row['id'], 'refusal_marker': pending['marker'], 'requires': 'Separately reviewed Test Student reset or another supported cleanup route; do not repeat direct file deletion'}
        session.data['pending'] = None; session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified_not_removed', 'writes_sent': 0, 'course_content_baseline_restored': True, 'full_cleanup_complete': False, 'session_closed': False, 'remaining': [{'kind': r['kind'], 'id': r['id']} for r in session.data['owned'] if not r.get('deleted')], 'cleanup_blocker': session.data['cleanup_blocker']}, 0


def prepare_reset(reader, args, history, downloader=None):
    with history.locked():
        session = Session(reader, history, args.session, downloader); session.check()
        learner = session.data.get('learner') or {}
        blocker = session.data.get('cleanup_blocker') or {}
        if learner.get('preexisting') is not False or learner.get('baseline_files') != [] or blocker.get('kind') != 'submitted_attachment_delete_refused' or session.data['baseline']['assignment'] or session.data['baseline_extra']['discussion']: refuse('Reset preparation requires this new, initially empty Test Student and its protected attachment in an initially assignment/discussion-free course')
        remaining = [r for r in session.data['owned'] if not r.get('deleted')]
        if {r['kind'] for r in remaining} != {'enrollment', 'attachment'} or len([r for r in remaining if r['kind'] == 'attachment']) != 1 or any(r['kind'] == 'enrollment' and r['user'] != learner['id'] for r in remaining): refuse('Only the recorded submitted attachment and newly created enrollments may remain')
        file = session.own('attachment', blocker['id'])
        plan = {'command': 'prepare-test-reset', 'session': args.session, 'binding': session.data['binding'], 'state_hash': digest(session.data), 'old_learner_id': learner['id'], 'old_enrollment_ids': learner['enrollments'], 'attachment': {'id': file['id'], 'bytes': file['bytes'], 'sha256': file['sha256']}, 'browser_course_url': reader.client.origin + '/courses/' + session.data['binding']['course_id'], 'effects': ['The separately approved browser Reset Student action replaces only this course Test Student and clears its test submission activity', 'Inspect the replacement identity and old attachment before further cleanup; do not repeat an uncertain reset', 'No browser action or Canvas mutation is sent by this preparation command']}
        plan['preview_hash'] = digest(plan)
        if not args.execute: return {'mode': 'preview', **plan, 'writes_sent': 0}, 0
        if args.expect != plan['preview_hash']: refuse('Reset preparation requires its fresh reviewed preview hash')
        operation = uuid.uuid4().hex
        session.data['pending'] = {'command': 'reset-test-student', 'operation': operation, 'before_state_hash': plan['state_hash'], 'old_learner_id': learner['id'], 'old_enrollment_ids': list(learner['enrollments'])}
        session.store.save(session.data)
        marker = journal(session, 'reset-test-student', operation, 'uncertain', plan['preview_hash'], target_ids=[learner['id']])
        session.data['pending']['marker'] = marker; session.store.save(session.data)
        return {'mode': 'armed', 'session': args.session, 'operation': operation, 'browser_course_url': plan['browser_course_url'], 'preview_hash': plan['preview_hash'], 'writes_sent': 0, 'browser_action_still_required': True}, 0


def inspect_reset(reader, args, history, downloader=None):
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending'] or {}
        if pending.get('command') != 'reset-test-student' or not pending.get('marker'): refuse('An explicitly armed browser reset is required')
        after = access(reader, session.base)
        old = pending['old_learner_id']
        if after['sections'] != session.data['baseline_extra']['sections'] or len(after['learners']) != 1 or after['learners'] == [old] or not after['enrollments'] or set(after['enrollments']) & set(pending['old_enrollment_ids']): refuse('One replacement Test Student and new enrollments in the unchanged sections are required')
        uid = after['learners'][0]
        if fake_enrollments(reader, session.base, old, True): refuse('The original Test Student still has an active enrollment')
        rows = fake_enrollments(reader, session.base, uid)
        if sorted(str(r['course_section_id']) for r in rows) != after['sections']: refuse('Replacement enrollments differ from the existing sections')
        replacement = {'id': uid, 'enrollments': after['enrollments'], 'sections': after['sections']}
        if pending.get('replacement') and pending['replacement'] != replacement: refuse('The already recorded replacement Test Student changed; do not adopt another reset')
        pending['replacement'] = replacement; session.store.save(session.data)
        file = session.own('attachment', session.data['cleanup_blocker']['id'])
        actor = ActorClient(reader.client, session)
        result = {'mode': 'inspection', 'session': args.session, 'old_learner_id': old, 'replacement': pending['replacement'], 'writes_sent': 0, 'old_actor': {}}
        for path in ('/api/v1/users/self', '/api/v1/users/self/files', file['path']):
            try:
                record = actor.get(path)
                if isinstance(record, list): value = {'status': 'accessible', 'file_ids': [auth.id_string(r['id']) for r in record]}
                else: value = {'status': 'accessible', **{k: record[k] for k in ('id', 'workflow_state', 'display_name', 'size', 'content-type', 'created_at', 'updated_at') if k in record}}
                result['old_actor'][path] = value
            except auth.CanvasError as error: result['old_actor'][path] = {'error_kind': error.kind, 'status': error.status}
        result['teacher_reads'] = {}
        for path in (file['path'], '/api/v1/users/' + old):
            try:
                record = reader.object(path)
                result['teacher_reads'][path] = {'status': 'accessible', **{k: record[k] for k in ('id', 'workflow_state', 'display_name', 'size', 'content-type', 'created_at', 'updated_at') if k in record}}
            except auth.CanvasError as error: result['teacher_reads'][path] = {'error_kind': error.kind, 'status': error.status}
        original = session.data['learner']
        try:
            session.data['learner'] = {'id': uid, 'enrollments': after['enrollments'], 'preexisting': False, 'baseline_files': []}
            replacement_actor = session.learner_reader()
            result['replacement_files'] = [auth.id_string(r['id']) for r in replacement_actor.client.paginate('/api/v1/users/self/files').items]
        finally: session.data['learner'] = original
        return result, 0


def verify_reset(reader, args, history, downloader=None):
    inspected, _ = inspect_reset(reader, args, history, downloader)
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending'] or {}; replacement = pending.get('replacement') or {}
        if pending.get('command') != 'reset-test-student' or not pending.get('marker') or replacement != inspected['replacement'] or inspected['replacement_files']: refuse('Reset verification requires the signed replacement and its empty personal file inventory')
        before = copy.deepcopy(session.data); before['pending'] = None
        if digest(before) != pending['before_state_hash']: refuse('The signed pre-reset session changed outside the recorded reset response')
        old = pending['old_learner_id']; uid = replacement['id']
        file = session.own('attachment', session.data['cleanup_blocker']['id'])
        if inspected['old_actor'].get('/api/v1/users/self', {}).get('status') != 401 or inspected['old_actor'].get(file['path'], {}).get('status') != 401 or inspected['teacher_reads'].get('/api/v1/users/' + old, {}).get('status') != 404 or inspected['teacher_reads'].get(file['path'], {}).get('status') not in {403, 404}: refuse('The old Test Student must be removed and unable to authenticate; file denial alone is not removal proof')
        current = access(reader, session.base)
        if current != {'learners': [uid], 'enrollments': replacement['enrollments'], 'sections': replacement['sections']} or fake_enrollments(reader, session.base, old, True): refuse('Replacement identity, sections or original enrollment absence changed')
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r['record_id'] == pending['marker'] and r.get('operation_id') == pending['operation'] and r.get('command') == 'reset-test-student' and r.get('target_ids') == [old] and r['outcome'] == 'uncertain']
        if len(markers) != 1: refuse('One durable marker for the approved browser reset is required')
        for row in session.data['owned']:
            if row['kind'] == 'enrollment' and row['id'] in pending['old_enrollment_ids']:
                row.update(deleted=True, removed_with_test_student_reset=old)
            elif row is file:
                row.update(deleted=True, removed_with_test_student_reset=old, content_purge_verified=False)
            elif not row.get('deleted'): refuse('An unreviewed object remains outside the reset cleanup')
        session.data['reset'] = {'old_learner_id': old, 'old_enrollment_ids': pending['old_enrollment_ids'], 'replacement': replacement, 'retired_attachment_ids': [file['id']], 'content_purge_verified': False, 'operation': pending['operation']}
        session.data['learner'] = {'id': uid, 'enrollments': replacement['enrollments'], 'preexisting': False, 'baseline_files': []}
        actor = session.learner_reader()
        if actor.client.paginate('/api/v1/users/self/files').items: refuse('The replacement Test Student gained unrecorded files')
        records = fake_enrollments(reader, session.base, uid)
        for record in records:
            rid = auth.id_string(record['id'])
            if any(r['kind'] == 'enrollment' and r['id'] == rid for r in session.data['owned']): refuse('Replacement enrollment already has another receipt')
            row = {'kind': 'enrollment', 'id': rid, 'path': session.base + '/enrollments/' + rid, 'user': uid, 'snapshot': None, 'created_by_test_student_reset': pending['operation']}
            session.data['owned'].append(row); row['snapshot'] = session.snapshot(row)
        session.check_state()
        journal(session, 'verify-test-reset', pending['operation'], 'verified', markers[0]['preview_hash'], resolves=pending['marker'], target_ids=[old, uid, *replacement['enrollments']])
        session.data['pending'] = None; session.data.pop('cleanup_blocker'); session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified_reset', 'writes_sent': 0, 'session': args.session, 'old_learner_removed': True, 'old_attachment_retired_with_removed_owner': file['id'], 'content_purge_verified': False, 'replacement_learner_id': uid, 'replacement_file_baseline_restored': True, 'remaining_enrollment_ids': replacement['enrollments'], 'session_closed': False}, 0


def status(reader, args, history):
    session = Session(reader, history, args.session)
    value = {'mode': 'inspection', 'session': args.session, 'pending': session.data['pending'], 'owned': [{'kind': r['kind'], 'id': r['id'], 'verified': bool(r.get('snapshot')), 'deleted': bool(r.get('deleted'))} for r in session.data['owned']], 'writes_sent': 0, 'actor_reads': {}}
    if session.data.get('cleanup_blocker'): value['cleanup_blocker'] = session.data['cleanup_blocker']
    if args.inspect_owned:
        current = extra_inventory(reader, session.base, session.data['owned'])
        current['enrollments'] = sorted(set(current['enrollments']) - {r['id'] for r in session.data['owned'] if r['kind'] == 'enrollment'})
        if session.data.get('learner') and not session.data['learner']['preexisting']:
            current['learners'] = [uid for uid in current['learners'] if uid != session.data['learner']['id']]
        value['inventory_differences'] = {key: {'baseline': session.data['baseline_extra'].get(key), 'current': current.get(key)} for key in set(current) | set(session.data['baseline_extra']) if current.get(key) != session.data['baseline_extra'].get(key)}
        keys = ('id', 'page_id', 'posted_at', 'delayed_post_at', 'unlock_at', 'created_at', 'updated_at', 'published', 'workflow_state', 'is_announcement', 'unpublishable', 'has_submitted_submissions', 'needs_grading_count', 'submission_types', 'points_possible')
        for summary, row in zip(value['owned'], session.data['owned']):
            if row.get('deleted'): continue
            try: record = session.record(row)
            except auth.CanvasError as error:
                summary['inspection_error'] = {'kind': error.kind, 'status': error.status}; continue
            summary['metadata'] = {key: record[key] for key in keys if key in record}
            try: summary['receipt_matches'] = session.snapshot(row) == row.get('snapshot')
            except auth.CanvasError as error: summary['receipt_error'] = {'kind': error.kind, 'status': error.status}
            if row['kind'] == 'assignment' and session.data.get('learner'):
                actor = session.learner_reader()
                path = row['path'] + '/submissions/self'
                before = actor.object(path, {'include[]': 'submission_comments'})
                after = actor.object(path, {'include[]': 'submission_comments'})
                fields = ('id', 'user_id', 'assignment_id', 'attempt', 'submitted_at', 'submission_type', 'workflow_state', 'score', 'grade', 'grader_id')
                summary['learner_submission'] = {key: after.get(key) for key in fields}
                summary['submission_changing_fields'] = sorted(key for key in set(stable(before)) | set(stable(after)) if stable(before).get(key) != stable(after).get(key))
                receipt = next((r for r in session.data['owned'] if r['kind'] == 'submission' and r['assignment'] == row['id']), None)
                if receipt:
                    current = session.record(receipt)
                    summary['teacher_submission_metadata'] = {k: v for k, v in current.items() if k not in {'body', 'url', 'preview_url', 'attachments', 'submission_comments', 'turnitin_data', 'rubric_assessment'}}
                    summary['teacher_submission_attachments'] = [{k: v for k, v in file.items() if k not in {'url', 'preview_url', 'thumbnail_url', 'uuid', 'canvadoc_session_url'}} for file in current.get('attachments', [])]
        if session.data.get('learner'):
            files = session.learner_reader().client.paginate('/api/v1/users/self/files').items
            keys = ('id', 'display_name', 'filename', 'size', 'content-type', 'created_at', 'updated_at', 'folder_id', 'user_id', 'hidden', 'locked', 'lock_at', 'unlock_at')
            value['learner_files'] = [{k: r[k] for k in keys if k in r} for r in files]
    if session.data.get('learner'):
        client = ActorClient(reader.client, session)
        for path in ('/api/v1/users/self', '/api/v1/users/self/profile', '/api/v1/users/self/files', session.base):
            try:
                record = client.get(path, {'include[]': 'permissions'} if path == session.base else None)
                value['actor_reads'][path] = {'status': 'accessible', 'id': record.get('id'), 'enrollments': record.get('enrollments')} if isinstance(record, dict) else {'status': 'accessible', 'count': len(record)}
            except auth.CanvasError as error: value['actor_reads'][path] = {'status': error.status, 'error_kind': error.kind}
    return value, 0


def deletion_parent(session, row):
    if row['kind'] == 'entry':
        parent = session.own('discussion', row['topic']); before = session.record(parent)
        keys = ('updated_at', 'discussion_subentry_count', 'last_reply_at')
        return {'kind': parent['kind'], 'id': parent['id'], 'hash': digest(stable(before)), 'fields': {k: before[k] for k in keys if k in before}, 'absent': [k for k in keys if k not in before]}
    return None


def confirm_absent(session, row, acknowledged=False):
    kind = row['kind']
    if kind == 'entry':
        if not acknowledged:
            records = session.reader.client.paginate(session.base + '/discussion_topics/' + row['topic'] + '/entry_list', {'ids[]': row['id']}).items
            if len(records) != 1 or str(records[0].get('id')) != row['id'] or records[0].get('deleted') is not True: refuse('Unacknowledged reply absence requires its exact readable deletion marker')
        if row['id'] in session.entries(row['topic']): refuse('Deleted reply is still active')
    elif kind == 'comment':
        sub = session.reader.object(row['submission_path'], {'include[]': 'submission_comments'})
        if row['id'] in {str(r['id']) for r in sub.get('submission_comments', [])}: refuse('Deleted comment is still present')
    elif kind == 'enrollment':
        if not acknowledged: refuse('Enrollment absence also requires its recorded deletion acknowledgment')
        permissions = session.reader.object(session.base + '/permissions', {'permissions[]': ['use_student_view']})
        if permissions.get('use_student_view') is not True: refuse('Student View permission changed')
        if row['id'] in access(session.reader, session.base)['enrollments']: refuse('Test Student enrollment is still active')
    else:
        try: session.record(row)
        except auth.CanvasError as error:
            if error.status != 404 and not (kind == 'page' and error.status == 403 and acknowledged): raise
        else: refuse('Deleted test object is still readable')
    row['deleted'] = True
    if kind == 'assignment':
        for child in session.data['owned']:
            if child['kind'] == 'submission' and child['assignment'] == row['id']: child['deleted'] = True
    if kind == 'comment':
        subrow = next(r for r in session.data['owned'] if r['kind'] == 'submission' and r['assignment'] == row['assignment'] and not r.get('deleted'))
        record = session.record(subrow)
        guard = session.submission_metadata(record)
        if guard != subrow['metadata_hash']: refuse('Submission changed beyond the deleted comment')
        subrow['snapshot'] = session.snapshot(subrow)
    if session.data['pending'].get('parent'): session.refresh_parent(session.data['pending']['parent'])
    session.check_state()


def cleanup(reader, args, history, downloader=None):
    with history.locked():
        session = Session(reader, history, args.session, downloader); session.check()
        if session.data.get('cleanup_blocker'): refuse('Submitted attachment deletion was explicitly refused; a separately reviewed cleanup route is required')
        rank = {'comment': 0, 'entry': 1, 'assignment': 2, 'page': 3, 'announcement': 4, 'discussion': 5, 'attachment': 6, 'enrollment': 7}
        targets = sorted([r for r in session.data['owned'] if not r.get('deleted') and r['kind'] != 'submission'], key=lambda r: (rank[r['kind']], -int(r['id'])))
        plan = {'command': 'cleanup-test', 'session': args.session, 'binding': session.data['binding'], 'state_hash': digest(session.data), 'deletions': [{'kind': r['kind'], 'id': r['id'], 'method': 'DELETE', 'path': r['path'], 'fields': {'task': 'delete'} if r['kind'] == 'enrollment' else {}, 'snapshot': r['snapshot']} for r in targets], 'effects': ['Remove exact recorded test creations, their active submission parent records and personal submission attachments', 'Remove only Test Student enrollments created by this session; preserve existing learner files, enrollment and work', 'Canvas soft-deletion/audit history is retained; no independent submission withdrawal or user-record purge is claimed']}
        plan['preview_hash'] = digest(plan)
        if not args.execute: return {'mode': 'preview', **plan, 'writes_sent': 0}, 0
        if args.expect != plan['preview_hash']: refuse('Test cleanup requires the fresh reviewed preview hash')
        operation = uuid.uuid4().hex; sent = 0; removed = []
        try:
            for row in targets:
                session.check()
                if row['kind'] == 'enrollment':
                    permissions = reader.object(session.base + '/permissions', {'permissions[]': ['use_student_view']})
                    if permissions.get('use_student_view') is not True: refuse('Student View permission changed')
                    learner = session.data['learner']
                    files = session.learner_reader().client.paginate('/api/v1/users/self/files').items
                    if sorted(str(r['id']) for r in files) != learner['baseline_files']: refuse('Learner files were not restored before enrollment cleanup')
                    learner['files_restored'] = True
                session.data['pending'] = {'command': 'cleanup-test', 'operation': operation, 'kind': row['kind'], 'id': row['id'], 'acknowledged': False, 'parent': deletion_parent(session, row)}
                session.store.save(session.data)
                marker = journal(session, 'cleanup-test', operation, 'uncertain', plan['preview_hash'], target_ids=[row['id']])
                session.data['pending']['marker'] = marker; session.store.save(session.data)
                client = session.learner_reader().client if row['kind'] == 'attachment' else reader.client
                sent += 1
                raw = client.request('DELETE', row['path'], data={'task': 'delete'} if row['kind'] == 'enrollment' else None)
                response = auth.parse_json(raw)
                if row['kind'] == 'entry' and raw.status == 204 and response is None: response = {}
                if not isinstance(response, dict): refuse('Deletion response lacks its required acknowledgment')
                returned = response.get('page_id') if row['kind'] == 'page' else response.get('id')
                if returned is not None and str(returned) != row['id']: refuse('Deletion acknowledgment has the wrong identity')
                if row['kind'] == 'enrollment' and response.get('enrollment_state') != 'deleted': refuse('Enrollment deletion did not acknowledge the deleted state')
                session.data['pending']['acknowledged'] = True; session.store.save(session.data)
                confirm_absent(session, row, True)
                session.data['pending'] = None; session.store.save(session.data)
                journal(session, 'cleanup-test', operation, 'verified', plan['preview_hash'], resolves=marker, target_ids=[row['id']])
                removed.append({'kind': row['kind'], 'id': row['id']})
            session.check()
            if extra_inventory(reader, session.base) != session.data['baseline_extra']: refuse('Final topic/learner baseline differs')
            if any(not r.get('deleted') for r in session.data['owned']): refuse('A test creation still exists')
            session.data['closed'] = True; session.store.save(session.data)
            return {'mode': 'executed', 'outcome': 'verified', 'session': args.session, 'writes_sent': sent, 'removed': removed, 'baseline_restored': True, 'session_closed': True}, 0
        except Exception as error:
            return {'mode': 'executed', 'outcome': 'PARTIAL or uncertain' if sent else 'refused', 'session': args.session, 'writes_sent': sent, 'removed': removed, 'baseline_restored': False, 'error_kind': getattr(error, 'kind', 'transport_or_history_error'), 'error_status': getattr(error, 'status', None)}, 3 if sent else 1


def verify_cleanup(reader, args, history, downloader=None):
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending']
        if not pending or pending.get('command') != 'cleanup-test' or not pending.get('marker'): refuse('No exact pending test deletion is recorded')
        row = session.own(pending['kind'], pending['id'])
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r.get('record_id') == pending['marker'] and r.get('operation_id') == pending['operation'] and (r.get('outcome') == 'uncertain' or r.get('recorded_outcome') == 'uncertain')]
        if len(markers) != 1: refuse('Pending deletion lacks one durable uncertain marker')
        confirm_absent(session, row, pending.get('acknowledged') is True)
        journal(session, 'verify-test-cleanup', pending['operation'], 'verified', markers[0]['preview_hash'], resolves=pending['marker'], target_ids=[row['id']])
        session.data['pending'] = None; session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified_absent', 'writes_sent': 0, 'kind': row['kind'], 'id': row['id'], 'session_closed': False}, 0
