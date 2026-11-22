#!/usr/bin/env python3
"""Explicit project journal migration. Reads Git metadata; never contacts GitHub."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import SimpleNamespace
from collaboration import default_journal_root, state_location, Refusal, git


def tree(root):
    values = []
    for p in sorted(root.rglob('*')):
        if p.name == 'lock' and p.parent == root: continue
        st = p.lstat()
        if p.is_symlink() or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077 or not (p.is_file() or p.is_dir()): raise Refusal('Unsafe journal contents')
        values.append([str(p.relative_to(root)), stat.S_IMODE(st.st_mode), hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None])
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def private(path):
    missing = []; p = path
    while not p.exists(): missing.append(p); p = p.parent
    for p in reversed(missing): p.mkdir(mode=0o700)
    st = path.lstat()
    if path.is_symlink() or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: raise Refusal('Unsafe private directory')


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def write_private(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(value, out); out.flush(); os.fsync(out.fileno())
    sync_dir(path.parent)


def migrate(project, repo, host='github.com', execute=False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not re.fullmatch(r'[A-Za-z0-9.-]+',host): raise Refusal('Invalid repository or host')
    top = git(Path(project).absolute(), 'rev-parse','--show-toplevel')
    worktrees = git(Path(top),'worktree','list','--porcelain')
    primary = Path(next(line[9:] for line in worktrees.splitlines() if line.startswith('worktree ')))
    name = host + '_' + repo.replace('/','_')
    # Reuse the runtime's exact remote-identity check, with explicit old state selection.
    oldroot = primary / '.github/project-collaboration'
    context = SimpleNamespace(args=SimpleNamespace(project=str(primary),state_dir=str(oldroot)),host=host,repo=repo)
    source = state_location(context)
    target_root = default_journal_root(); target = target_root / name
    pending = target_root / ('.migration-' + name + '.json')
    if pending.exists(): raise Refusal('A previous migration needs reconciliation')
    if not source.is_dir() or source.is_symlink() or target.exists(): raise Refusal('Missing source or existing destination; refusing a merge')
    st = source.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) & 0o077: raise Refusal('Unsafe source directory')
    before = tree(source)
    if not execute: return {'status':'github_journal_migration_preview','source':str(source),'destination':str(target),'requires':'Stop all callers and old installed versions; no GitHub request is sent.'}
    private(target_root)
    fd = os.open(source / 'lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if source.stat().st_dev != target_root.stat().st_dev: raise Refusal('Cross-filesystem migration is unsupported')
        if tree(source) != before: raise Refusal('Journal changed during preparation')
        write_private(pending, {'source':str(source),'destination':str(target),'hash':before})
        os.rename(source,target)
        sync_dir(source.parent); sync_dir(target.parent)
        private(source)
        write_private(source/'moved.json', {'kind':'github-journal-moved-v1','destination':str(target)})
        # Old runtimes open this path with O_NOFOLLOW and must refuse instead of starting a second journal.
        (source/'lock').symlink_to('migrated-journal-do-not-use')
        sync_dir(source)
        if tree(target) != before: raise Refusal('Moved journal differs; preserve the migration record')
        pending.unlink(); sync_dir(pending.parent)
        return {'status':'github_journal_migrated','contentsVerified':True,'remoteWrites':0}
    finally: os.close(fd)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--project',required=True);p.add_argument('--repo',required=True);p.add_argument('--host',default='github.com');p.add_argument('--execute',action='store_true');a=p.parse_args()
    try: print(json.dumps(migrate(a.project,a.repo,a.host,a.execute)))
    except Exception:
        print('ERROR: Journal migration unavailable or uncertain. Stop callers and inspect the private source/destination; no merge or remote write attempted.',file=sys.stderr);sys.exit(1)
