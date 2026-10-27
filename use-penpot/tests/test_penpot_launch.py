"""Deterministic launch checks and OS-check harness tests; never invoke real ps."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

USE = Path(__file__).resolve().parents[1]
CONNECTOR = USE / 'scripts/penpot-mcp'
OS_CHECK = USE / 'tests/check-process-arguments.sh'
SYNTHETIC_KEY = 'synthetic-penpot-key-456'
SYNTHETIC_URL = 'https://127.0.0.1:9/mcp/stream?userToken=' + SYNTHETIC_KEY


class LaunchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='penpot-launch-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.capture = self.root / 'launch.json'
        self.ps_calls = self.root / 'ps-called'
        self.env = dict(os.environ, PENPOT_CONFIG_DIR=str(self.root / 'unconfigured'),
                        PENPOT_MCP_SERVER_URL=SYNTHETIC_URL, BASH_ENV='/dev/null',
                        PATH=str(self.bin)+':/usr/bin:/bin',
                        PENPOT_TEST_CAPTURE=str(self.capture), PENPOT_TEST_PS_CALLS=str(self.ps_calls))
        for name in ['PENPOT_ENV_FILE', 'PENPOT_PYTHON', 'PENPOT_TEST_LOCAL_URL']:
            self.env.pop(name, None)
        self.python_double = self.executable('python-double', '''import json,os,sys
from pathlib import Path
Path(os.environ['PENPOT_TEST_CAPTURE']).write_text(json.dumps({
    'argv':sys.argv[1:],
    'synthetic_url_received':os.environ.get('PENPOT_MCP_SERVER_URL') == '''+repr(SYNTHETIC_URL)+'''}))
''')
        # A marker protects against accidental process inspection in default/launch tests.
        self.executable('ps', '''import os,sys
from pathlib import Path
Path(os.environ['PENPOT_TEST_PS_CALLS']).touch()
sys.exit(126)
''')

    def executable(self, name, body):
        target = self.bin / name
        target.write_text('#!'+sys.executable+'\n'+body)
        target.chmod(0o755)
        return target

    def test_direct_and_uv_launches_keep_key_out_of_arguments(self):
        for route in ['direct', 'uv']:
            for mode in [[], ['--list-tools']]:
                with self.subTest(route=route, mode=mode):
                    env = dict(self.env)
                    if route == 'direct':
                        env['PENPOT_PYTHON'] = str(self.python_double)
                    else:
                        self.executable('uv', self.python_double.read_text().split('\n',1)[1])
                    run = subprocess.run(['/bin/bash', str(CONNECTOR), *mode], env=env, text=True, capture_output=True, timeout=5)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    captured = json.loads(self.capture.read_text())
                    expected = [str(USE / 'scripts/penpot_mcp_bridge.py'), *mode]
                    if route == 'uv':
                        expected = ['run', '--project', str(USE), '--locked', '--quiet', 'python', *expected]
                    self.assertEqual(captured['argv'], expected)
                    self.assertTrue(captured['synthetic_url_received'])
                    self.assertNotIn(SYNTHETIC_KEY, json.dumps(captured['argv']))
                    self.assertNotIn(SYNTHETIC_KEY, run.stdout+run.stderr)
                    self.assertFalse(self.ps_calls.exists())

    def test_os_check_requires_explicit_opt_in_without_calling_ps(self):
        run = subprocess.run(['/bin/bash', str(OS_CHECK)], env=self.env, text=True, capture_output=True, timeout=5)
        self.assertEqual(run.returncode, 77, run.stderr)
        self.assertIn('remains unverified', run.stdout)
        self.assertFalse(self.ps_calls.exists())
        self.assertFalse(self.capture.exists())

    def os_fixture(self, listing, status=0, leak_output=False):
        # This child is a controlled stand-in, not the real MCP bridge.
        waiting = self.executable('waiting-child', '''import sys
sys.stdin.read()
'''+('print('+repr(SYNTHETIC_KEY)+')\n' if leak_output else ''))
        self.executable('ps', '''import os,sys
from pathlib import Path
Path(os.environ['PENPOT_TEST_PS_CALLS']).touch()
assert sys.argv[1:]==['-axo','args=']
print('''+repr(listing)+''')
sys.exit('''+str(status)+''')
''')
        env = dict(self.env, PENPOT_PYTHON=str(waiting))
        run = subprocess.run(['/bin/bash', str(OS_CHECK), '--inspect-processes'], env=env, text=True, capture_output=True, timeout=10)
        self.assertTrue(self.ps_calls.exists(), 'Only the controlled ps double should be invoked')
        return run

    def test_simulated_denial_is_skipped_not_passed(self):
        run = self.os_fixture('', status=126)
        self.assertEqual(run.returncode, 77, run.stderr)
        self.assertIn('unavailable or denied (exit 126)', run.stdout)
        self.assertIn('remains unverified', run.stdout)
        self.assertNotIn('PASS', run.stdout)

    def test_simulated_leaks_still_fail(self):
        for listing, output in [(SYNTHETIC_KEY, False), ('safe arguments', True)]:
            with self.subTest(output=output):
                run = self.os_fixture(listing, leak_output=output)
                self.assertEqual(run.returncode, 1, run.stdout+run.stderr)
                self.assertIn('FAIL', run.stderr)
                self.assertNotIn(SYNTHETIC_KEY, run.stdout+run.stderr)

    def test_simulated_clean_inspection_passes(self):
        run = self.os_fixture('safe arguments')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('PASS OS process-argument', run.stdout)


if __name__ == '__main__':
    unittest.main()
