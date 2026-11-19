"""Runtime diagnostics stay credential-free and never replay a service operation."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

AUTH = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime", AUTH / "scripts/runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class RuntimeChecks(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.env = dict(os.environ, GOOGLE_CONFIG_DIR=str(self.root), GOOGLE_PYTHON=sys.executable,
                        GOOGLE_ENV_FILE=str(self.root / "empty.env"), GOOGLE_ACCOUNTS_PATH=str(self.root / "invalid-accounts.json"))
        (self.root / "empty.env").write_text("")
        (self.root / "invalid-accounts.json").write_text("PRIVATE_SENTINEL_NOT_JSON")
        self.env["GOOGLE_ACCESS_TOKEN"] = "PRIVATE_TOKEN_SENTINEL"
        self.operation = self.root / "operation with spaces.py"
        self.receipt = self.root / "called.json"
        self.operation.write_text("import json, os, sys\nfrom pathlib import Path\np=Path(os.environ['TEST_RECEIPT'])\nassert not p.exists(), 'operation replayed'\np.write_text(json.dumps(sys.argv[1:]))\nprint('operation output')\nprint(os.environ.get('TEST_ERROR', ''), file=sys.stderr)\nsys.exit(int(os.environ.get('TEST_EXIT', '0')))\n")
        self.env["TEST_RECEIPT"] = str(self.receipt)

    def authorize(self, *args):
        return subprocess.run(["/bin/bash", str(AUTH / "scripts/authorize"), *args], env=self.env, capture_output=True, text=True)

    def invoke(self, *args):
        return subprocess.run(["/bin/bash", "-c", 'set -eu; source "$1"; shift; _google_python "$@"', "test", str(AUTH / "scripts/client.sh"), str(AUTH), str(self.operation), *args], env=self.env, capture_output=True, text=True)

    def test_runtime_report_does_not_read_accounts_or_tokens(self):
        result = self.authorize("runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Python: " + ".".join(map(str, sys.version_info[:3])), result.stdout)
        self.assertIn("Runner: GOOGLE_PYTHON", result.stdout)
        self.assertNotIn("PRIVATE", result.stdout + result.stderr)
        self.assertNotIn(str(self.root), result.stdout + result.stderr)
        self.assertFalse(self.receipt.exists())

    def test_versions_fail_before_operation_with_actual_version(self):
        # The diagnostic itself intentionally parses on older Python to explain the unsupported runtime.
        launcher = self.root / "older-python"
        launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c " + shlex.quote("import runpy, sys; sys.version_info=(3,9,6); sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')") + ' "$@"\n')
        launcher.chmod(0o700)
        self.env["GOOGLE_PYTHON"] = str(launcher)
        result = self.invoke("selected-target")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Unsupported Python 3.9.6", result.stderr)
        self.assertIn("Python 3.11+", result.stderr)
        self.assertIn("preflight failed before", result.stderr)
        self.assertFalse(self.receipt.exists())

    def test_minimum_boundary_and_quiet_success(self):
        for version, expected in [((3, 10, 99), 2), ((3, 11, 0), 0), ((3, 13, 1), 0)]:
            out, err = io.StringIO(), io.StringIO()
            with patch.object(runtime.sys, "version_info", version), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(runtime.main(["--check"]), expected)
            self.assertEqual(out.getvalue(), "")
            if expected == 0:
                self.assertEqual(err.getvalue(), "")

    def test_operation_arguments_output_and_failure_are_preserved_once(self):
        self.env.update(TEST_EXIT="7", TEST_ERROR="Original DNS/service failure")
        args = ["argument with spaces", "literal'quote", "$(not-executed)", "--exact-target"]
        result = self.invoke(*args)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(result.stdout, "operation output\n")
        self.assertEqual(result.stderr, "Original DNS/service failure\n")
        self.assertEqual(json.loads(self.receipt.read_text()), args)
        self.assertNotIn("PRIVATE", result.stdout + result.stderr)

    def test_missing_executable_does_not_fall_back(self):
        self.env["GOOGLE_PYTHON"] = str(self.root / "missing-python")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("preflight failed before", result.stderr)
        self.assertFalse(self.receipt.exists())

    def fake_uv(self, fail=False):
        shim = self.root / "uv"
        script = "#!/bin/sh\nexec " + shlex.quote(sys.executable) + " -c "
        code = "import subprocess,sys; assert sys.argv[1:3]==['run','--project']; assert sys.argv[4]=='python'; "
        if fail:
            code += "print('error: Failed to initialize cache: Permission denied',file=sys.stderr); sys.exit(29)"
        else:
            code += "sys.exit(subprocess.call([sys.executable,*sys.argv[5:]]))"
        shim.write_text(script + shlex.quote(code) + ' "$@"\n')
        shim.chmod(0o700)
        self.env.pop("GOOGLE_PYTHON", None)
        self.env["PATH"] = str(self.root) + os.pathsep + self.env.get("PATH", "")

    def test_uv_route_and_report_keep_existing_project_selection(self):
        self.fake_uv()
        result = self.authorize("runtime")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Runner: uv", result.stdout)
        result = self.invoke("exact-argument")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.receipt.read_text()), ["exact-argument"])

    def test_uv_cache_failure_is_preserved_without_operation_or_retry(self):
        self.fake_uv(fail=True)
        result = self.invoke()
        self.assertEqual(result.returncode, 29)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "error: Failed to initialize cache: Permission denied\n")
        self.assertFalse(self.receipt.exists())

    def test_runtime_rejects_account_argument_without_auth(self):
        result = self.authorize("runtime", "example")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("takes no account", result.stderr)
        self.assertNotIn("PRIVATE", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
