"""Bounded inline-image inspection and private, revision-guarded local-file repair."""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import struct
import tempfile
import urllib.parse
import urllib.request
import uuid
import zipfile

DOCS = 'https://docs.googleapis.com/v1/documents/'
DRIVE = 'https://www.googleapis.com/drive/v3/files'
MAX_BYTES = 20 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dimensions(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return 'png', *struct.unpack('>II', data[16:24])
    if data[:6] in (b'GIF87a', b'GIF89a') and len(data) >= 10:
        return 'gif', *struct.unpack('<HH', data[6:10])
    if data.startswith(b'\xff\xd8'):
        stream = io.BytesIO(data[2:])
        while True:
            marker = stream.read(1)
            if not marker:
                break
            if marker != b'\xff':
                continue
            while marker == b'\xff':
                marker = stream.read(1)
            if not marker or marker in (b'\xd9', b'\xda'):
                break
            if marker == b'\x01' or 0xD0 <= marker[0] <= 0xD8:
                continue
            length = stream.read(2)
            if len(length) != 2:
                break
            size = struct.unpack('>H', length)[0]
            if marker[0] in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                head = stream.read(5)
                if len(head) == 5:
                    h, w = struct.unpack('>HH', head[1:])
                    return 'jpg', w, h
                break
            if size < 2:
                break
            stream.seek(size - 2, 1)
    raise ValueError('Unsupported or malformed image; supply a valid PNG, JPEG or GIF')


def check_content_uri(uri):
    parsed = urllib.parse.urlsplit(uri)
    host = parsed.hostname or ''
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443) or not (host == 'googleusercontent.com' or host.endswith('.googleusercontent.com')):
        raise ValueError('Expected a Google-supplied HTTPS image content URI; source links are not fetched')


class ContentRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_content_uri(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Authenticated image-import request redirected; no credential was forwarded')


def content_bytes(uri):
    check_content_uri(uri)
    with urllib.request.build_opener(ContentRedirect()).open(uri, timeout=30) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Image exceeds the 20 MiB operation limit')
    dimensions(data)
    return data


def private_directory(path):
    if path.is_symlink():
        raise ValueError('Private output directory must not be a symlink')
    path = path.resolve(strict=True)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or (hasattr(os, 'getuid') and info.st_uid != os.getuid()):
        raise ValueError('Use an owner-only private directory (mode 0700)')
    for parent in (path, *path.parents):
        marker = parent / '.git'
        if marker.exists() or marker.is_symlink():
            raise ValueError('Private image outputs and recovery records must be outside Git checkouts')
    env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
    probe = subprocess.run(['git', '-C', str(path), 'rev-parse', '--git-dir'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
        raise ValueError('Private image outputs and recovery records must be outside Git checkouts')
    return path


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def save_record(path, record):
    data = json.dumps(record, indent=2).encode()
    fd, temporary = tempfile.mkstemp(prefix='.image-record-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_source(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('Image source must be a regular file')
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Image source exceeds 20 MiB')
    return data


def private_folder(folder, token, api):
    fields = 'id,mimeType,trashed,driveId,ownedByMe,capabilities(canAddChildren),permissions(type,role,deleted)'
    result = api['api_json']('GET', DRIVE + '/' + folder + '?supportsAllDrives=true&fields=' + fields, token)
    permissions = result.get('permissions')
    if result.get('id') != folder or result.get('trashed') or result.get('driveId') or result.get('ownedByMe') is not True or result.get('mimeType') != 'application/vnd.google-apps.folder' or not result.get('capabilities', {}).get('canAddChildren'):
        raise ValueError('Temporary folder must be an owned, writable My Drive folder')
    if not isinstance(permissions, list) or len(permissions) != 1 or permissions[0].get('type') != 'user' or permissions[0].get('role') != 'owner' or permissions[0].get('deleted'):
        raise ValueError('Temporary folder must have owner-only sharing; incomplete or shared permissions are refused')


def safe_error(exc):
    return re.sub(r'https?://[^\s\"\'<>]+', '[redacted URL]', str(exc))


def inline_images(document):
    result = []
    def elements(items, tab_id, objects):
        for item in items or []:
            for part in item.get('paragraph', {}).get('elements', []):
                ident = part.get('inlineObjectElement', {}).get('inlineObjectId')
                if not ident:
                    continue
                obj = objects.get(ident, {})
                embedded = obj.get('inlineObjectProperties', {}).get('embeddedObject', {})
                image = embedded.get('imageProperties')
                if image is None:
                    continue
                if not isinstance(part.get('startIndex'), int) or part.get('endIndex') != part['startIndex'] + 1:
                    raise ValueError('Inline image has an ambiguous range; no repair can be constructed')
                result.append({'object_id': ident, 'tab_id': tab_id, 'index': part['startIndex'], 'size': embedded.get('size', {}), 'image_properties': image, 'suggested': any(k.startswith('suggested') and v for node in (part, obj, embedded) for k, v in node.items())})
            for row in item.get('table', {}).get('tableRows', []):
                for cell in row.get('tableCells', []):
                    elements(cell.get('content'), tab_id, objects)
    def tabs(items):
        for tab in items:
            body = tab.get('documentTab', {})
            elements(body.get('body', {}).get('content'), tab.get('tabProperties', {}).get('tabId', ''), body.get('inlineObjects', document.get('inlineObjects', {})))
            tabs(tab.get('childTabs', []))
    if document.get('tabs'):
        tabs(document['tabs'])
    else:
        elements(document.get('body', {}).get('content'), '', document.get('inlineObjects', {}))
    return result


def snapshot(document, text_fn):
    rows, blobs = [], {}
    for obj in inline_images(document):
        uri = obj['image_properties'].get('contentUri')
        data = content_bytes(uri) if uri else None
        ext, width, height = dimensions(data) if data is not None else (None, None, None)
        key = (obj['tab_id'], obj['index'])
        if key in blobs:
            raise ValueError('Duplicate image placement index')
        blobs[key] = data
        rows.append({k: obj[k] for k in ('object_id', 'tab_id', 'index', 'size', 'suggested')} | {'sha256': digest(data) if data is not None else None, 'unavailable': data is None, 'pixel_width': width, 'pixel_height': height, 'format': ext, 'source_uri_sha256': digest(obj['image_properties']['sourceUri'].encode()) if obj['image_properties'].get('sourceUri') else None})
    text = [(t['id'], t['text']) for t in text_fn(document)]
    return {'revision': document.get('revisionId'), 'images': rows, 'text_sha256': digest(json.dumps(text, ensure_ascii=False).encode())}, blobs


def command_images(args, api):
    token = api['access_token']()
    doc = api['get_document'](api['document_id_from'](args), token)
    state, blobs = snapshot(doc, api['document_tabs'])
    if args.out_dir:
        path = Path(args.out_dir)
        if not path.exists():
            path.mkdir(mode=0o700)
        path = private_directory(path)
        for row in state['images']:
            if row['unavailable']:
                continue
            name = f"image-{row['index']}-{row['object_id']}.{row['format']}"
            if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
                raise ValueError('Unsafe image identifier; download refused')
            target = path / name
            write_private(target, blobs[(row['tab_id'], row['index'])])
            row['path'] = str(target)
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print('Revision:', state['revision'])
        for row in state['images']:
            print(f"{row['object_id']} tab={row['tab_id']} index={row['index']} pixels={row['pixel_width']}x{row['pixel_height']} sha256={row['sha256']}")
    return 0


def prepare(document, source_plan, alias, folder, text_fn):
    if not document.get('revisionId'):
        raise ValueError('Document revision is unavailable; image writes require a revision guard')
    if not isinstance(source_plan, list) or not 1 <= len(source_plan) <= 20:
        raise ValueError('Plan must contain 1 to 20 explicit image replacements')
    images = inline_images(document)
    plan, used, total = [], set(), 0
    for item in source_plan:
        if not isinstance(item, dict) or set(item) - {'object_id', 'tab_id', 'image_file', 'width_pt'}:
            raise ValueError('Unknown image-plan fields')
        matches = [x for x in images if x['object_id'] == item.get('object_id') and ('tab_id' not in item or x['tab_id'] == item['tab_id'])]
        if len(matches) != 1:
            raise ValueError('Target must resolve to exactly one existing inline image; inspect with docs images')
        obj = matches[0]
        if obj['object_id'] in used or obj['suggested']:
            raise ValueError('Duplicate target or pending image suggestion; resolve it before repair')
        props = obj['image_properties']
        def nonzero(value):
            return any(nonzero(v) for v in value.values()) if isinstance(value, dict) else bool(value)
        effects = {k: v for k, v in props.items() if k not in ('contentUri', 'sourceUri') and nonzero(v)}
        if effects:
            raise ValueError('Target has image effects/cropping; reinsertion cannot preserve them')
        source = Path(item.get('image_file', ''))
        if source.is_symlink() or not source.is_file():
            raise ValueError('Image source must be an explicit regular file, not a symlink')
        data = read_source(source)
        total += len(data)
        if total > MAX_BYTES:
            raise ValueError('Combined image sources exceed 20 MiB')
        ext, w, h = dimensions(data)
        if w <= 0 or h <= 0 or w * h > 25_000_000:
            raise ValueError('Image dimensions must be positive and at most 25 megapixels')
        width = item.get('width_pt')
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not 1 <= width <= 1000:
            raise ValueError('Provide an explicit width_pt between 1 and 1000')
        plan.append({'object_id': obj['object_id'], 'tab_id': obj['tab_id'], 'index': obj['index'], 'image_file': str(source.resolve()), 'sha256': digest(data), 'format': ext, 'pixel_width': w, 'pixel_height': h, 'width_pt': width, 'height_pt': round(width * h / w, 6)})
        used.add(obj['object_id'])
    public = {'account': alias, 'document_id': document.get('documentId'), 'revision': document['revisionId'], 'temporary_folder': folder, 'replacements': plan, 'text_sha256': digest(json.dumps([(x['id'], x['text']) for x in text_fn(document)], ensure_ascii=False).encode())}
    return public, digest(json.dumps(public, sort_keys=True, separators=(',', ':')).encode())


def carrier_docx(plan):
    buf = io.BytesIO()
    rels, body, types = [], [], set()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for i, item in enumerate(plan, 1):
            ext = item['format']; types.add(ext)
            name = f'image{i}.{ext}'
            data = read_source(Path(item['image_file']))
            if digest(data) != item['sha256']:
                raise ValueError('Source image changed before import; prepare a fresh preview')
            z.writestr('word/media/' + name, data)
            rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
            cx, cy = int(item['width_pt'] * 12700), int(item['height_pt'] * 12700)
            body.append(f'<w:p><w:r><w:drawing><wp:inline><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{i}" name="Image {i}"/><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="{i}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="rId{i}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>')
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' + ''.join(f'<Default Extension="{e}" ContentType="image/{"jpeg" if e == "jpg" else e}"/>' for e in sorted(types)) + '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/_rels/document.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(rels) + '</Relationships>')
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>' + ''.join(body) + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')
    return buf.getvalue()


def import_carrier(data, folder, token):
    boundary = 'docs-images-' + uuid.uuid4().hex
    meta = {'name': 'Temporary Docs image repair ' + uuid.uuid4().hex, 'mimeType': 'application/vnd.google-apps.document', 'parents': [folder]}
    payload = ('--' + boundary + '\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n' + json.dumps(meta) + '\r\n--' + boundary + '\r\nContent-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n').encode() + data + ('\r\n--' + boundary + '--\r\n').encode()
    request = urllib.request.Request('https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,mimeType,parents', data=payload, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'multipart/related; boundary=' + boundary}, method='POST')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=60) as response:
        result = json.load(response)
    if not result.get('id') or result.get('mimeType') != meta['mimeType'] or result.get('parents') != [folder]:
        raise RuntimeError('Temporary import response is uncertain; inspect the explicit folder before retrying')
    return result['id']


