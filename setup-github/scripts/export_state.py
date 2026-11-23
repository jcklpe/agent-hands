"""Private, durable local export publication recovery. No GitHub requests or automatic retirement."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import shutil
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'setup-agent-hands/scripts'))
from private_settings import safe, private, write, sync, fingerprint, StorageError


def root():return safe(Path(os.environ.get('AGENT_HANDS_STATE_DIR',str(Path.home()/'.agent-hands')))/'github-exports')


def directory(raw):
    p=safe(Path(raw));r=root()
    if p.parent!=r or not re.fullmatch(r'[a-f0-9]{32}',p.name):raise StorageError('Select an exact registered export run')
    if not p.is_dir() or p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o077:raise StorageError('Unsafe export run')
    return p


def read(run):
    run=directory(run);p=run/'publication.json';safe(p)
    if p.stat().st_uid!=os.getuid() or p.stat().st_mode&0o077:raise StorageError('Unsafe export record')
    value=json.loads(p.read_text());dest=safe(Path(value['destination']),False)
    if type(value.get('pid')) is not int or value['pid']<=0:raise StorageError('Invalid export controller')
    if value.get('kind')!='github-export-publication-v1' or not dest.is_dir():raise StorageError('Invalid publication record')
    for entry in value['entries']:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',entry['name']) or entry['name'] in ('.','..'):raise StorageError('Unsafe artifact name')
    return value


def signature(path):
    return fingerprint(path) if path.exists() or path.is_symlink() else None


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def locked():
    private(root());fd=os.open(root()/'.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except Exception:os.close(fd);raise
    return fd


def begin(destination,pid):
    dest=safe(Path(destination).absolute(),False)
    dest.mkdir(parents=True,exist_ok=True)
    if not dest.is_dir():raise StorageError('Invalid export destination')
    if type(pid) is not int or pid<=0:raise StorageError('Invalid export controller')
    os.kill(pid,0)
    if any(dest.glob('.github-export.*')):raise StorageError('Legacy export staging needs explicit inspection; no cleanup or replacement attempted')
    fd=locked()
    try:
        if dest.stat().st_dev!=root().stat().st_dev:raise StorageError('Cross-filesystem export publication is unsupported')
        for item in root().iterdir():
            if item.is_dir():
                previous=read(item)
                if previous['destination']==str(dest) and previous['status'] not in ('completed','retrieval_failed','restored'):
                    raise StorageError('Earlier publication needs inspection before another export')
        run=root()/uuid.uuid4().hex;private(run);private(run/'new');private(run/'previous')
        write(run/'publication.json',{'kind':'github-export-publication-v1','destination':str(dest),'pid':pid,'created':time.time(),'status':'retrieving','entries':[]})
        return str(run)
    finally:os.close(fd)


def no_replace(source,target):
    # Files use an exclusive hard-link publication; directories reserve an empty destination atomically. A concurrently populated directory makes rename fail rather than overwriting content.
    if source.is_dir():
        target.mkdir(mode=source.stat().st_mode&0o777)
        os.rename(source,target)
    else:
        os.link(source,target,follow_symlinks=False)
        sync(target.parent)
        source.unlink()


def flush_tree(path):
    if not path.exists():return
    fingerprint(path)
    for item in [path,*path.rglob('*')] if path.is_dir() else [path]:
        if item.is_file():
            fd=os.open(item,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.fsync(fd)
            finally:os.close(fd)
    if path.is_dir():
        for item in sorted((p for p in path.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync(item)
        sync(path)


def publish(run,names):
    fd=locked()
    try:
        run=directory(run);record=read(run);dest=Path(record['destination'])
        if record['status']!='retrieving' or record['entries']:raise StorageError('Publication was already dispatched; inspect instead of replaying')
        if len(names)!=len(set(names)):raise StorageError('Duplicate artifact names')
        for name in names:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',name) or name in ('.','..'):raise StorageError('Unsafe artifact name')
            before=signature(dest/name);after=signature(run/'new'/name)
            flush_tree(dest/name);flush_tree(run/'new'/name)
            record['entries'].append({'name':name,'before':before,'after':after})
        record['status']='publishing';write(run/'publication.json',record)
        for entry in record['entries']:
            name=entry['name'];current=dest/name;incoming=run/'new'/name;previous=run/'previous'/name
            if signature(current)!=entry['before'] or signature(incoming)!=entry['after']:raise StorageError('Export input changed before publication')
            record['pending']=name;write(run/'publication.json',record)
            if current.exists():
                os.rename(current,previous);sync(dest);sync(previous.parent)
                if signature(previous)!=entry['before']:raise StorageError('Original changed during publication; preserve its recovery copy')
            if incoming.exists():no_replace(incoming,current);sync(incoming.parent);sync(dest)
            if signature(current)!=entry['after']:raise StorageError('Published artifact differs; preserve recovery')
            record.pop('pending',None);write(run/'publication.json',record)
        record['status']='completed';write(run/'publication.json',record)
        return {'status':'export_completed','recoveryRetained':True}
    finally:os.close(fd)


def inspect(run):
    run=directory(run);record=read(run);dest=Path(record['destination']);entries=[]
    for entry in record['entries']:
        current=signature(dest/entry['name']);previous=signature(run/'previous'/entry['name'])
        entries.append({**entry,'current':current,'previous':previous,'can_restore':current is None and previous is not None and previous==entry['before']})
    try:os.kill(record['pid'],0);controller='alive'
    except ProcessLookupError:controller='absent'
    except OSError:controller='unknown'
    view={'status':record['status'],'entries':entries,'destination':str(dest),'controller':controller}
    return {**view,'hash':digest(view),'run':str(run)}


def restore(run,expected):
    fd=locked()
    try:
        run=directory(run);view=inspect(run)
        if view['controller']!='absent':raise StorageError('Export controller is live or its status is unknown')
        if not expected or view['hash']!=expected:raise StorageError('Recovery preview changed')
        record=read(run);dest=Path(record['destination']);restored=0
        for entry in view['entries']:
            if entry['can_restore']:
                target=dest/entry['name'];old=run/'previous'/entry['name']
                if target.exists() or target.is_symlink() or signature(old)!=entry['before']:raise StorageError('Restore target changed')
                no_replace(old,target);sync(old.parent);sync(dest);restored+=1
        if all(signature(dest/e['name'])==e['before'] for e in record['entries']):record['status']='restored'
        else:record['status']='partial_needs_review'
        record.pop('pending',None);write(run/'publication.json',record)
        return {'status':record['status'],'restored':restored,'recordsRetained':True}
    finally:os.close(fd)


def reconcile(run):
    fd=locked()
    try:
        run=directory(run);record=read(run);dest=Path(record['destination'])
        if record['entries']:
            if all(signature(dest/e['name'])==e['after'] and signature(run/'previous'/e['name'])==e['before'] for e in record['entries']):record['status']='completed'
            elif all(signature(dest/e['name'])==e['before'] for e in record['entries']):record['status']='restored'
            else:record['status']='partial_needs_review'
        elif record['status']=='retrieving':record['status']='retrieval_failed'
        write(run/'publication.json',record)
        return {'status':record['status'],'targetWrites':0,'recordsRetained':True}
    finally:os.close(fd)


def finish(run):
    # Called only by this run's EXIT trap. Persist classification; never discard preimages or journals.
    fd=locked()
    try:
        run=directory(run);record=read(run)
        if record['status']=='retrieving':record['status']='retrieval_failed';write(run/'publication.json',record)
        return {'status':record['status'],'recoveryRetained':True}
    finally:os.close(fd)


def retirement(run,execute=False,expected=None):
    fd=locked()
    try:
        run=directory(run);record=read(run);view=inspect(run)
        eligible=record['status'] in ('completed','retrieval_failed','restored') and view['controller']=='absent' and time.time()-record.get('created',time.time())>=7*86400
        tree=fingerprint(run)
        result={'status':'export_retirement_preview','eligible':eligible,'run':str(run),'hash':tree,'reason':'Resolved export run older than seven days; unresolved publication is protected'}
        if not execute:return result
        if not eligible or not expected or expected!=tree:raise StorageError('Retirement preview changed or run remains protected')
        shutil.rmtree(run);sync(root())
        return {'status':'export_run_retired','removed':1}
    finally:os.close(fd)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['begin','publish','inspect','restore','finish','retire','legacy','reconcile']);p.add_argument('path');p.add_argument('names',nargs='*');p.add_argument('--pid',type=int);p.add_argument('--execute',action='store_true');p.add_argument('--hash');a=p.parse_args()
    try:
        if a.command=='legacy':
            dest=safe(Path(a.path).absolute(),False)
            print(json.dumps({'status':'legacy_export_inventory','runs':[{'path':str(p),'hash':fingerprint(p),'classification':'Unregistered publication recovery; preserve pending owner review'} for p in sorted(dest.glob('.github-export.*'))]}));return
        if a.command=='begin':print(begin(a.path,a.pid));return
        if a.command=='publish':result=publish(a.path,a.names)
        elif a.command=='restore':
            if not a.execute:result=inspect(a.path)
            else:result=restore(a.path,a.hash)
        elif a.command=='inspect':result=inspect(a.path)
        elif a.command=='reconcile':result=reconcile(a.path)
        elif a.command=='retire':result=retirement(a.path,a.execute,a.hash)
        else:result=finish(a.path)
        print(json.dumps(result))
    except Exception:raise SystemExit('ERROR: Export publication or recovery requires inspection; private records retained. No automatic replay, overwrite or cleanup.')

if __name__=='__main__':main()
