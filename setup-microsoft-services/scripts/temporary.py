"""Registered disposable Microsoft runs. Never sweeps unregistered or live directories."""
import argparse
import errno
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import time
from runtime_state import validate, write

PREFIX = 'microsoft-work.'
MARKER = '.run.json'


def root_path(raw):
    root = Path(raw).resolve(strict=True)
    validate(root)
    if not root.is_dir(): raise ValueError('Temporary root must be a directory')
    return root


def candidates(root, now=None):
    now = time.time() if now is None else now
    result = []
    for folder in root.glob(PREFIX + '*'):
        try:
            st = folder.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700: continue
            marker = folder / MARKER
            mst = marker.lstat()
            if not stat.S_ISREG(mst.st_mode) or mst.st_uid != os.getuid() or stat.S_IMODE(mst.st_mode) != 0o600: continue
            record = json.loads(marker.read_text())
            if record.get('kind') != 'microsoft-disposable-run-v1' or record.get('device') != st.st_dev or record.get('inode') != st.st_ino: continue
            pid = record.get('pid'); created = record.get('created')
            if type(pid) is not int or pid <= 0 or type(created) not in (int, float) or not (24*3600 <= now-created): continue
            try: os.kill(pid, 0)
            except OSError as error:
                if error.errno != errno.ESRCH: continue
            else: continue
            # Refuse unusual contents instead of following or retiring externally linked data.
            if any(p.is_symlink() or p.lstat().st_uid != os.getuid() or not (p.is_file() or p.is_dir()) for p in folder.rglob('*')): continue
            result.append(folder)
        except (OSError, ValueError, TypeError): continue
    return result


def cleanup(root):
    removed = 0
    for folder in candidates(root):
        # Recheck age, identity and dead-controller status immediately before removal.
        if folder not in candidates(root): continue
        shutil.rmtree(folder); removed += 1
    return removed


def create(root, pid):
    if pid <= 0: raise ValueError('Invalid controller')
    os.kill(pid, 0)
    cleanup(root)
    folder = Path(tempfile.mkdtemp(prefix=PREFIX, dir=root))
    st = folder.stat()
    try: write(folder / MARKER, {'kind':'microsoft-disposable-run-v1', 'pid':pid, 'created':time.time(), 'device':st.st_dev, 'inode':st.st_ino})
    except Exception:
        shutil.rmtree(folder); raise
    return folder


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['create','cleanup']);parser.add_argument('--root',required=True);parser.add_argument('--pid',type=int);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    root=root_path(args.root)
    if args.command=='create': print(create(root,args.pid))
    elif args.execute: print(json.dumps({'removed':cleanup(root)}))
    else: print(json.dumps({'eligible_runs':len(candidates(root)), 'unregisteredRunsSkipped':True}))


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('ERROR: Microsoft temporary storage unavailable; no fallback or broad cleanup attempted')