def build_requests(plan, uris, location_fn, range_fn):
    if len(plan) != len(uris):
        raise ValueError('Every replacement needs exactly one imported image URI')
    requests = []
    for item, uri in sorted(zip(plan, uris), key=lambda pair: (pair[0]['tab_id'], -pair[0]['index'])):
        check_content_uri(uri)
        if len(uri) > 2048:
            raise ValueError('Google image content URI exceeds the Docs API 2 KiB limit')
        tab, index = item['tab_id'], item['index']
        requests.append({'deleteContentRange': {'range': range_fn(tab, index, index + 1)}})
        requests.append({'insertInlineImage': {'uri': uri, 'location': location_fn(tab, index), 'objectSize': {'width': {'magnitude': item['width_pt'], 'unit': 'PT'}, 'height': {'magnitude': item['height_pt'], 'unit': 'PT'}}}})
    return requests


def verify(before, after, plan, expected, expected_uri_hashes=None):
    if len(plan) != len(expected):
        raise RuntimeError('Expected image inventory is incomplete')
    if before['text_sha256'] != after['text_sha256']:
        raise RuntimeError('Image repair readback changed document text; inspect before any retry')
    old = {(x['tab_id'], x['index']): x for x in before['images']}
    new = {(x['tab_id'], x['index']): x for x in after['images']}
    if old.keys() != new.keys():
        raise RuntimeError('Image placement inventory changed unexpectedly')
    targets = {(x['tab_id'], x['index']): digest(data) for x, data in zip(plan, expected)}
    for key, image in new.items():
        target = next((x for x in plan if (x['tab_id'], x['index']) == key), None)
        if target and 'width_pt' in target:
            for axis in ('width', 'height'):
                size = image.get('size', {}).get(axis, {})
                if size.get('unit') != 'PT' or not isinstance(size.get('magnitude'), (int, float)) or not math.isclose(size['magnitude'], target[axis + '_pt'], abs_tol=0.01):
                    raise RuntimeError('Replacement display size was not verified; inspect before retrying')
        wanted = targets.get(key, old[key]['sha256'])
        if image['sha256'] != wanted:
            # Google may re-encode an inserted image. Its independently returned source identity and intrinsic dimensions must still match the exact private import dispatched for this target.
            uri_match = key in targets and expected_uri_hashes and image.get('source_uri_sha256') == expected_uri_hashes.get(key)
            size_match = target and (image.get('pixel_width'), image.get('pixel_height')) == (target['pixel_width'], target['pixel_height'])
            if not (uri_match and size_match):
                raise RuntimeError('Image-byte/source-identity readback mismatch; preserve the operation record and inspect before retrying')
        if key not in targets and image['object_id'] != old[key]['object_id']:
            raise RuntimeError('An unaffected image object changed')


