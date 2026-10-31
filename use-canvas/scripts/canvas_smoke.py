"""Private smoke-test provenance and deletion of unchanged, recorded creations only."""
import hashlib
import hmac
import copy
import datetime as dt
import math
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from canvas_auth import CanvasError, id_string, parse_json, verify_identity
from canvas_history import safe_path
from canvas_write import canonical, digest, stable, matches

DELETE_PERMISSIONS = ('manage_wiki_delete', 'manage_assignments_delete', 'manage_course_content_delete', 'manage_files_delete')
KINDS = {'page': 'pages', 'assignment': 'assignments', 'module': 'modules', 'file': 'files'}
SUPPORTED = {'create-page': 'page', 'edit-page': 'page', 'create-assignment': 'assignment', 'edit-assignment': 'assignment', 'create-module': 'module', 'edit-module': 'module', 'upload-file': 'file', 'add-module-item': 'item', 'edit-module-item': 'item'}


def refuse(message):
    raise CanvasError('smoke_refused', message)


def add_commands(commands, canvas_id):
    for name in ('smoke-session', 'cleanup-smoke', 'verify-smoke-cleanup', 'verify-smoke-assignment', 'verify-smoke-file', 'verify-smoke-item-title', 'inspect-smoke-creation'):
        description = {'smoke-session': 'prepare private test provenance', 'cleanup-smoke': 'preview deletion of unchanged recorded test creations', 'verify-smoke-cleanup': 'verify absence after a pending cleanup without sending mutations', 'verify-smoke-assignment': 'verify an acknowledged ungraded creation against its original preview without mutations', 'verify-smoke-file': 'verify an acknowledged completed upload against its original preview without mutations', 'verify-smoke-item-title': 'verify only a recorded item-title effect with the prior signed content fingerprint', 'inspect-smoke-creation': 'inspect only the signed response ID of a pending creation without mutations'}[name]
        p = commands.add_parser(name, help=description)
        p.add_argument('alias')
        p.add_argument('--history-dir', type=Path)
        p.add_argument('--json', action='store_true')
        if name == 'smoke-session':
            p.add_argument('--course', type=canvas_id, required=True)
        else:
            p.add_argument('--session', required=True)
        if name == 'cleanup-smoke':
            p.add_argument('--execute', action='store_true')
            p.add_argument('--expect')
        if name in {'verify-smoke-assignment', 'verify-smoke-file', 'verify-smoke-item-title'}: p.add_argument('--preview-file', type=Path, required=True)
        if name == 'verify-smoke-item-title': p.add_argument('--before-name', required=True)


