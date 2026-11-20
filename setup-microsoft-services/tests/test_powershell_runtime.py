"""Exercise startup diagnostics and disposable caches without authentication."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "setup-microsoft-services/scripts/client.sh"


class PowerShellRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="agent-hands-pwsh-test-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.cache = self.root / "temp"
        self.cache.mkdir()
        self.log = self.root / "calls.jsonl"
        self.fake = self.root / "pwsh"
        self.fake.write_text('''#!/usr/bin/env python3
import json, os, sys, time
from pathlib import Path
cache = Path(os.environ['XDG_CACHE_HOME'])
assert cache.is_dir() and cache.stat().st_mode & 0o077 == 0
assert Path(os.environ['PSModuleAnalysisCachePath']).parent == cache / 'powershell'
with open(os.environ['PROBE_LOG'], 'a') as log:
    log.write(json.dumps({'cache': str(cache), 'args': sys.argv[1:]}) + '\\n')
(cache / 'cache-fixture').write_text('synthetic cache')
time.sleep(0.05)
mode = os.environ.get('FAKE_MODE', 'ready')
if mode == 'missing':
    print('AGENT_HANDS_GRAPH_MISSING'); sys.exit(2)
if mode in ('crash', 'false_success'):
    print('Unhandled startup failure')
    print('PRIVATE_DIAGNOSTIC_MUST_NOT_LEAK', file=sys.stderr)
    sys.exit(134 if mode == 'crash' else 0)
if '-File' in sys.argv:
    print('{"id":"synthetic-user"}')
else:
    print('AGENT_HANDS_GRAPH_READY')
'''.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
        self.fake.chmod(0o700)
        self.env = dict(os.environ, M365_PWSH_BIN=str(self.fake), TMPDIR=str(self.cache), PROBE_LOG=str(self.log))

    def run_command(self, command="_m365_powershell_ready", **overrides):
        env = dict(self.env, **overrides)
        return subprocess.run(["bash", "-c", 'source "$1"; ' + command, "probe", str(CLIENT)], env=env, text=True, capture_output=True, timeout=15)

    def assert_clean(self):
        self.assertEqual(list(self.cache.iterdir()), [])

    def test_ready_and_cache_cleanup(self):
        result = self.run_command()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assert_clean()

    def test_only_confirmed_missing_module_suggests_install(self):
        result = self.run_command(FAKE_MODE="missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not installed", result.stderr)
        self.assertIn("Install-Module", result.stdout)
        self.assert_clean()

    def test_crash_is_not_a_missing_module_or_raw_diagnostic(self):
        result = self.run_command(FAKE_MODE="crash")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exit 134", result.stderr)
        self.assertNotIn("Install-Module", result.stdout)
        self.assertNotIn("PRIVATE_DIAGNOSTIC", result.stdout + result.stderr)
        self.assert_clean()

    def test_zero_exit_without_readiness_marker_is_failure(self):
        result = self.run_command(FAKE_MODE="false_success")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exit 0", result.stderr)
        self.assertNotIn("PRIVATE_DIAGNOSTIC", result.stdout + result.stderr)
        self.assert_clean()

    def test_each_concurrent_process_has_its_own_cache(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.run_command(), range(4)))
        self.assertTrue(all(r.returncode == 0 for r in results))
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len({c["cache"] for c in calls}), 4)
        self.assert_clean()

    def test_provider_invocation_uses_same_isolation(self):
        result = self.run_command('_m365_powershell_invoke request /synthetic/request.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"id": "synthetic-user"})
        args = json.loads(self.log.read_text())["args"]
        self.assertIn("-NonInteractive", args)
        self.assertIn("-RequestPath", args)
        self.assert_clean()

    def test_checkout_temp_override_and_symlink_are_refused(self):
        self.env["TMPDIR"] = str(ROOT)
        result = self.run_command()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        link = self.root / "checkout-link"
        link.symlink_to(ROOT, target_is_directory=True)
        result = self.run_command(TMPDIR=str(link))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_other_git_checkout_and_missing_temp_have_no_fallback(self):
        other = self.root / "other"
        other.mkdir()
        (other / ".git").write_text("gitdir: /synthetic/module")
        result = self.run_command(TMPDIR=str(other))
        self.assertNotEqual(result.returncode, 0)
        result = self.run_command(TMPDIR=str(self.root / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
