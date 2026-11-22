"""Private Microsoft storage selection and explicit local migration; no service requests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid

class StateError(ValueError):
    pass


ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    'config': ('setup-microsoft-services', ['.env', 'm365-accounts.json']),
    'planner': ('use-planner', ['task-writes.jsonl', 'planner-task-chat', 'planner-task-delete']),
    'files': ('use-microsoft-files', ['file-writes.jsonl', '.organization-state']),
    'mail': ('use-outlook-mail', ['mail-writes.jsonl', '.draft-state']),
    'excel': ('use-excel-workbooks', ['workbook-writes.jsonl']),
}


def validate(path, outside=True):
    path = Path(path)
    if not path.is_absolute(): raise StateError('Private state paths must be absolute')
    for current in [*reversed(path.parents), path]:
        if current.is_symlink(): raise StateError('Private state cannot traverse symlinks')
        if outside and (current / '.git').exists(): raise StateError('Private state cannot live in a Git checkout')
    return path


def base():
    return validate(Path(os.environ.get('AGENT_HANDS_STATE_DIR', str(Path.home() / '.agent-hands'))) / 'microsoft')


def private_dir(path):
    validate(path)
    missing = []; current = path
    while not current.exists(): missing.append(current); current = current.parent
    for directory in reversed(missing): directory.mkdir(mode=0o700)
    st = path.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: raise StateError('Private state directories must be owner-only')


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write(path, value):
    validate(path, outside=False)
    temporary = path.with_name('.pending-' + uuid.uuid4().hex)
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out); out.write('\n'); out.flush(); os.fsync(out.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if temporary.exists(): temporary.unlink()


def fingerprint(path):
    result = []
    for item in [path, *sorted(path.rglob('*'))] if path.is_dir() else [path]:
        st = item.lstat()
        if item.is_symlink() or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077 or not (item.is_file() or item.is_dir()): raise StateError('Unsafe migration source')
        result.append([str(item.relative_to(path)) if item != path else '.', stat.S_IMODE(st.st_mode), hashlib.sha256(item.read_bytes()).hexdigest() if item.is_file() else None])
    return hashlib.sha256(json.dumps(result).encode()).hexdigest()


def location(group, create=True):
    if group not in GROUPS: raise StateError('Unknown private store')
    target = base() / group
    if (base() / '.migration.json').exists(): raise StateError('Microsoft state migration is incomplete; reconcile its private record before use')
    source = ROOT / GROUPS[group][0]
    pointer = source / '.runtime-state.json'
    legacy = any((source / name).exists() or (source / name).is_symlink() for name in GROUPS[group][1])
    if pointer.exists():
        validate(pointer, outside=False)
        if json.loads(pointer.read_text()) != {'kind': 'microsoft-state-moved-v1', 'destination': str(target)}: raise StateError('Private store selection changed; inspect the migration pointer')
        if not target.is_dir(): raise StateError('Migrated private store is missing; restore it instead of starting an empty history')
    elif legacy:
        raise StateError('Legacy Microsoft state exists; run authorize migrate-runtime before selecting a new default')
    if create: private_dir(target)
    return target


def literal_env(file):
    values = {}
    if not file.exists(): return values
    for line in file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise StateError('Malformed private env file')
        key, value = line.split('=', 1); value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]: raise StateError('Malformed private env quote')
            value = value[1:-1]
        values[key.strip()] = value
    return values


def migration_plan():
    if any(os.environ.get(k) for k in ('M365_CONFIG_DIR', 'M365_ENV_FILE', 'M365_ACCOUNTS_PATH', 'M365_FILES_AUDIT_LOG', 'M365_PLANNER_AUDIT_LOG', 'M365_MAIL_AUDIT_LOG', 'M365_EXCEL_AUDIT_LOG')):
        raise StateError('Explicit Microsoft paths are active; keep their selection and prepare a targeted migration instead of moving defaults')
    if (base() / '.migration.json').exists(): raise StateError('A previous migration needs reconciliation')
    config_source = ROOT / 'setup-microsoft-services'
    env = literal_env(config_source / '.env')
    if any(env.get(k) for k in env if k.endswith('_AUDIT_LOG')): raise StateError('Private audit overrides need a targeted migration; no defaults moved')
    account_name = env.get('M365_ACCOUNTS_PATH', 'm365-accounts.json')
    if not account_name or account_name in ('.', '..') or Path(account_name).is_absolute() or '..' in Path(account_name).parts: raise StateError('Absolute or escaping account paths need a targeted migration')
    units = []
    for group, (folder, names) in GROUPS.items():
        source = ROOT / folder
        if (source / '.runtime-state.json').exists(): raise StateError('A store is already migrated; inspect existing selections')
        names = list(names)
        if group == 'config':
            names = ['.env', account_name]
            account_file = source / account_name
            if account_file.exists():
                cfg = json.loads(account_file.read_text())
                for account in cfg.get('accounts', []):
                    if account.get('auth_provider', 'msal') != 'msal': continue
                    raw_token = account.get('token_path')
                    if not isinstance(raw_token, str) or not raw_token or raw_token in ('.', '..'): raise StateError('MSAL token path is missing or unsafe')
                    token = Path(raw_token)
                    if token.is_absolute() or '..' in token.parts: raise StateError('MSAL token path requires a targeted migration')
                    names.append(str(token))
        for name in dict.fromkeys(names):
            item = source / name
            if not item.exists() and not item.is_symlink(): continue
            validate(item, outside=False)
            if group == 'config' and not item.is_file(): raise StateError('Config and token inputs must be regular files')
            destination = base() / group / name
            validate(destination)
            if destination.exists() or destination.is_symlink(): raise StateError('Destination exists; refusing to merge private state')
            units.append({'group': group, 'source': str(item), 'destination': str(destination), 'hash': fingerprint(item)})
    return units


def migrate(execute=False):
    units = migration_plan()
    if not units: raise StateError('No default Microsoft stores need migration')
    if not execute: return {'status': 'microsoft_migration_preview', 'units': len(units), 'groups': sorted({u['group'] for u in units}), 'requires': 'Stop every Microsoft caller, including older installed copies. SDK authentication is not moved.'}
    private_dir(base())
    marker = base() / '.migration.json'
    fd = os.open(base() / '.migration.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    import fcntl
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if marker.exists(): raise StateError('Migration already in progress')
        for unit in units:
            source, destination = Path(unit['source']), Path(unit['destination'])
            private_dir(destination.parent)
            if source.stat().st_dev != destination.parent.stat().st_dev: raise StateError('Cross-filesystem migration is not supported')
            if fingerprint(source) != unit['hash']: raise StateError('Source changed before migration')
            if source.is_dir() and any(p.name.endswith('.lock') or p.name == 'lock' for p in source.rglob('*')):
                # Existing OS lock files can be idle; conservatively require their owning recovery procedure to resolve them first.
                raise StateError('Recovery lock files need inspection before migration')
        write(marker, {'kind': 'microsoft-runtime-migration-v1', 'stage': 'moving', 'units': units})
        for unit in units:
            source, destination = Path(unit['source']), Path(unit['destination'])
            if destination.exists(): raise StateError('Destination appeared during migration')
            os.rename(source, destination)
            sync_dir(source.parent); sync_dir(destination.parent)
            if fingerprint(destination) != unit['hash']: raise StateError('Moved content differs; preserve the migration record')
        for group, (folder, _) in GROUPS.items():
            private_dir(base() / group)
            write(ROOT / folder / '.runtime-state.json', {'kind': 'microsoft-state-moved-v1', 'destination': str(base() / group)})
        marker.unlink(); sync_dir(marker.parent)
        return {'status': 'microsoft_runtime_migrated', 'verified_units': len(units), 'sdkAuthenticationChanged': False}
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['path', 'migrate'])
    parser.add_argument('group', nargs='?', choices=list(GROUPS))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.command == 'path': print(location(args.group))
    else: print(json.dumps(migrate(args.execute)))


if __name__ == '__main__':
    try: main()
    except StateError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception:
        print('ERROR: Microsoft private storage is unavailable or migration needs inspection; no automatic retry or merge. Run the migration preview with default paths and inspect private recovery state.', file=sys.stderr)
        raise SystemExit(1)
