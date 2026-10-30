"""One streamed multipart upload request, with no Canvas credentials or automatic redirects."""
import http.client
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from canvas_auth import CanvasError, Response, TIMEOUT_SECONDS, MAX_JSON_BYTES, USER_AGENT, _NoRedirect, _header_map
from canvas_export import checked_download_url


class Multipart:
    def __init__(self, parameters, path, name, content_type):
        if not isinstance(parameters, dict) or not all(isinstance(k,str) and isinstance(v,str) for k,v in parameters.items()):
            raise CanvasError('upload_invalid','Canvas upload parameters must be text fields')
        if any(c in name + content_type + ''.join(parameters) for c in '\r\n'):
            raise CanvasError('upload_invalid','Multipart names and content type cannot contain line breaks')
        self.path=Path(path)
        self.boundary='canvas-'+uuid.uuid4().hex
        quote=lambda value: value.replace('\\','\\\\').replace('"','\\"')
        chunks=[]
        for key,value in parameters.items():
            chunks.append((f'--{self.boundary}\r\nContent-Disposition: form-data; name="{quote(key)}"\r\n\r\n'+value+'\r\n').encode())
        chunks.append((f'--{self.boundary}\r\nContent-Disposition: form-data; name="file"; filename="{quote(name)}"\r\nContent-Type: {content_type}\r\n\r\n').encode())
        self.prefix=b''.join(chunks)
        self.suffix=f'\r\n--{self.boundary}--\r\n'.encode()
        self.length=len(self.prefix)+self.path.stat().st_size+len(self.suffix)

    def __iter__(self):
        yield self.prefix
        with self.path.open('rb') as source:
            while block:=source.read(1024*1024):
                yield block
        yield self.suffix


def send_upload(url, parameters, path, name, content_type, opener=None):
    checked_download_url(url)
    body=Multipart(parameters,path,name,content_type)
    request=urllib.request.Request(url,data=body,method='POST',headers={'Content-Type':'multipart/form-data; boundary='+body.boundary,'Content-Length':str(body.length),'User-Agent':USER_AGENT})
    opener=opener or urllib.request.build_opener(_NoRedirect())
    try:
        try:
            response=opener.open(request,timeout=TIMEOUT_SECONDS)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            raw=response.read(MAX_JSON_BYTES+1)
            if len(raw)>MAX_JSON_BYTES:
                raise CanvasError('too_large','Upload service response exceeded the JSON response limit')
            return Response(response.status,_header_map(response.headers),raw)
    except (urllib.error.URLError,OSError,http.client.HTTPException):
        raise CanvasError('network_error','Upload failed before a complete response arrived; inspect before retrying') from None