class Store:
    def __init__(self, history, session):
        if not re.fullmatch('[0-9a-f]{32}', session):
            refuse('Invalid smoke-session ID')
        self.root = safe_path(history.path / 'smoke')
        self.key_path = safe_path(self.root / '.signing-key')
        self.path = safe_path(self.root / (session + '.json'))

    def secure(self, path):
        safe_path(path)
        if os.name != 'nt' and path.stat().st_mode & 0o077:
            refuse('Smoke records and signing key must have owner-only permissions')

    def key(self, create=False):
        if create:
            self.root.mkdir(mode=0o700, exist_ok=True)
            self.secure(self.root)
            try:
                fd = os.open(self.key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(os.urandom(32)); stream.flush(); os.fsync(stream.fileno())
        self.secure(self.root); self.secure(self.key_path)
        key = self.key_path.read_bytes()
        if len(key) != 32:
            refuse('Invalid smoke signing key')
        return key

    def load(self):
        self.secure(self.path)
        try:
            packet = json.loads(self.path.read_text(encoding='utf-8'))
            data = packet['data']
            signature = hmac.new(self.key(), canonical(data).encode(), hashlib.sha256).hexdigest()
            valid = hmac.compare_digest(signature, packet['signature']) and data['session'] == self.path.stem and data['schema_version'] == 1
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            refuse('Smoke-session signature or identity differs; no writes sent')
        return data

    def save(self, data, create=False):
        key = self.key(create)
        if self.path.exists(): self.secure(self.path)
        packet = {'data': data, 'signature': hmac.new(key, canonical(data).encode(), hashlib.sha256).hexdigest()}
        fd, temporary = tempfile.mkstemp(prefix='.smoke-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(canonical(packet) + '\n'); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            if os.name != 'nt':
                directory = os.open(self.root, os.O_RDONLY)
                try: os.fsync(directory)
                finally: os.close(directory)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


def binding(reader, course):
    return {'alias': reader.client.account.alias, 'origin': reader.client.origin, 'user_id': reader.client.account.user_id, 'course_id': course}


def context(reader, data):
    verify_identity(reader.client)
    if binding(reader, data['binding']['course_id']) != data['binding']:
        refuse('Smoke session belongs to a different account, origin or user')
    base = '/api/v1/courses/' + data['binding']['course_id']
    course = reader.object(base)
    if id_string(course.get('id')) != data['binding']['course_id'] or course.get('workflow_state') != 'unpublished':
        refuse('Smoke cleanup requires the same unpublished course')
    permissions = reader.object(base + '/permissions', {'permissions[]': list(DELETE_PERMISSIONS)})
    if any(permissions.get(k) is not True for k in DELETE_PERMISSIONS):
        refuse('Every required delete permission must be explicitly true')
    return base, course, permissions


def listing(reader, path):
    rows = reader.client.paginate(path).items
    if not all(isinstance(r, dict) for r in rows): refuse('Malformed smoke inventory')
    ids = [id_string(r.get('page_id') if path.endswith('/pages') else r.get('id')) for r in rows]
    if len(set(ids)) != len(ids): refuse('Duplicate identities in smoke inventory')
    return rows


def ordered(rows):
    return [id_string(r['id']) for r in sorted(rows, key=lambda r: (r.get('position') or 0, id_string(r['id'])))]


def inventory(reader, base, owned=()):
    excluded = {(r['kind'], r['id']) for r in owned}
    result, choices = {}, {}
    for kind, endpoint in {**KINDS, 'folder': 'folders', 'assignment_group': 'assignment_groups'}.items():
        rows = listing(reader, base + '/' + endpoint)
        present = {id_string(r.get('page_id') if kind == 'page' else r['id']) for r in rows}
        for row in owned:
            if row['kind'] == kind and ((row['id'] in present) == bool(row.get('deleted'))):
                refuse('Recorded test-object presence differs from the complete course inventory')
        rows = [r for r in rows if (kind, id_string(r.get('page_id') if kind == 'page' else r['id'])) not in excluded]
        result[kind] = sorted(id_string(r.get('page_id') if kind == 'page' else r['id']) for r in rows)
        if kind in {'folder', 'assignment_group'}:
            choices[kind] = [{'id': id_string(r['id']), 'name': r.get('name')} for r in rows]
        if kind == 'module':
            result['module_order'] = ordered(rows)
            items = {id_string(r['id']): listing(reader, base + '/modules/' + id_string(r['id']) + '/items') for r in rows}
            result['module_items'] = {mid: digest(stable(values)) for mid, values in items.items()}
            result['item'] = sorted(id_string(r['id']) for values in items.values() for r in values)
        if kind == 'assignment':
            result['assignment_order'] = {group: ordered([r for r in rows if str(r.get('assignment_group_id')) == group]) for group in sorted({str(r.get('assignment_group_id')) for r in rows})}
    return result, choices


def prepare(reader, args, history):
    session = uuid.uuid4().hex
    data = {'schema_version': 1, 'session': session, 'binding': binding(reader, args.course), 'prefix': 'TEMP Canvas smoke ' + session[:12], 'owned': [], 'pending': None, 'closed': False}
    base, course, permissions = context(reader, data)
    data['baseline'], choices = inventory(reader, base)
    with history.locked():
        Store(history, session).save(data, create=True)
    return {'mode': 'prepared', 'session': session, 'prefix': data['prefix'], 'course': {k: course.get(k) for k in ('id', 'name', 'workflow_state')}, 'delete_permissions': permissions, 'existing_containers': choices, 'baseline_counts': {k: len(v) for k, v in data['baseline'].items() if isinstance(v, list)}, 'writes_sent': 0}, 0


class Session:
    def __init__(self, reader, history, session, downloader=None):
        self.reader, self.history = reader, history
        self.store = Store(history, session)
        self.data = self.store.load()
        self.downloader = downloader
        self.base, _, _ = context(reader, self.data)

    def own(self, kind, rid):
        found = next((r for r in self.data['owned'] if r['kind'] == kind and r['id'] == rid and not r.get('deleted')), None)
        if found is None: refuse('Target is not a recorded live test creation')
        return found

    def snapshot(self, row, expected=None):
        obj = self.reader.object(row['path'])
        if expected is not None and (stable(obj) != stable(expected) or row['kind'] == 'page' and obj.get('url') != expected.get('url')):
            keys = sorted(k for k in set(stable(obj)) | set(stable(expected)) if stable(obj).get(k) != stable(expected).get(k))
            refuse('Object changed between execution readback and its cleanup receipt: ' + ', '.join(keys))
        if id_string(obj.get('page_id') if row['kind'] == 'page' else obj.get('id')) != row['id']:
            refuse('Smoke readback returned the wrong identity')
        if row['kind'] in {'page', 'assignment', 'module'} and obj.get('published') is not False:
            refuse('Test object is published or publication state is unknown')
        if obj.get('front_page') or obj.get('has_submitted_submissions'):
            refuse('A test object became a front page or received a submission')
        value = stable(obj)
        if row['kind'] == 'page':
            value['page_slug'] = obj.get('url')
            value['latest_revision'] = id_string(self.reader.object(row['path'] + '/revisions/latest').get('revision_id'))
        if row['kind'] == 'module':
            items = listing(self.reader, row['path'] + '/items')
            expected = {r['id'] for r in self.data['owned'] if r['kind'] == 'item' and r.get('module') == row['id'] and not r.get('deleted')}
            if {id_string(r['id']) for r in items} != expected:
                refuse('Test module contains an unrecorded item')
            value['smoke_items'] = stable(items)
        if row['kind'] == 'file':
            from canvas_export import download
            with tempfile.TemporaryDirectory() as directory:
                evidence = (self.downloader or download)(self.reader.client, obj, Path(directory).resolve() / 'content')
            value['smoke_content_sha256'] = evidence['sha256']
        return digest(value)

    def module_guard(self, row):
        obj = self.reader.object(row['path'])
        return digest(stable({k: v for k, v in obj.items() if k not in {'updated_at', 'items_count', 'items'}}))

    def refresh_parent(self, row):
        parent = self.own('module', row['module'])
        if self.module_guard(parent) != parent['container_guard']:
            refuse('Parent module changed outside the recorded item action')
        parent['snapshot'] = self.snapshot(parent)

    def check(self):
        if self.data['pending']:
            refuse('Session has an interrupted or uncertain action; inspect it before any further mutation or cleanup')
        if self.data['closed']: refuse('Smoke session is closed')
        self.check_state()

    def check_state(self):
        current, _ = inventory(self.reader, self.base, self.data['owned'])
        if current != self.data['baseline']:
            refuse('Original inventory or order differs, or an unrecorded object exists; no deletion is safe')
        for row in self.data['owned']:
            if not row.get('deleted') and (not row.get('snapshot') or self.snapshot(row) != row['snapshot']):
                refuse('Test ' + row['kind'] + ' ' + row['id'] + ' changed or lacks verified readback; no mutation is safe')

    def confirm_absent(self, row, allow_page_denial=False, allow_item_tombstone=False):
        try:
            self.reader.object(row['path'])
        except CanvasError as error:
            status = error.status
            if status == 403 and error.kind == 'denied' and row['kind'] == 'page' and allow_page_denial:
                permissions = self.reader.object(self.base + '/permissions', {'permissions[]': ['manage_wiki_update']})
                if permissions.get('manage_wiki_update') is not True:
                    refuse('Denied page read without explicit page-edit permission cannot prove absence')
            elif status != 404:
                raise
        else:
            if row['kind'] != 'item' or not allow_item_tombstone:
                refuse('Test object is still readable; no absence was established')
            record=self.reader.object(row['path'])
            if id_string(record.get('id')) != row['id'] or str(record.get('module_id')) != row['module']:
                refuse('Readable module-item deletion record has the wrong identity')
            permissions=self.reader.object(self.base+'/permissions',{'permissions[]':['manage_course_content_edit']})
            if permissions.get('manage_course_content_edit') is not True:
                refuse('Active-item absence requires explicit module-edit permission')
            status=200
        row['deleted'] = True
        if row['kind'] == 'item': self.refresh_parent(row)
        # An object read denial never proves absence alone: require the complete scoped inventory and baseline.
        self.check_state()
        row['removal_evidence'] = {'object_read_status': status, 'complete_inventory_absence': True, 'original_inventory_preserved': True}
        return row['removal_evidence']

    def attach(self, builder):
        a = builder.args
        if a.command not in SUPPORTED or getattr(a, 'course', None) != self.data['binding']['course_id']:
            refuse('Command or course is outside the smoke session')
        self.check()
        kind = SUPPORTED[a.command]
        creates = a.command.startswith('create-') or a.command in {'upload-file', 'add-module-item'}
        if any(getattr(a, k, None) for k in ('notify', 'published', 'front_page', 'allow_duplicate', 'replace', 'rename_on_conflict', 'move_to_module')):
            refuse('Smoke writes cannot publish, notify, replace, duplicate or move content')
        if kind in {'page', 'assignment', 'module'}:
            name = getattr(a, 'title', None) if kind == 'page' else getattr(a, 'name', None)
            if name is not None and not name.startswith(self.data['prefix'] + ' '): refuse('Test names must use this session prefix')
        if not creates:
            self.own(kind, getattr(a, kind))
        if kind == 'assignment':
            if creates and (a.points != 0 or a.submission_type != ['not_graded']): refuse('Smoke assignments require zero points and not_graded')
            if a.points not in (None, 0) or a.submission_type not in (None, ['not_graded']) or any(getattr(a, k, None) for k in ('due_at', 'lock_at', 'unlock_at')):
                refuse('Smoke assignments cannot add points, submissions or dates')
            if creates and a.assignment_group not in self.data['baseline']['assignment_group']: refuse('Choose an existing assignment group explicitly')
            if not creates and a.assignment_group is not None: refuse('Smoke assignment edits cannot change groups')
        if kind == 'module' and any(getattr(a, k, None) is not None for k in ('position', 'prerequisite', 'unlock_at', 'sequential')):
            refuse('Smoke modules append and retain default progression settings')
        if kind == 'file':
            if a.folder not in self.data['baseline']['folder'] or not a.name or not a.name.startswith(self.data['prefix'] + ' ') or not a.verify_content:
                refuse('Smoke uploads require a session filename, existing folder and --verify-content')
        if kind == 'item':
            self.own('module', a.module)
            if getattr(a, 'position', None) is not None: refuse('Smoke module items append without changing existing order')
            if creates:
                if a.type == 'Page': self.own('page', a.page)
                elif a.type in {'Assignment', 'File'}: self.own(a.type.lower(), a.content_id)
                elif a.type != 'SubHeader': refuse('Smoke items can reference only this session\'s content')
            linked=builder.steps[-1]['readback'].get('linked_title')
            if linked: self.own(linked['kind'],linked['id'])
        self.kind, self.creates = kind, creates
        self.builder = builder
        token = digest(self.data)
        builder.plan.pop('preview_hash')
        builder.plan['smoke_session'] = {'id': self.data['session'], 'state_hash': token, 'cleanup': 'unchanged recorded creations only'}
        builder.plan['preview_hash'] = digest({'plan': builder.plan, 'steps': builder.steps})

    def begin(self, operation):
        # Called under the same history lock as execution, before its first network mutation.
        if self.store.load() != self.data: refuse('Smoke-session state changed since preview')
        context(self.reader, self.data); self.check()
        self.data['pending'] = {'operation': operation, 'command': self.builder.args.command, 'created_id': None}
        linked=self.builder.steps[-1]['readback'].get('linked_title')
        if linked: self.data['pending']['linked_title']=linked
        self.store.save(self.data)

    def learned(self, rid, path):
        if not self.creates: return
        if rid in self.data['baseline'].get(self.kind, []) or any(r['kind'] == self.kind and r['id'] == rid for r in self.data['owned']):
            refuse('Creation returned a pre-existing or previously recorded identity')
        row = {'kind': self.kind, 'id': rid, 'path': path, 'snapshot': None}
        if self.kind == 'item': row['module'] = self.builder.args.module
        self.data['owned'].append(row)
        self.data['pending']['created_id'] = rid
        self.store.save(self.data)

    def complete(self, variables, record):
        rid = variables[self.kind + '.id']
        row = self.own(self.kind, rid)
        row['snapshot'] = self.snapshot(row, record)
        row['position'] = record.get('position') or 0
        if self.kind == 'module': row['container_guard'] = self.module_guard(row)
        if self.kind == 'item':
            linked=self.data['pending'].get('linked_title')
            if linked:
                source=self.reader.object(linked['path'])
                inverse=stable(source)
                inverse.update(linked['before'])
                for key in linked['absent_before']: inverse.pop(key,None)
                if source.get(linked['field'])!=linked['expected'] or digest(stable(inverse))!=linked['before_hash']:
                    refuse('Associated content changed beyond the planned module-item title effect')
                related=self.own(linked['kind'],linked['id'])
                related['snapshot']=self.snapshot(related,source)
            self.refresh_parent(row)
        self.data['pending'] = None
        self.store.save(self.data)

    def refused_before_change(self):
        self.data['pending'] = None
        self.store.save(self.data)


def cleanup(reader, args, history, downloader=None):
    if args.execute and (not args.expect or not re.fullmatch('[0-9a-f]{64}', args.expect)):
        refuse('Cleanup execution requires its reviewed preview hash')
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        session.check()
        rank = {'item': 0, 'module': 1, 'assignment': 2, 'page': 3, 'file': 4}
        # Remove later positions first so Canvas's reindexing cannot change a remaining owned target.
        targets = sorted((r for r in session.data['owned'] if not r.get('deleted')), key=lambda r: (rank[r['kind']], -r.get('position', 0), r['id']))
        plan = {'command': 'cleanup-smoke', 'session': args.session, 'binding': session.data['binding'], 'state_hash': digest(session.data), 'deletions': [{'kind': r['kind'], 'id': r['id'], 'method': 'DELETE', 'path': r['path'], 'snapshot': r['snapshot']} for r in targets], 'effects': ['Permanently delete only the listed unchanged test creations; files are irretrievable', 'Verify their absence and original inventory/order; preserve folders and assignment groups']}
        plan['preview_hash'] = digest(plan)
        if not args.execute: return {'mode': 'preview', **plan, 'writes_sent': 0}, 0
        if args.expect != plan['preview_hash']: refuse('Cleanup preview is stale; no writes sent')
        sent, removed = 0, []
        operation = uuid.uuid4().hex
        active, phase = None, 'before_send'
        def journal(outcome, resolves=None, row=None):
            record = {'schema_version': 1, 'record_id': uuid.uuid4().hex, 'operation_id': operation, 'time': history.now.isoformat(), 'kind': 'write', 'command': 'cleanup-smoke', 'account': reader.client.account.alias, 'course_ids': [session.data['binding']['course_id']], 'outcome': outcome, 'target_ids': [row['id']] if row else [r['id'] for r in targets], 'preview_hash': plan['preview_hash']}
            if resolves: record['resolves'] = resolves
            history._append(record)
            return record['record_id']
        try:
            for row in targets:
                context(reader, session.data); session.check()
                session.data['pending'] = {'command': 'cleanup-smoke', 'kind': row['kind'], 'id': row['id'], 'operation_id': operation}
                session.store.save(session.data)
                active = journal('uncertain', row=row)
                session.data['pending']['record_id'] = active
                session.store.save(session.data)
                sent += 1
                phase = 'sending'
                response = parse_json(reader.client.request('DELETE', row['path']))
                phase = 'after_send'
                if row['kind'] == 'page' and isinstance(response, dict) and response.get('page_id') is not None and str(response['page_id']) != row['id']:
                    refuse('Delete acknowledgment returned a different page ID')
                page_ack = row['kind'] == 'page' and isinstance(response, dict) and str(response.get('page_id')) == row['id']
                session.data['pending']['delete_acknowledged'] = True
                session.data['pending']['page_id_acknowledged'] = page_ack
                session.store.save(session.data)
                session.confirm_absent(row, allow_page_denial=page_ack, allow_item_tombstone=row['kind']=='item')
                session.data['pending'] = None
                session.store.save(session.data)
                journal('verified', resolves=active, row=row)
                active = None
                removed.append({'kind': row['kind'], 'id': row['id']})
            session.check()
            session.data['closed'] = True
            session.store.save(session.data)
            journal('verified')
            return {'mode': 'executed', 'outcome': 'verified', 'writes_sent': sent, 'removed': removed, 'baseline_restored': True}, 0
        except Exception as error:
            if active and phase == 'sending' and isinstance(error, CanvasError) and error.status in {400, 401, 403, 404, 409, 422, 429}:
                try: journal('not_landed', resolves=active)
                except OSError: pass
            return {'mode': 'executed', 'outcome': 'PARTIAL or uncertain' if sent else 'refused', 'writes_sent': sent, 'removed': removed, 'baseline_restored': False, 'error_kind': error.kind if isinstance(error, CanvasError) else 'transport_or_history_error', 'error_status': error.status if isinstance(error, CanvasError) else None, 'phase': phase, 'session': args.session}, 3 if sent else 1


def verify_cleanup(reader, args, history, downloader=None):
    """Resolve only a recorded pending deletion by fresh absence checks; never send another mutation."""
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending']
        if session.data['closed'] or not pending or pending.get('command') != 'cleanup-smoke':
            refuse('Verification requires this signed session\'s pending cleanup deletion')
        row = session.own(pending['kind'], pending['id'])
        if not row.get('snapshot'): refuse('Pending target lacks verified creation provenance')
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r.get('command') == 'cleanup-smoke' and r.get('target_ids') == [row['id']] and (r.get('outcome') == 'uncertain' or r.get('recorded_outcome') == 'uncertain')]
        if pending.get('record_id'): markers = [r for r in markers if r['record_id'] == pending['record_id']]
        if pending.get('operation_id'): markers = [r for r in markers if r.get('operation_id') == pending['operation_id']]
        if len(markers) != 1: refuse('The pending deletion does not have one unambiguous durable history marker')
        # This is an observation of absence after an interrupted deletion, not proof of which actor removed it.
        evidence = session.confirm_absent(row, allow_page_denial=True, allow_item_tombstone=row['kind']=='item' and pending.get('delete_acknowledged') is True)
        session.data['pending'] = None
        session.data['closed'] = all(r.get('deleted') for r in session.data['owned'])
        history._append({'schema_version': 1, 'record_id': uuid.uuid4().hex, 'operation_id': markers[0]['operation_id'], 'time': history.now.isoformat(), 'kind': 'write', 'command': 'verify-smoke-cleanup', 'account': reader.client.account.alias, 'course_ids': [session.data['binding']['course_id']], 'outcome': 'verified', 'resolves': markers[0]['record_id'], 'target_ids': [row['id']], 'coverage': evidence})
        session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified_absent', 'session': args.session, 'verified_absent': [{'kind': row['kind'], 'id': row['id']}], 'evidence': evidence, 'baseline_restored': session.data['closed'], 'session_closed': session.data['closed'], 'writes_sent': 0}, 0


def verify_assignment(reader, args, history):
    """Verify one signed response ID after the documented ungraded-point normalization, never guess a creation."""
    with history.locked():
        session = Session(reader, history, args.session)
        pending = session.data['pending']
        if not pending or pending.get('command') != 'create-assignment' or not pending.get('created_id') or session.data['closed']:
            refuse('Assignment verification requires a signed acknowledged creation ID')
        row = session.own('assignment', pending['created_id'])
        if row.get('snapshot') is not None or row['id'] in session.data['baseline']['assignment'] or row['path'] != session.base + '/assignments/' + row['id']:
            refuse('Assignment is not this session\'s unverified new creation')
        original = json.loads(safe_path(args.preview_file).read_text(encoding='utf-8'))
        if original.get('mode') != 'preview' or original.get('command') != 'create-assignment' or original.get('writes_sent') != 0 or len(original.get('steps', [])) != 1:
            refuse('The original creation preview is required')
        if original['account'] != {k: session.data['binding'][k] for k in ('alias', 'origin', 'user_id')} or original['context'] != {'type': 'course', 'id': session.data['binding']['course_id'], 'course_id': session.data['binding']['course_id']} or original['smoke_session']['id'] != args.session:
            refuse('Creation preview context differs from the signed session')
        before = copy.deepcopy(session.data)
        before['pending'] = None
        before['owned'] = [r for r in before['owned'] if not (r['kind'] == 'assignment' and r['id'] == row['id'])]
        if digest(before) != original['smoke_session']['state_hash']:
            refuse('The creation preview does not match the signed pre-creation state')
        step = copy.deepcopy(original['steps'][0])
        if step.get('method') != 'POST' or step.get('path') != session.base + '/assignments' or step.get('out') != 'assignment' or step['readback']['path'] != session.base + '/assignments/$assignment.id' or step['readback']['resource'] != 'id':
            refuse('Preview is not the bounded assignment-creation request')
        fields = step['fields']
        names = {'name', 'published', 'points_possible', 'assignment_group_id', 'submission_types', 'description'}
        keys = {'assignment[' + key + ']' + ('[]' if key == 'submission_types' else '') for key in names} | {'assignment[notify_of_update]'}
        if set(fields) != keys or fields['assignment[published]'] is not False or fields['assignment[notify_of_update]'] is not False or fields['assignment[points_possible]'] != 0 or fields['assignment[submission_types][]'] != ['not_graded'] or fields['assignment[assignment_group_id]'] not in session.data['baseline']['assignment_group'] or not fields['assignment[name]'].startswith(session.data['prefix'] + ' '):
            refuse('Preview is outside the quiet ungraded smoke-assignment contract')
        changes = [c for c in original['changes'] if c['field'] == 'description']
        if len(changes) != 1: refuse('Creation description is missing or ambiguous')
        body = changes[0]['converted_html']
        if fields['assignment[description]'] != {'bytes': len(body.encode()), 'sha256': hashlib.sha256(body.encode()).hexdigest()}:
            refuse('Creation description differs from its fingerprint')
        fields['assignment[description]'] = body
        expected = {key: fields['assignment[' + key + ']' + ('[]' if key == 'submission_types' else '')] for key in names}
        expected['id'] = '$assignment.id'
        if any(n.get('field') == 'points_possible' and n.get('stored') is None for n in original.get('normalizations', [])):
            expected['points_possible'] = None
        if set(step['readback']['fields']) != set(expected): refuse('Unexpected readback fields in the original preview')
        step['readback']['fields'] = expected
        plan = {k: v for k, v in original.items() if k not in {'mode', 'writes_sent', 'preview_hash'}}
        fingerprint = digest({'plan': plan, 'steps': [step]})
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r.get('operation_id') == pending['operation'] and r.get('command') == 'create-assignment' and (r.get('outcome') == 'uncertain' or r.get('recorded_outcome') == 'uncertain')]
        if len(markers) != 1 or fingerprint != original['preview_hash'] or markers[0]['preview_hash'] != fingerprint:
            refuse('The creation request does not match its durable history fingerprint')
        record = reader.object(row['path'])
        expected.update(id=row['id'], points_possible=None)
        differences = [key for key, value in expected.items() if not matches(record.get(key), value, key)]
        if differences or not record.get('created_at') or record.get('updated_at') != record['created_at'] or record.get('has_submitted_submissions') is not False or record.get('has_overrides') or any(record.get(key) is not None for key in ('due_at', 'unlock_at', 'lock_at')):
            refuse('The acknowledged assignment differs in ' + ', '.join(differences or ['creation timestamps, submission state or dates']))
        row['snapshot'] = session.snapshot(row, record)
        row['position'] = record.get('position') or 0
        session.check_state()
        session.data['pending'] = None
        evidence = {'field': 'points_possible', 'sent': 0, 'stored': None, 'submission_types': ['not_graded']}
        history._append({'schema_version': 1, 'record_id': uuid.uuid4().hex, 'operation_id': pending['operation'], 'time': history.now.isoformat(), 'kind': 'write', 'command': 'verify-smoke-assignment', 'account': reader.client.account.alias, 'course_ids': [session.data['binding']['course_id']], 'outcome': 'verified', 'resolves': markers[0]['record_id'], 'target_ids': [row['id']], 'preview_hash': fingerprint, 'coverage': evidence})
        session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified', 'target_ids': {'assignment.id': row['id']}, 'normalizations': [evidence], 'writes_sent': 0}, 0


