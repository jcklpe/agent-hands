"""Private smoke-test provenance and deletion of unchanged, recorded creations only."""
import hashlib
import hmac
import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from canvas_auth import CanvasError, id_string, parse_json, verify_identity
from canvas_history import safe_path
from canvas_write import canonical, digest, stable

DELETE_PERMISSIONS = ('manage_wiki_delete', 'manage_assignments_delete', 'manage_course_content_delete', 'manage_files_delete')
KINDS = {'page': 'pages', 'assignment': 'assignments', 'module': 'modules', 'file': 'files'}
SUPPORTED = {'create-page': 'page', 'edit-page': 'page', 'create-assignment': 'assignment', 'edit-assignment': 'assignment', 'create-module': 'module', 'edit-module': 'module', 'upload-file': 'file', 'add-module-item': 'item', 'edit-module-item': 'item'}


def refuse(message):
    raise CanvasError('smoke_refused', message)


def add_commands(commands, canvas_id):
    for name in ('smoke-session', 'cleanup-smoke'):
        p = commands.add_parser(name, help='prepare private test provenance' if name == 'smoke-session' else 'preview deletion of unchanged recorded test creations')
        p.add_argument('alias')
        p.add_argument('--history-dir', type=Path)
        p.add_argument('--json', action='store_true')
        if name == 'smoke-session':
            p.add_argument('--course', type=canvas_id, required=True)
        else:
            p.add_argument('--session', required=True)
            p.add_argument('--execute', action='store_true')
            p.add_argument('--expect')


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
            refuse('Object changed between execution readback and its cleanup receipt')
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
        current, _ = inventory(self.reader, self.base, self.data['owned'])
        if current != self.data['baseline']:
            refuse('Original inventory or order differs, or an unrecorded object exists; no deletion is safe')
        for row in self.data['owned']:
            if not row.get('deleted') and (not row.get('snapshot') or self.snapshot(row) != row['snapshot']):
                refuse('A test object changed or lacks verified readback; no mutation is safe')

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
                session.data['pending'] = {'command': 'cleanup-smoke', 'kind': row['kind'], 'id': row['id']}
                session.store.save(session.data)
                active = journal('uncertain', row=row)
                sent += 1
                phase = 'sending'
                parse_json(reader.client.request('DELETE', row['path']))
                phase = 'after_send'
                try:
                    reader.object(row['path'])
                except CanvasError as error:
                    if error.status != 404: raise
                else:
                    refuse('Deleted test object is still readable')
                row['deleted'] = True
                if row['kind'] == 'item':
                    session.refresh_parent(row)
                current, _ = inventory(reader, session.base, session.data['owned'])
                if current != session.data['baseline']:
                    refuse('Inventory or original order differs after deletion')
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
            return {'mode': 'executed', 'outcome': 'PARTIAL or uncertain' if sent else 'refused', 'writes_sent': sent, 'removed': removed, 'baseline_restored': False, 'error_kind': error.kind if isinstance(error, CanvasError) else 'transport_or_history_error', 'session': args.session}, 3 if sent else 1
