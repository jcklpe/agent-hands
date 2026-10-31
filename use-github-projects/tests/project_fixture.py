"""Isolated native CLI fixtures; no credentials or live services are used."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "use-github-projects/scripts/github"


def fixture():
    owner = {"id": "OWNER_1", "login": "example-owner"}
    meta = {"id": "PROJECT_1", "number": 1, "title": "Example project", "url": "https://github.com/orgs/example-owner/projects/1", "owner": owner, "closed": False, "public": False, "updatedAt": "revision-0", "viewerCanUpdate": True}
    options = [{"id": "WAITING", "name": "Waiting", "color": "GRAY", "description": ""}, {"id": "READY", "name": "Ready", "color": "GREEN", "description": ""}, {"id": "DONE", "name": "Done", "color": "PURPLE", "description": ""}]
    fields = [{"id": "FIELD_STATUS", "name": "Status", "dataType": "SINGLE_SELECT", "options": options}, {"id": "FIELD_NOTE", "name": "Note", "dataType": "TEXT"}]
    view = {"id": "VIEW_1", "number": 1, "name": "Board", "layout": "BOARD_LAYOUT", "filter": "is:open", "updatedAt": "revision-0", "project": {"id": "PROJECT_1"}, "visible": ["FIELD_NOTE", "FIELD_STATUS"]}
    item = {"id": "ITEM_1", "content": {"__typename": "Issue", "id": "ISSUE_1", "number": 1, "repository": {"nameWithOwner": "example-owner/example-project"}}, "fieldValueByName": {"__typename": "ProjectV2ItemFieldSingleSelectValue", "optionId": "WAITING", "name": "Waiting", "field": {"id": "FIELD_STATUS"}}}
    return {"actor": {"id": 7, "login": "example-user"}, "repository": {"id": 10, "node_id": "REPO_1", "full_name": "example-owner/example-project"}, "owners": {"example-owner": {"node_id": "OWNER_1", "login": "example-owner", "type": "Organization"}, "other-owner": {"node_id": "OWNER_2", "login": "other-owner", "type": "User"}}, "projects": {"PROJECT_1": {"meta": meta, "fields": fields, "views": [view], "workflows": [{"id": "WORKFLOW_1", "number": 1, "name": "Auto-close issue", "enabled": True}], "repositories": [], "items": [item]}}, "calls": [], "mutations": []}


class ProjectFixture:
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="projects-collaboration-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(self.checkout)], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "remote", "add", "origin", "https://github.com/example-owner/example-project.git"], check=True)
        (self.checkout / ".gitignore").write_text("/.github/project-collaboration/\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        executable = self.bin / "gh"
        executable.write_text("#!" + sys.executable + "\n" + (Path(__file__).parent / "fake_gh.py").read_text())
        executable.chmod(0o700)
        self.state = fixture()
        self.state_path = self.root / "state.json"
        self.save()
        self.config = self.root / "config"
        self.config.mkdir()
        (self.config / "github-repos.json").write_text(json.dumps({"repos": [{"alias": "example", "owner": "example-owner", "repo": "example-project", "projects": [{"number": 1, "name": "example"}]}]}))
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GH_", "GITHUB_"))}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"], PROJECT_TEST_STATE=str(self.state_path), GITHUB_PYTHON=sys.executable, GITHUB_CONFIG_DIR=str(self.config), GH_CONFIG_DIR=str(self.config), PYTHONDONTWRITEBYTECODE="1")

    @property
    def project(self):
        return self.state["projects"]["PROJECT_1"]

    def save(self):
        self.state_path.write_text(json.dumps(self.state))

    def load(self):
        self.state = json.loads(self.state_path.read_text())
        return self.state

    def json_file(self, name, value):
        p = self.root / name
        p.write_text(json.dumps(value))
        return p

    def call(self, command, *options, code=0, selector=True, repo="example-owner/example-project"):
        args = ["bash", str(CLI), command, "--repo", repo, "--actor", "example-user", "--project", str(self.checkout), "--json"]
        if selector:
            args += ["--project-id", "PROJECT_1"]
        args += list(map(str, options))
        result = subprocess.run(args, text=True, capture_output=True, cwd=self.checkout, env=self.env)
        if code is None:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def apply(self, command, *options, code=0, **kwargs):
        preview = self.call(command, *options, **kwargs)
        self.assertEqual(preview["outcome"], "preview")
        return self.call(command, *options, "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=code, **kwargs)

    def assert_no_writes(self):
        self.assertFalse(self.load()["mutations"])