def inspect_creation(reader, args, history, downloader=None):
    session = Session(reader, history, args.session, downloader)
    pending = session.data['pending']
    if not pending or not pending.get('created_id'): refuse('Inspection requires a signed acknowledged creation ID')
    rows = [r for r in session.data['owned'] if r['id'] == pending['created_id'] and r.get('snapshot') is None]
    if len(rows) != 1: refuse('Pending creation identity is ambiguous')
    row = rows[0]
    before = reader.object(row['path'])
    fields = ('id', 'page_id', 'name', 'display_name', 'filename', 'folder_id', 'size', 'content-type', 'created_at', 'updated_at', 'modified_at', 'locked', 'hidden', 'locked_for_user', 'hidden_for_user', 'upload_status', 'published', 'points_possible', 'grading_type', 'submission_types', 'assignment_group_id', 'has_submitted_submissions', 'has_overrides', 'due_at', 'unlock_at', 'lock_at', 'position', 'items_count', 'state')
    content = None
    if row['kind'] == 'file':
        from canvas_export import download
        with tempfile.TemporaryDirectory() as directory:
            content = (downloader or download)(reader.client, before, Path(directory).resolve() / 'content')
    after = reader.object(row['path'])
    changed = sorted(k for k in set(stable(before)) | set(stable(after)) if stable(before).get(k) != stable(after).get(k))
    return {'mode': 'inspection', 'kind': row['kind'], 'id': row['id'], 'metadata_keys': sorted(after), 'before': {k: before[k] for k in fields if k in before}, 'after': {k: after[k] for k in fields if k in after}, 'content': content, 'changed_fields': changed, 'writes_sent': 0}, 0


