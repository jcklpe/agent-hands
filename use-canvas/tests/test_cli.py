import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

from canvas_fixture import CanvasFixture, ORIGIN, TOKEN
import canvas
from canvas_auth import CanvasError
from canvas_history import History


class CliTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        self.env=self.root/'.env'
        self.env.write_text('CANVAS_TOKEN_EXAMPLE='+TOKEN+'\n')
        self.env.chmod(0o600)
        self.config=self.root/'canvas-accounts.json'
        self.config.write_text(json.dumps({'accounts':[{'alias':'example','base_url':ORIGIN,'user_id':'1001','token_env':'CANVAS_TOKEN_EXAMPLE','courses':['123']}]}))
        environment=patch.dict(os.environ,{'CANVAS_CONFIG_DIR':str(self.root),'CANVAS_HISTORY_DIR':str(self.root/'history')},clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.fixture=CanvasFixture()

    def run_cli(self,*args):
        output,error=io.StringIO(),io.StringIO()
        with redirect_stdout(output),redirect_stderr(error):
            code=canvas.main(list(args),transport=self.fixture,downloader=self.fixture.download,now=dt.datetime(2026,10,30,tzinfo=dt.timezone.utc))
        self.assertNotIn(TOKEN,output.getvalue()+error.getvalue())
        return code,output.getvalue(),error.getvalue()

    def test_export_verify_courses_and_history(self):
        code,output,error=self.run_cli('export','example','--output',str(self.root/'snapshot'),'--json')
        self.assertEqual(code,0,error)
        self.assertTrue(json.loads(output)['published'])
        self.assertEqual(self.run_cli('courses','example')[0],0)
        self.assertEqual(self.run_cli('verify','example')[0],0)
        sent=len(self.fixture.sent)
        code,output,error=self.run_cli('history','example','--kind','export','--course','123','--json')
        self.assertEqual(code,0,error)
        self.assertEqual(len(json.loads(output)),1)
        self.assertEqual(len(self.fixture.sent),sent)
        self.assertNotIn('<p>',output)

    def test_failed_export_exit_status_history_and_previous_preservation(self):
        path=self.root/'snapshot'
        self.run_cli('export','example','--output',str(path))
        before=(path/'index.json').read_bytes()
        self.fixture.failures['/api/v1/courses/123/assignments']=(500,{})
        code,output,_=self.run_cli('export','example','--output',str(path),'--json')
        self.assertEqual(code,1)
        self.assertFalse(json.loads(output)['published'])
        self.assertEqual((path/'index.json').read_bytes(),before)
        records=list(History(self.root/'history').rows())
        self.assertEqual(records[-1]['outcome'],'not_published')

    def test_history_failure_warns_but_read_succeeds(self):
        with patch.object(History,'record',side_effect=OSError('synthetic unavailable history')):
            code,output,error=self.run_cli('courses','example')
        self.assertEqual(code,0)
        self.assertIn('WARNING',error)
        self.assertIn('Example Course',output)

    def test_identity_mismatch_stops_before_course_read(self):
        data=json.loads(self.config.read_text())
        data['accounts'][0]['user_id']='2002'
        self.config.write_text(json.dumps(data))
        code,_,error=self.run_cli('export','example','--output',str(self.root/'snapshot'))
        self.assertEqual(code,1)
        self.assertIn('identity_mismatch',error)
        self.assertEqual([p for p,_ in self.fixture.sent],['/api/v1/users/self'])

    def test_help_works_without_config_or_conversion_packages(self):
        result=subprocess.run([sys.executable,'-S',str(Path(canvas.__file__)),'--help'],env={'CANVAS_CONFIG_DIR':'/missing'},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('download-file',result.stdout)

    def test_history_queries_need_no_token_or_network(self):
        self.env.write_text('')
        self.assertEqual(self.run_cli('history','example','--json')[0],0)
        self.assertEqual(self.fixture.sent,[])


if __name__=='__main__':
    unittest.main()
