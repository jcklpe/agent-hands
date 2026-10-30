import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from canvas_fixture import TOKEN
from canvas_write_fixture import WriteFixture,NOW
from canvas_auth import CanvasError
from canvas_history import History
from canvas_upload import Multipart,send_upload
from canvas_write import run_write
import canvas


class UploadTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.fixture=WriteFixture()
        self.file=self.root/'file.txt';self.file.write_bytes(b'file content')
        self.history=History(self.root/'history',now=NOW)

    def args(self,command,*options): return canvas.parser().parse_args([command,'example',*options])

    def run_command(self,args): return run_write(self.fixture.reader(),args,self.history,NOW,self.fixture.upload_sender)

    def execute(self,command,*options):
        args=self.args(command,*options);plan,code=self.run_command(args)
        self.assertEqual(code,0)
        args.execute=True;args.expect=plan['preview_hash']
        return self.run_command(args)

    def test_course_upload_and_streaming_parameters(self):
        result,code=self.execute('upload-file','--course','123','--file',str(self.file),'--folder','80')
        self.assertEqual(code,0,result)
        self.assertEqual(result['writes_sent'],3)
        self.assertIn('file.id',result['target_ids'])
        self.assertEqual(self.fixture.writes[0][2]['on_duplicate'],'rename')
        upload=self.fixture.uploads[0]
        raw=b''.join(upload['chunks'])
        self.assertIn(b'opaque-key',raw);self.assertIn(b'synthetic-signature',raw)
        self.assertGreater(raw.find(b'name="file"'),raw.find(b'name="signature"'))
        self.assertNotIn(TOKEN.encode(),raw)

    def test_filename_collision_replace_id_and_explicit_rename(self):
        base=['--course','123','--file',str(self.file),'--name','diagram.png']
        with self.assertRaises(CanvasError):self.run_command(self.args('upload-file',*base))
        with self.assertRaises(CanvasError):self.run_command(self.args('upload-file',*base,'--replace','999'))
        result,code=self.execute('upload-file',*base,'--replace','900')
        self.assertEqual(code,0,result);self.assertEqual(result['target_ids']['file.id'],'900')
        result,code=self.execute('upload-file',*base,'--rename-on-conflict')
        self.assertEqual(code,0,result)
        self.assertTrue(any(f['display_name'].startswith('renamed-') for f in self.fixture.data['files']))

    def test_changed_local_file_refuses_before_any_write(self):
        args=self.args('upload-file','--course','123','--file',str(self.file))
        plan,_=self.run_command(args);self.file.write_bytes(b'changed')
        args.execute=True;args.expect=plan['preview_hash']
        with self.assertRaises(CanvasError):self.run_command(args)
        self.assertEqual(self.fixture.writes,[])

    def test_storage_confirmation_origin_and_size_fail_as_uncertain(self):
        for kind in ('off_origin','bad_size'):
            with self.subTest(kind=kind):
                self.fixture=WriteFixture();setattr(self.fixture,kind,True)
                result,code=self.execute('upload-file','--course','123','--file',str(self.file))
                self.assertEqual(code,3,result)
                self.assertEqual(len(self.fixture.writes),1)
                if kind=='off_origin':self.assertFalse(any('create_success' in p for p,_ in self.fixture.sent))

    def test_group_and_personal_upload_contexts(self):
        for flag,value in (('--group','77'),('--personal',None)):
            options=[flag]+([value] if value else [])+['--file',str(self.file)]
            result,code=self.execute('upload-file',*options)
            self.assertEqual(code,0,result)
        self.assertTrue(any(p=='/api/v1/groups/77/files' for _,p,_ in self.fixture.writes))
        self.assertTrue(any(p=='/api/v1/users/self/files' for _,p,_ in self.fixture.writes))

    def test_file_submission_uses_submission_upload_endpoint(self):
        self.fixture.data['assignments'][0]['submission_types']=['online_upload']
        result,code=self.execute('submit-assignment','--course','123','--assignment','456','--file',str(self.file))
        self.assertEqual(code,0,result)
        self.assertEqual(self.fixture.writes[0][1],'/api/v1/courses/123/assignments/456/submissions/self/files')
        self.assertEqual(self.fixture.submission['attempt'],2)
        self.assertEqual(self.fixture.submission['attachments'][0]['display_name'],'file.txt')

    def test_real_upload_request_has_no_auth_and_never_follows_redirects(self):
        class Response(io.BytesIO):
            status=302
            def __init__(self):
                super().__init__(b'');self.headers=Message();self.headers['Location']='https://example.instructure.com/api/v1/files/900/create_success'
        class Opener:
            def __init__(self):self.requests=[]
            def open(self,request,timeout):
                self.requests.append(request)
                self.assertions(request)
                return Response()
            def assertions(self,request):
                assert request.get_header('Authorization') is None
                assert not isinstance(request.data,bytes)
                data=b''.join(request.data)
                assert len(data)==int(request.get_header('Content-length'))
        opener=Opener()
        response=send_upload('https://storage.example.net/upload',{'key':'literal&value','signature':'a+b'},self.file,'file.txt','text/plain',opener)
        self.assertEqual(response.status,302);self.assertEqual(len(opener.requests),1)
        for url in ('http://storage.example.net/x','https://user@storage.example.net/x'):
            with self.assertRaises(CanvasError):send_upload(url,{},self.file,'file.txt','text/plain',opener)
        self.assertEqual(len(opener.requests),1)

    def test_large_multipart_file_is_not_read_whole(self):
        self.file.write_bytes(b'x'*(3*1024*1024))
        packet=Multipart({'key':'opaque'},self.file,'large.bin','application/octet-stream')
        lengths=[len(chunk) for chunk in packet]
        self.assertEqual(sum(lengths),packet.length)
        self.assertGreater(len(lengths),3)
        self.assertLessEqual(max(lengths),1024*1024)

    def test_group_pages_create_edit_revert(self):
        html=self.root/'body.html';html.write_text('<p>Group page.</p>')
        for command,options in (('create-page',['--title','New group page','--body-file',str(html)]),('edit-page',['--page','790','--body-file',str(html)]),('revert-page',['--page','790','--revision','12'])):
            result,code=self.execute(command,'--group','77',*options)
            self.assertEqual(code,0,result)
        self.assertTrue(all('/groups/77/pages' in p for _,p,_ in self.fixture.writes))

    def test_optional_uploaded_content_verification(self):
        import hashlib
        args=self.args('upload-file','--course','123','--file',str(self.file),'--verify-content')
        plan,_=self.run_command(args);args.execute=True;args.expect=plan['preview_hash']
        def downloader(client,metadata,output):
            content=self.file.read_bytes();Path(output).write_bytes(content)
            return {'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
        result,code=run_write(self.fixture.reader(),args,self.history,NOW,self.fixture.upload_sender,downloader)
        self.assertEqual(code,0,result)

    def test_relative_confirmation_and_201_are_supported(self):
        sender=self.fixture.upload_sender
        def relative(*args):
            response=sender(*args)
            response.headers['location']=response.headers['location'].replace('https://example.instructure.com','')
            response.status=201
            return response
        self.fixture.upload_sender=relative
        result,code=self.execute('upload-file','--course','123','--file',str(self.file))
        self.assertEqual(code,0,result)

    def test_real_urllib_streams_to_loopback_without_credentials(self):
        import http.server,threading,urllib.request
        from canvas_auth import _NoRedirect
        received=[]
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append((dict(self.headers),self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(302);self.send_header('Location','https://example.instructure.com/api/v1/files/900/create_success');self.end_headers()
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            base='http://127.0.0.1:'+str(server.server_address[1])
            class LoopbackOpener:
                def open(self,request,timeout):
                    rewritten=urllib.request.Request(base+'/upload',data=request.data,headers=dict(request.header_items()),method='POST')
                    return urllib.request.build_opener(_NoRedirect()).open(rewritten,timeout=timeout)
            response=send_upload('https://storage.example.net/upload',{'key':'opaque','signature':'synthetic'},self.file,'file.txt','text/plain',LoopbackOpener())
            self.assertEqual(response.status,302);self.assertEqual(len(received),1)
            headers,body=received[0]
            self.assertNotIn('Authorization',headers);self.assertNotIn('Transfer-Encoding',headers)
            self.assertGreater(body.find(b'name="file"'),body.find(b'name="signature"'))
            self.assertIn(b'file content',body)
        finally:
            server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