def verify_file(reader, args, history, downloader=None):
    """Seal only an acknowledged, fully read-back upload with its original digest and untouched metadata."""
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        pending = session.data['pending']
        if not pending or pending.get('command') != 'upload-file' or not pending.get('created_id') or session.data['closed']:
            refuse('File verification requires a signed acknowledged upload ID')
        row = session.own('file', pending['created_id'])
        if row.get('snapshot') is not None or row['id'] in session.data['baseline']['file'] or row['path'] != '/api/v1/files/' + row['id']:
            refuse('File is not this session\'s unverified new upload')
        original = json.loads(safe_path(args.preview_file).read_text(encoding='utf-8'))
        if original.get('mode') != 'preview' or original.get('command') != 'upload-file' or original.get('writes_sent') != 0 or len(original.get('steps', [])) != 1:
            refuse('The original upload preview is required')
        if original['account'] != {k: session.data['binding'][k] for k in ('alias', 'origin', 'user_id')} or original['context'] != {'type': 'course', 'id': session.data['binding']['course_id'], 'course_id': session.data['binding']['course_id']} or original['smoke_session']['id'] != args.session:
            refuse('Upload preview context differs from the signed session')
        before = copy.deepcopy(session.data); before['pending'] = None
        before['owned'] = [r for r in before['owned'] if not (r['kind'] == 'file' and r['id'] == row['id'])]
        if digest(before) != original['smoke_session']['state_hash']: refuse('Upload preview differs from the signed pre-upload state')
        step = copy.deepcopy(original['steps'][0])
        changes = [c for c in original['changes'] if c['field'] == 'upload']
        if len(changes) != 1: refuse('Upload facts are missing or ambiguous')
        facts = changes[0]['file']; folder = step['fields'].get('parent_folder_id')
        if step.get('method') != 'POST' or step.get('path') != session.base + '/files' or step.get('out') != 'file' or step.get('replace') is not None or step.get('rename') is not False or step.get('verify_content') is not True or folder not in session.data['baseline']['folder'] or not facts['name'].startswith(session.data['prefix'] + ' '):
            refuse('Preview is outside the guarded new-upload contract')
        if step['fields'] != {'name': facts['name'], 'size': facts['size'], 'content_type': facts['content_type'], 'on_duplicate': 'rename', 'parent_folder_id': folder} or step['readback']['path'] != '/api/v1/files/$file.id' or step['readback']['resource'] != 'id' or set(step['readback']['fields']) != {'size', 'content-type', 'folder_id'}:
            refuse('Unexpected upload request or readback')
        step['upload'] = facts
        step['readback']['fields'] = {'size': facts['size'], 'content-type': facts['content_type'], 'folder_id': folder}
        plan = {k: v for k, v in original.items() if k not in {'mode', 'writes_sent', 'preview_hash'}}
        fingerprint = digest({'plan': plan, 'steps': [step]})
        markers = [r for r in history.rows(account=reader.client.account.alias, course=session.data['binding']['course_id'], kind='write') if r.get('operation_id') == pending['operation'] and r.get('command') == 'upload-file' and r.get('recorded_outcome') == 'uncertain']
        if fingerprint != original['preview_hash'] or len(markers) != 3 or any(r['outcome'] != 'verified' or r['preview_hash'] != fingerprint for r in markers):
            refuse('Upload lacks three verified protocol steps bound to its original fingerprint')
        record = reader.object(row['path'])
        expected = {'id': row['id'], 'display_name': facts['name'], 'size': facts['size'], 'content-type': facts['content_type'], 'folder_id': folder}
        if not matches(record, expected) or not record.get('created_at') or record.get('updated_at') != record['created_at'] or record.get('modified_at') != record['created_at'] or record.get('locked') is not False or record.get('hidden') is not False or any(record.get(k) is not None for k in ('lock_at', 'unlock_at')):
            refuse('The acknowledged file changed or does not match its original upload contract')
        from canvas_export import download
        with tempfile.TemporaryDirectory() as directory:
            content = (downloader or download)(reader.client, record, Path(directory).resolve() / 'content')
        if content['sha256'] != facts['sha256'] or content['bytes'] != facts['size']: refuse('Acknowledged file content differs from the original upload')
        row['snapshot'] = session.snapshot(row, record)
        session.check_state(); session.data['pending'] = None
        history._append({'schema_version': 1, 'record_id': uuid.uuid4().hex, 'operation_id': pending['operation'], 'time': history.now.isoformat(), 'kind': 'write', 'command': 'verify-smoke-file', 'account': reader.client.account.alias, 'course_ids': [session.data['binding']['course_id']], 'outcome': 'verified', 'target_ids': [row['id']], 'preview_hash': fingerprint, 'coverage': {'content_sha256': facts['sha256'], 'bytes': facts['size']}})
        session.store.save(session.data)
        return {'mode': 'verified', 'outcome': 'verified', 'target_ids': {'file.id': row['id']}, 'content': content, 'writes_sent': 0}, 0


