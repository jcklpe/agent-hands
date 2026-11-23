"""Dependency-free storage mechanics; provider wrappers declare their own file contract."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import uuid


class StorageError(ValueError): pass


def safe(path, outside=True):
    path=Path(path)
    if not path.is_absolute(): raise StorageError('Storage paths must be absolute')
    for p in [path,*path.parents]:
        if p.is_symlink(): raise StorageError('Storage cannot traverse symlinks')
        if outside and (p/'.git').exists(): raise StorageError('Private storage cannot live in a checkout')
    return path


def private(path):
    safe(path)
    missing=[];p=path
    while not p.exists(): missing.append(p);p=p.parent
    for p in reversed(missing):p.mkdir(mode=0o700)
    st=path.stat()
    if not path.is_dir() or st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077: raise StorageError('Private directories require owner-only access')


def sync(path):
    fd=os.open(path,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def write(path,value):
    safe(path,False)
    pending=path.with_name('.write-'+uuid.uuid4().hex)
    fd=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as out:
        json.dump(value,out);out.flush();os.fsync(out.fileno())
    os.replace(pending,path);sync(path.parent)


def fingerprint(path):
    safe(path,False);rows=[]
    for p in [path,*sorted(path.rglob('*'))] if path.is_dir() else [path]:
        st=p.lstat()
        if p.is_symlink() or st.st_uid!=os.getuid() or not (p.is_file() or p.is_dir()):raise StorageError('Unsafe settings input')
        rows.append([str(p.relative_to(path)),stat.S_IMODE(st.st_mode),hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None])
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def env_values(file):
    result={}
    if not file.exists():return result
    safe(file,False)
    for line in file.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if line.startswith('export '):line=line[7:]
        key,sep,value=line.partition('=')
        if not sep:raise StorageError('Malformed settings file')
        value=value.strip()
        if value.startswith(('"',"'")):
            if len(value)<2 or value[-1]!=value[0]:raise StorageError('Malformed settings quote')
            value=value[1:-1]
        result[key.strip()]=value
    return result


class Settings:
    def __init__(self,provider,source,prefix,account=None,account_key=None,fields=(),patterns=(),extra_keys=None,extra_files=()):
        self.provider=provider;self.source=Path(source);self.prefix=prefix;self.account=account;self.account_key=account_key;self.fields=fields;self.patterns=patterns;self.extra_keys=extra_keys or {};self.extra_files=extra_files
    @property
    def target(self):return safe(Path(os.environ.get('AGENT_HANDS_STATE_DIR',str(Path.home()/'.agent-hands')))/self.provider/'config')
    @property
    def marker(self):return self.source/'.runtime-settings.json'
    @property
    def pending(self):return self.target.parent/'.settings-migration.json'
    def selection(self,create=True):
        target=self.target
        if self.pending.exists():raise StorageError('Settings migration incomplete; inspect its private recovery record')
        if self.marker.exists() or self.marker.is_symlink():
            safe(self.marker,False)
            if json.loads(self.marker.read_text())!={'kind':'provider-settings-moved-v1','destination':str(target)}:raise StorageError('Settings selection differs from its migration marker')
            if not target.is_dir():raise StorageError('Migrated settings are missing; restore them instead of starting empty')
            if (self.source/'.env').exists() or (self.account and (self.source/self.account).exists()) or any(any(self.source.glob(pattern)) for pattern in self.patterns) or any(Path(src).exists() for src,_ in self.extra_files):raise StorageError('Legacy settings reappeared; reconcile before use')
        elif (self.source/'.env').exists() or (self.account and (self.source/self.account).exists()) or any(any(self.source.glob(pattern)) for pattern in self.patterns) or any(Path(src).exists() for src,_ in self.extra_files):raise StorageError('Legacy settings exist; run this provider runtime_state.py migrate explicitly')
        if create:private(target)
        return target
    def units(self):
        for key in [self.prefix+'_CONFIG_DIR',self.prefix+'_ENV_FILE',self.account_key,*self.extra_keys]:
            if key and os.environ.get(key):raise StorageError('Explicit settings selection is active; preserve it and prepare a targeted migration')
        if self.pending.exists() or self.marker.exists():raise StorageError('Existing migration requires inspection')
        env=env_values(self.source/'.env');names=['.env']
        def relative(value):
            p=Path(value)
            if not value or p.is_absolute() or '..' in p.parts or value in ('.','..'):raise StorageError('Nonrelative settings reference requires a targeted migration')
            return p
        if self.account:
            account=relative(env.get(self.account_key,self.account) if self.account_key else self.account)
            names.append(str(account));cfg=self.source/account
            if cfg.exists():
                safe(cfg,False)
                for item in json.loads(cfg.read_text()).get('accounts',[]):
                    for field,default in self.fields:
                        value=item.get(field,default)
                        if value is None:raise StorageError('Required credential reference is missing')
                        names.append(str(relative(value)))
        for key,default in self.extra_keys.items():names.append(str(relative(env.get(key,default))))
        for pattern in self.patterns:names.extend(str(p.relative_to(self.source)) for p in self.source.glob(pattern))
        units=[]
        for raw in dict.fromkeys(names):
            src=self.source/raw
            if not src.exists() and not src.is_symlink():continue
            safe(src,False);dst=self.target/raw;safe(dst)
            if dst.exists() or dst.is_symlink():raise StorageError('Destination collision; no merge allowed')
            units.append({'source':str(src),'destination':str(dst),'hash':fingerprint(src)})
        for src,dest in self.extra_files:
            src=Path(src);dst=self.target/dest
            if src.exists():
                safe(src,False);safe(dst)
                if dst.exists():raise StorageError('Destination collision')
                units.append({'source':str(src),'destination':str(dst),'hash':fingerprint(src)})
        sources=[Path(u['source']) for u in units]
        if any(a!=b and a in b.parents for a in sources for b in sources):raise StorageError('Overlapping migration inputs')
        return units
    def migrate(self,execute=False):
        units=self.units()
        if not units:return {'status':'no_legacy_settings','units':0}
        if not execute:return {'status':'settings_migration_preview','provider':self.provider,'units':len(units),'requires':'Stop all callers, including older installations. No sign-in or remote action occurs.'}
        private(self.target.parent)
        fd=os.open(self.target.parent/'.settings-migration.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);locks=[]
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            units=self.units()
            for unit in units:
                src=Path(unit['source']);dst=Path(unit['destination']);private(dst.parent)
                if src.stat().st_dev!=dst.parent.stat().st_dev:raise StorageError('Cross-filesystem migration is unsupported')
                if fingerprint(src)!=unit['hash']:raise StorageError('Input changed during preparation')
                if src.name == 'lock' or src.name.endswith('.lock'):
                    lock=os.open(src,os.O_RDWR|os.O_NOFOLLOW);locks.append(lock);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                if src.is_dir() and any(p.name=='lock' or p.name.endswith('.lock') for p in src.rglob('*')):raise StorageError('Nested recovery locks need owner-specific inspection')
            write(self.pending,{'kind':'provider-settings-migration-v1','units':units})
            for unit in units:
                src=Path(unit['source']);dst=Path(unit['destination'])
                if dst.exists():raise StorageError('Destination appeared during migration')
                os.rename(src,dst);sync(src.parent);sync(dst.parent)
                if fingerprint(dst)!=unit['hash']:raise StorageError('Moved settings differ; preserve recovery state')
            private(self.target)
            write(self.marker,{'kind':'provider-settings-moved-v1','destination':str(self.target)})
            self.pending.unlink();sync(self.pending.parent)
            return {'status':'settings_migrated','provider':self.provider,'verified_units':len(units),'remoteWrites':0}
        finally:
            for lock in locks:os.close(lock)
            os.close(fd)


def main(settings):
    p=argparse.ArgumentParser();p.add_argument('command',choices=['path','migrate']);p.add_argument('--execute',action='store_true');a=p.parse_args()
    try:
        if a.command=='path':print(settings.selection())
        else:print(json.dumps(settings.migrate(a.execute)))
    except Exception:raise SystemExit('ERROR: Private settings unavailable or migration requires inspection; preserve recovery records. No automatic merge, sign-in reset or retry.')
