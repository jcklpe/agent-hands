"""Build a bounded, immutable multipart upload and its review fingerprint."""
import hashlib
import json
import mimetypes
from pathlib import Path
import sys


def prepare(alias, source, folder, name, work):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError('Source must be a regular non-symlink file')
    if not name or name.strip() != name or any(ord(c) < 32 for c in name) or '/' in name or '\\' in name:
        raise ValueError('Name must be a single safe filename')
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Upload supports at most 64 MiB; use another explicit transfer route for larger files')
    with source.open('rb') as stream:
        data = stream.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024:
        raise ValueError('Source grew beyond the 64 MiB upload bound')
    mime = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    plan = dict(account=alias, source=str(source.resolve()), folder=folder, name=name, mimeType=mime, size=len(data), sha256=hashlib.sha256(data).hexdigest(), md5=hashlib.md5(data).hexdigest())
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    boundary = 'drive-upload-' + fingerprint
    metadata = json.dumps(dict(name=name, mimeType=mime, parents=[folder])).encode()
    payload = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() + metadata + f'\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode())
    work = Path(work)
    (work / 'upload.body').write_bytes(payload)
    (work / 'upload.plan').write_text(json.dumps(plan))
    (work / 'upload.boundary').write_text(boundary)
    (work / 'upload.hash').write_text(fingerprint)
    return plan


if __name__ == '__main__':
    try:
        prepare(*sys.argv[1:])
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))