def verify_item_title(reader, args, history, downloader=None):
    """Reconcile a legacy recorded item-title edit only by proving the old linked-assignment fingerprint."""
    with history.locked():
        session = Session(reader, history, args.session, downloader)
        if session.data['pending'] or session.data['closed']: refuse('Title-effect verification requires a completed recorded edit')
        original = json.loads(safe_path(args.preview_file).read_text(encoding='utf-8'))
        if original.get('mode') != 'preview' or original.get('command') != 'edit-module-item' or original.get('writes_sent') != 0 or len(original.get('steps', [])) != 1:
            refuse('The original item-title preview is required')
        if original['account'] != {k: session.data['binding'][k] for k in ('alias','origin','user_id')} or original['context']['course_id'] != session.data['binding']['course_id'] or original['smoke_session']['id'] != args.session:
            refuse('Title preview differs from the signed session')
        item = session.own('item',original['target']['item_id']); module = session.own('module',original['target']['module_id'])
        if item['module'] != module['id']: refuse('Item is not in its recorded test module')
        step = copy.deepcopy(original['steps'][0]); fields = step['fields']
        if set(fields) != {'module_item[title]'} or step['method'] != 'PUT' or step['path'] != item['path'] or step['readback']['path'] != item['path'] or set(step['readback']['fields']) != {'title','id'} or step['readback'].get('linked_title'):
            refuse('Only an exact legacy title-only request can be reconciled')
        title = fields['module_item[title]']
        step['readback']['fields'] = {'title':title,'id':item['id']}
        plan = {k:v for k,v in original.items() if k not in {'mode','writes_sent','preview_hash'}}
        fingerprint = digest({'plan':plan,'steps':[step]})
        if fingerprint != original['preview_hash']: refuse('Title preview fingerprint differs')
        rows = list(history.rows(account=reader.client.account.alias,course=session.data['binding']['course_id'],kind='write'))
        markers = [r for r in rows if r.get('command') == 'edit-module-item' and r.get('preview_hash') == fingerprint and r.get('recorded_outcome') == 'uncertain' and r['outcome'] == 'verified' and item['id'] in r.get('target_ids',[])]
        if len(markers) != 1: refuse('Title edit lacks one verified durable operation')
        observed = reader.object(item['path'])
        if observed.get('type') != 'Assignment' or observed.get('title') != title or session.snapshot(item) != item['snapshot']:
            refuse('Recorded item changed beyond the verified title edit')
        change = [c for c in original['changes'] if c['field'] == 'title']
        if len(change) != 1 or change[0]['after'] != title: refuse('Original title delta is missing')
        old_item = dict(observed,title=change[0]['before'])
        if digest(stable(old_item)) != original['dependencies'].get(item['path']+'?{}'):
            refuse('Item identity/content differs from its pre-edit fingerprint')
        related = session.own('assignment',id_string(observed.get('content_id')))
        if not args.before_name.startswith(session.data['prefix']+' '): refuse('Prior name is outside the test namespace')
        def stamp(record): return dt.datetime.fromisoformat(record['time']).timestamp()
        event = markers[0]; event_end = max(stamp(r) for r in rows if r.get('operation_id') == event['operation_id'] and r.get('command') == 'edit-module-item')
        prior = [r for r in rows if r.get('command') in {'create-assignment','edit-assignment'} and r.get('recorded_outcome') == 'uncertain' and r['outcome'] == 'verified' and stamp(r) < stamp(event) and any(t.get('operation_id') == r['operation_id'] and related['id'] in t.get('target_ids',[]) for t in rows)]
        if not prior: refuse('Prior linked-assignment write is not recorded')
        prior = max(prior,key=stamp)
        prior_end = max(stamp(r) for r in rows if r.get('operation_id') == prior['operation_id'] and r.get('command') == prior['command'])
        lower, upper = math.floor(stamp(prior))-1, math.ceil(prior_end)+1
        if upper-lower > 120: refuse('Prior write interval is too broad for exact timestamp proof')
        record = reader.object(related['path'])
        updated = dt.datetime.fromisoformat(record.get('updated_at') or '').timestamp()
        if record.get('name') != title or not math.floor(stamp(event))-1 <= updated <= math.ceil(event_end)+1:
            refuse('Linked name/timestamp does not match the recorded item edit')
        proof = None
        for second in range(lower,upper+1):
            value = dt.datetime.fromtimestamp(second,dt.timezone.utc).isoformat().replace('+00:00','Z')
            inverse = dict(record,name=args.before_name,updated_at=value)
            if digest(stable(inverse)) == related['snapshot']:
                proof = value; break
        if proof is None: refuse('Linked assignment changed beyond the exact title and recorded update timestamp')
        related['snapshot'] = session.snapshot(related,record)
        session.check_state()
        history._append({'schema_version':1,'record_id':uuid.uuid4().hex,'operation_id':event['operation_id'],'time':history.now.isoformat(),'kind':'write','command':'verify-smoke-item-title','account':reader.client.account.alias,'course_ids':[session.data['binding']['course_id']],'outcome':'verified','preview_hash':fingerprint,'target_ids':[item['id'],related['id']],'coverage':{'linked_title_effect':True,'prior_fingerprint_proved':True,'prior_updated_at':proof}})
        session.store.save(session.data)
        return {'mode':'verified','outcome':'verified','target_ids':{'item.id':item['id'],'assignment.id':related['id']},'prior_fingerprint_proved':True,'writes_sent':0},0