def command_replace(args, api):
    token = api['access_token'](); ident = api['document_id_from'](args)
    document = api['get_document'](ident, token)
    raw = json.loads(Path(args.plan).read_text())
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.temporary_folder):
        raise ValueError('An explicit Drive temporary-folder ID is required')
    plan, fingerprint = prepare(document, raw, os.environ.get('GOOGLE_DOCS_ALIAS', ''), args.temporary_folder, api['document_tabs'])
    private_folder(args.temporary_folder, token, api)
    print(json.dumps(plan, indent=2)); print('Preview SHA-256:', fingerprint)
    if not args.execute:
        print('DRY RUN: no document or temporary import created. Execution reinserts only these inline images; new object IDs replace the old ones.')
        return 0
    if args.expect != fingerprint:
        raise ValueError('Preview fingerprint changed or --expect is missing; obtain and inspect a fresh preview')
    if os.environ.get('GOOGLE_DOCS_IMAGE_IMPORT_ENABLED') != 'true':
        raise ValueError('Local-image import requires the selected account drive.write_enabled opt-in; no authorization is expanded automatically')
    if not args.record:
        raise ValueError('--record is required for execution and uncertain-write recovery')
    path = Path(args.record)
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ValueError('Record must be a new file in an existing private directory')
    path = private_directory(path.parent) / path.name
    before, blobs = snapshot(document, api['document_tabs'])
    record = {'document_id': ident, 'preview_sha256': fingerprint, 'plan': plan, 'before': before, 'status': 'prepared'}
    write_private(path, json.dumps(record, indent=2).encode())
    backup = path.with_suffix(path.suffix + '.images'); backup.mkdir(mode=0o700)
    for index, x in enumerate(plan['replacements'], 1):
        data = blobs[(x['tab_id'], x['index'])]
        if data is not None:
            write_private(backup / f'image-{index}.bin', data)
    def save():
        save_record(path, record)
    carrier = None
    try:
        private_folder(args.temporary_folder, token, api)
        record['status'] = 'import_dispatching'; save()
        carrier = import_carrier(carrier_docx(plan['replacements']), args.temporary_folder, token)
        record['temporary_document_id'] = carrier; record['status'] = 'imported'; save()
        imported = api['get_document'](carrier, token)
        images = inline_images(imported)
        if len(images) != len(plan['replacements']):
            raise RuntimeError('Temporary import image count differs; target was not changed')
        uris = [x['image_properties']['contentUri'] for x in images]
        expected = [content_bytes(uri) for uri in uris]
        for item, data in zip(plan['replacements'], expected):
            _, w, h = dimensions(data)
            if (w, h) != (item['pixel_width'], item['pixel_height']):
                raise RuntimeError('Private import changed image dimensions; target was not changed')
        live = api['get_document'](ident, token)
        if live.get('revisionId') != document['revisionId']:
            raise RuntimeError('Target revision changed during private import; prepare a fresh preview')
        requests = build_requests(plan['replacements'], uris, api['_location'], api['_range'])
        expected_uri_hashes = {(x['tab_id'], x['index']): digest(uri.encode()) for x, uri in zip(plan['replacements'], uris)}
        record['expected_import_images'] = [{'tab_id': x['tab_id'], 'index': x['index'], 'import_sha256': digest(data), 'source_uri_sha256': digest(uri.encode())} for x, data, uri in zip(plan['replacements'], expected, uris)]
        record['status'] = 'dispatching'; save()
        api['api_json']('POST', DOCS + ident + ':batchUpdate', token, {'requests': requests, 'writeControl': {'requiredRevisionId': document['revisionId']}})
        after, _ = snapshot(api['get_document'](ident, token), api['document_tabs'])
        record['after'] = after; save()
        verify(before, after, plan['replacements'], expected, expected_uri_hashes)
        record['status'] = 'verified'; save()
    except Exception as exc:
        record['error'] = safe_error(exc); save()
        raise RuntimeError(safe_error(exc)) from None
    finally:
        if carrier:
            try:
                result = api['api_json']('PATCH', DRIVE + '/' + carrier + '?supportsAllDrives=true&fields=id,trashed', token, {'trashed': True})
                if result.get('id') != carrier or not result.get('trashed'):
                    raise RuntimeError('Temporary import trash readback did not confirm cleanup')
                record['temporary_import_trashed'] = True
            except Exception as exc:
                record['cleanup_error'] = safe_error(exc)
            save()
    if not record.get('temporary_import_trashed'):
        raise RuntimeError('Target verified, but temporary-import cleanup is incomplete; use the recorded ID for recovery')
    print('Verified image source identities/dimensions, unchanged text/unaffected images, and temporary-import cleanup. Record:', path)
    return 0
