"""End-to-end native CLI tests against a stateful synthetic gh executable."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collaboration as runtime

ROOT = Path(__file__).resolve().parents[2]
HEAD, BASE, MERGE = "a" * 40, "b" * 40, "c" * 40


def fixture():
    issue = {"id": 101, "node_id": "ISSUE_1", "number": 1, "title": "Example issue", "body": "Original description", "state": "open", "state_reason": None, "user": {"id": 7, "login": "example-user"}, "labels": [{"name": "keep"}], "assignees": [{"login": "teammate"}], "html_url": "https://github.com/example-owner/example-project/issues/1"}
    issue["url"] = "https://api.github.com/repos/example-owner/example-project/issues/1"
    pr = {**copy.deepcopy(issue), "id": 102, "node_id": "PR_2", "number": 2, "title": "Example PR", "html_url": "https://github.com/example-owner/example-project/pull/2", "draft": True, "merged": False, "merge_commit_sha": None, "head": {"sha": HEAD, "ref": "feature", "repo": {"full_name": "example-owner/example-project"}}, "base": {"sha": BASE, "ref": "main", "repo": {"full_name": "example-owner/example-project"}}, "requested_reviewers": [], "requested_teams": [], "commits": 2, "changed_files": 1}
    pr.update(url="https://api.github.com/repos/example-owner/example-project/pulls/2", issue_url="https://api.github.com/repos/example-owner/example-project/issues/2")
    thread = {"id": "THREAD_1", "isResolved": False, "isOutdated": False, "viewerCanResolve": True, "viewerCanUnresolve": True, "path": "app.py", "line": 2, "diffSide": "RIGHT", "pullRequest": {"number": 2, "repository": {"nameWithOwner": "example-owner/example-project"}}, "comments": {"nodes": [{"id": "COMMENT_1", "databaseId": 77, "body": "Check this", "url": pr["html_url"], "author": {"login": "teammate"}, "commit": {"oid": HEAD}, "originalCommit": {"oid": HEAD}}], "pageInfo": {"hasNextPage": False, "endCursor": None}}}
    return {"actor": {"id": 7, "login": "example-user"}, "repository": {"id": 10, "full_name": "example-owner/example-project", "allow_merge_commit": True, "allow_squash_merge": True, "allow_rebase_merge": True}, "issues": {"1": issue}, "prs": {"2": pr}, "issue_comments": [], "reviews": [], "review_comments": [], "thread": thread, "files": [{"filename": "app.py", "patch": "@@ -1,2 +1,3 @@\n old\n+new\n end", "additions": 1, "deletions": 0}], "head": HEAD, "base": BASE, "merge_sha": MERGE, "commits": ["d" * 40, HEAD], "checks": [{"id": 123, "name": "unit", "status": "completed", "conclusion": "success"}], "statuses": []}


class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.checkout = self.work / "project"
        self.checkout.mkdir()
        subprocess.run(["git", "init", "-q", str(self.checkout)], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "remote", "add", "origin", "https://github.com/example-owner/example-project.git"], check=True)
        (self.checkout / ".gitignore").write_text(".agent-hands/\n")
        self.bin = self.work / "bin"
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text("#!" + sys.executable + "\n" + (ROOT / "setup-github/tests/fake_gh.py").read_text())
        gh.chmod(0o700)
        self.state_file = self.work / "state.json"
        self.state = fixture()
        self.save()
        self.config = self.work / "config"
        self.config.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("GH_", "GITHUB_"))}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ["PATH"], FAKE_GITHUB_STATE=str(self.state_file), GITHUB_PYTHON=sys.executable, GITHUB_CONFIG_DIR=str(self.config), PYTHONDONTWRITEBYTECODE="1", GH_CONFIG_DIR=str(self.config))

    def save(self):
        self.state_file.write_text(json.dumps(self.state))

    def load(self):
        self.state = json.loads(self.state_file.read_text())
        return self.state

    def call(self, command, *options, code=0, domain=None):
        if domain is None:
            domain = "issues" if "issue" in command else "pull-requests"
        path = ROOT / ("use-github-" + domain) / "scripts/github"
        result = subprocess.run(["bash", str(path), command, "--repo", "example-owner/example-project", "--actor", "example-user", "--json", "--project", str(self.checkout), *map(str, options)], cwd=self.checkout, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except ValueError:
            self.fail(result.stdout + result.stderr)

    def apply(self, command, *options, code=0):
        preview = self.call(command, *options)
        self.assertEqual(preview["outcome"], "preview")
        return self.call(command, *options, "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=code)

    def test_preview_never_writes_or_creates_journal(self):
        result = self.call("create-issue", "--title", "Literal title", "--body", "Literal $() and `text`\nNext")
        self.assertIn("fingerprint", result["plan"])
        self.assertFalse(self.load().get("mutations"))
        self.assertFalse((self.checkout / ".agent-hands").exists())

    def test_issue_create_executes_and_independently_reads_back(self):
        text = "Literal $() and `text`\n\nTrailing newline\n"
        source = self.work / "body.md"
        source.write_text(text)
        result = self.apply("create-issue", "--title", "New issue", "--body-file", source, "--label", "literal\\nlabel", "--assign-me")
        self.assertEqual(result["outcome"], "success")
        state = self.load()
        self.assertEqual(state["issues"]["3"]["body"], text)
        self.assertEqual(state["issues"]["3"]["labels"], [{"name": "literal\\nlabel"}])
        self.assertEqual(len(state["mutations"]), 1)
        self.assertTrue(any(c["method"] == "GET" and c["path"].endswith("/issues/3") for c in state["calls"]))

    def test_issue_edit_preserves_other_fields_and_explicit_clear(self):
        self.apply("edit-issue", "--issue", 1, "--body", "", "--add-label", "new")
        issue = self.load()["issues"]["1"]
        self.assertEqual(issue["body"], "")
        self.assertEqual(issue["title"], "Example issue")
        self.assertEqual(issue["labels"], [{"name": "keep"}, {"name": "new"}])
        self.assertEqual(issue["assignees"], [{"login": "teammate"}])

    def test_issue_close_reopen_and_known_noop(self):
        self.apply("close-issue", "--issue", 1, "--reason", "not_planned")
        second = self.apply("close-issue", "--issue", 1, "--reason", "not_planned")
        self.assertTrue(second["already_satisfied"])
        self.apply("reopen-issue", "--issue", 1)
        self.assertEqual(self.load()["issues"]["1"]["state"], "open")

    def test_stale_field_refuses_before_mutation(self):
        preview = self.call("edit-issue", "--issue", 1, "--body", "Replacement")
        self.load()["issues"]["1"]["body"] = "Someone else's edit"
        self.save()
        self.call("edit-issue", "--issue", 1, "--body", "Replacement", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_unrelated_issue_field_change_does_not_invalidate(self):
        preview = self.call("edit-issue", "--issue", 1, "--body", "Replacement")
        self.load()["issues"]["1"]["title"] = "New title"
        self.save()
        self.call("edit-issue", "--issue", 1, "--body", "Replacement", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"])
        self.assertEqual(self.load()["issues"]["1"]["title"], "New title")

    def test_actor_mismatch_and_missing_fingerprint_refuse(self):
        self.state["actor"] = {"id": 8, "login": "other-user"}
        self.save()
        self.call("create-issue", "--title", "New", code=2)
        self.assertFalse(self.load().get("mutations"))
        self.state["actor"] = {"id": 7, "login": "example-user"}
        self.save()
        self.call("create-issue", "--title", "New", "--execute", code=2)

    def test_ignored_journal_required(self):
        (self.checkout / ".gitignore").write_text("")
        result = self.apply("comment-issue", "--issue", 1, "--body", "Hello", code=2)
        self.assertIn("gitignored", result["message"])
        self.assertFalse(self.load().get("mutations"))

    def test_uncertain_comment_reconciles_without_resending(self):
        self.state["fault"] = {"method": "POST", "path": "/issues/1/comments", "mode": "after"}
        self.save()
        result = self.apply("comment-issue", "--issue", 1, "--body", "Hello", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        state = self.load()
        self.assertEqual(len(state["issue_comments"]), 1)
        state.pop("fault")
        self.save()
        recovery = self.call("recover", "--operation-id", result["operation_id"], domain="issues")
        self.assertEqual(recovery["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_intentional_repeated_comment_gets_new_id(self):
        self.apply("comment-issue", "--issue", 1, "--body", "Same text")
        self.apply("comment-issue", "--issue", 1, "--body", "Same text")
        self.assertEqual(len(self.load()["issue_comments"]), 2)

    def test_closed_issue_can_be_read_and_pr_is_not_issue(self):
        self.state["issues"]["1"]["state"] = "closed"
        self.save()
        self.assertEqual(self.call("read-issue", "--issue", 1)["issue"]["state"], "closed")
        self.call("read-issue", "--issue", 2, code=2)

    def test_pr_read_covers_diff_checks_reviews_threads(self):
        result = self.call("read-pr", "--pr", 2)
        self.assertIn("patch", result["files"][0])
        self.assertTrue(result["coverage"]["threads"]["complete"])
        self.assertEqual(result["revision"]["head"], HEAD)
        self.assertTrue(result["coverage"]["revision_stable"])

    def test_diff_byte_limit_and_selective_json(self):
        result = self.call("read-pr", "--pr", 2, "--fields", "files", "--diff-bytes", 1)
        self.assertNotIn("patch", result["files"][0])
        self.assertNotIn("pr", result)
        self.assertEqual(result["coverage"]["files"]["patches_omitted"], ["app.py"])

    def test_create_pr_from_published_refs_with_metadata(self):
        result = self.apply("create-pr", "--head", "another-feature", "--base", "main", "--expected-head", HEAD, "--title", "Prepared contribution", "--body", "Description", "--label", "new", "--assignee", "example-user", "--reviewer", "teammate")
        self.assertEqual(result["outcome"], "success")
        pr = self.load()["prs"]["3"]
        self.assertTrue(pr["draft"])
        self.assertEqual(pr["labels"], [{"name": "new"}])
        self.assertEqual(pr["requested_reviewers"], [{"login": "teammate"}])
        self.assertTrue(all(c["path"] for c in self.state["calls"]))

    def test_matching_open_pr_is_detected(self):
        self.call("create-pr", "--head", "feature", "--base", "main", "--expected-head", HEAD, "--title", "New", code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_pr_updates_readiness_metadata_and_retarget(self):
        self.apply("edit-pr", "--pr", 2, "--title", "Updated", "--ready", "--add-label", "new", "--add-reviewer", "teammate")
        pr = self.load()["prs"]["2"]
        self.assertEqual(pr["title"], "Updated")
        self.assertFalse(pr["draft"])
        self.assertEqual({v["name"] for v in pr["labels"]}, {"keep", "new"})
        self.apply("edit-pr", "--pr", 2, "--draft", "--base", "release")
        self.assertTrue(self.load()["prs"]["2"]["draft"])
        self.assertEqual(self.state["prs"]["2"]["base"]["ref"], "release")

    def test_pr_conversation_and_all_formal_review_events(self):
        self.apply("comment-pr", "--pr", 2, "--body", "Conversation")
        for event, state in (("COMMENT", "COMMENTED"), ("APPROVE", "APPROVED"), ("REQUEST_CHANGES", "CHANGES_REQUESTED")):
            self.apply("review-pr", "--pr", 2, "--expected-head", HEAD, "--event", event, "--body", "Review " + event)
            self.assertEqual(self.load()["reviews"][-1]["state"], state)
            self.assertEqual(self.state["reviews"][-1]["commit_id"], HEAD)

    def test_inline_anchor_and_reply(self):
        self.apply("inline-comment", "--pr", 2, "--expected-head", HEAD, "--path", "app.py", "--line", 2, "--body", "Inline feedback")
        comment = self.load()["review_comments"][0]
        self.apply("reply-review-comment", "--pr", 2, "--expected-head", HEAD, "--comment", comment["id"], "--body", "Follow-up")
        self.assertEqual(self.load()["review_comments"][-1]["in_reply_to_id"], comment["id"])
        self.call("inline-comment", "--pr", 2, "--expected-head", HEAD, "--path", "app.py", "--line", 999, "--body", "Bad anchor", code=2)

    def test_thread_parent_and_resolve_unresolve(self):
        value = self.call("read-thread", "--pr", 2, "--thread-id", "THREAD_1")
        self.assertTrue(value["coverage"]["complete"])
        self.apply("resolve-thread", "--pr", 2, "--expected-head", HEAD, "--thread-id", "THREAD_1")
        self.assertTrue(self.load()["thread"]["isResolved"])
        self.apply("unresolve-thread", "--pr", 2, "--expected-head", HEAD, "--thread-id", "THREAD_1")
        self.assertFalse(self.load()["thread"]["isResolved"])
        self.state["thread"]["pullRequest"]["number"] = 99
        self.save()
        self.call("read-thread", "--pr", 2, "--thread-id", "THREAD_1", code=2)

    def test_pr_close_reopen_and_reviewer_removal(self):
        self.apply("close-pr", "--pr", 2)
        self.assertEqual(self.load()["prs"]["2"]["state"], "closed")
        self.apply("reopen-pr", "--pr", 2)
        self.apply("edit-pr", "--pr", 2, "--add-reviewer", "teammate", "--add-team-reviewer", "reviewers")
        self.apply("edit-pr", "--pr", 2, "--remove-reviewer", "teammate", "--remove-team-reviewer", "reviewers", "--remove-label", "keep", "--remove-assignee", "teammate")
        pr = self.load()["prs"]["2"]
        for field in ("requested_reviewers", "requested_teams", "labels", "assignees"):
            self.assertEqual(pr[field], [])
        self.assertEqual(pr["state"], "open")

    def test_uncertain_creates_recover_by_exact_new_item(self):
        for domain, command, options in (("issues", "create-issue", ("--title", "Created issue")), ("pull-requests", "create-pr", ("--title", "Created PR", "--head", "another-feature", "--base", "main", "--expected-head", HEAD))):
            self.state = fixture()
            endpoint = "/issues" if domain == "issues" else "/pulls"
            self.state["fault"] = {"method": "POST", "path": endpoint, "mode": "after"}
            self.save()
            result = self.apply(command, *options, code=3)
            self.load().pop("fault")
            self.save()
            recovered = self.call("recover", "--operation-id", result["operation_id"], domain=domain)
            self.assertEqual(recovered["outcome"], "success")
            self.assertEqual(len(self.load()["mutations"]), 1)

    def test_create_pr_from_explicit_fork_has_no_implicit_publication(self):
        result = self.apply("create-pr", "--head-repo", "fork-owner/example-project", "--head", "feature", "--base", "main", "--expected-head", HEAD, "--title", "Fork contribution")
        self.assertEqual(result["outcome"], "success")
        self.assertEqual(self.load()["prs"]["3"]["head"]["repo"]["full_name"], "fork-owner/example-project")
        self.assertEqual(len(self.state["mutations"]), 1)
        self.assertEqual(self.state["mutations"][0]["path"], "repos/example-owner/example-project/pulls")

    def test_inline_left_side_range_and_invalid_range(self):
        self.apply("inline-comment", "--pr", 2, "--expected-head", HEAD, "--path", "app.py", "--side", "LEFT", "--start-line", 1, "--line", 2, "--body", "Range feedback")
        comment = self.load()["review_comments"][0]
        self.assertEqual(comment["start_side"], "LEFT")
        self.assertEqual(comment["start_line"], 1)
        self.call("inline-comment", "--pr", 2, "--expected-head", HEAD, "--path", "app.py", "--side", "LEFT", "--start-line", 3, "--line", 2, "--body", "Invalid range", code=2)

    def test_merge_is_separate_and_preserves_history(self):
        self.state["prs"]["2"]["draft"] = False
        self.save()
        assessment = self.call("assess-merge", "--pr", 2)
        self.assertFalse(assessment["merge_authorized"])
        self.call("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", code=2)
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed", "--preserve-history", "--require-path", "docs/active-spikes/example.md")
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(self.load()["prs"]["2"]["merged"])
        self.assertEqual(len(self.state["mutations"]), 1)
        sent = self.state["mutations"][0]["payload"]
        self.assertEqual(sent, {"sha": HEAD, "merge_method": "merge", "merge_action": "direct_merge", "bypass_rules": False})

    def test_queue_failed_checks_and_strategy_substitution_refuse(self):
        self.state["prs"]["2"]["draft"] = False
        self.state["rules"] = [{"type": "merge_queue", "parameters": {}}]
        self.save()
        options = ("--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed")
        self.call("merge-pr", *options, code=2)
        self.state["rules"] = []
        self.state["checks"][0]["conclusion"] = "failure"
        self.save()
        self.call("merge-pr", *options, code=2)
        self.state["checks"][0]["conclusion"] = "success"
        self.save()
        self.call("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "squash", "--integration-discussed", "--preserve-history", code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_head_change_refuses_review(self):
        self.call("review-pr", "--pr", 2, "--expected-head", "e" * 40, "--event", "APPROVE", "--body", "Review", code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_partial_create_does_not_retry_whole_sequence(self):
        self.state["fault"] = {"method": "PUT", "path": "/labels", "mode": "refuse"}
        self.save()
        result = self.apply("create-pr", "--head", "another-feature", "--base", "main", "--expected-head", HEAD, "--title", "Prepared", "--label", "new", code=3)
        self.assertTrue(result["partial"])
        self.assertEqual(len(self.load()["prs"]), 2)
        self.assertEqual(len(self.state["mutations"]), 2)

    def test_journal_has_digests_not_bodies_and_refuses_reuse(self):
        result = self.apply("comment-issue", "--issue", 1, "--body", "Unique private content")
        files = list((self.checkout / ".agent-hands/github").rglob("*.json"))
        self.assertEqual(len(files), 1)
        self.assertNotIn("Unique private content", files[0].read_text())
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        preview = self.call("comment-issue", "--issue", 1, "--body", "Unique private content")
        self.call("comment-issue", "--issue", 1, "--body", "Unique private content", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", result["operation_id"], code=2)

    def test_malformed_reads_and_graphql_errors_do_not_claim_completeness(self):
        self.state["fault"] = {"method": "GET", "path": "/pulls/2/files", "mode": "malformed"}
        self.save()
        result = self.call("read-pr", "--pr", 2)
        self.assertFalse(result["coverage"]["files"]["complete"])
        self.state["fault"] = {"method": "POST", "path": "graphql", "mode": "graphql-errors"}
        self.save()
        result = self.call("read-pr", "--pr", 2)
        self.assertFalse(result["coverage"]["threads"]["complete"])

    def test_external_state_directory_without_checkout(self):
        plain = self.work / "plain"
        plain.mkdir()
        location = self.work / "private-state"
        result = self.apply("comment-issue", "--issue", 1, "--body", "No checkout", "--project", plain, "--state-dir", location)
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(list(location.rglob("*.json")))

    def test_wrong_project_and_symlink_journal_refuse(self):
        subprocess.run(["git", "-C", str(self.checkout), "remote", "set-url", "origin", "https://github.com/other-owner/other-project.git"], check=True)
        self.apply("comment-issue", "--issue", 1, "--body", "Wrong checkout", code=2)
        subprocess.run(["git", "-C", str(self.checkout), "remote", "set-url", "origin", "https://github.com/example-owner/example-project.git"], check=True)
        outside = self.work / "outside"
        outside.mkdir()
        (self.checkout / ".agent-hands").symlink_to(outside, target_is_directory=True)
        self.apply("comment-issue", "--issue", 1, "--body", "Symlink", code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_uncertain_intent_cannot_be_retried_with_another_operation_id(self):
        self.state["fault"] = {"method": "POST", "path": "/issues/1/comments", "mode": "after"}
        self.save()
        self.apply("comment-issue", "--issue", 1, "--body", "Uncertain", code=3)
        self.load().pop("fault")
        self.save()
        self.apply("comment-issue", "--issue", 1, "--body", "Uncertain", code=3)
        self.assertEqual(len(self.load()["mutations"]), 1)
        self.apply("comment-issue", "--issue", 1, "--body", "Independent action")
        self.assertEqual(len(self.load()["mutations"]), 2)

    def test_ambiguous_recovery_requires_explicit_result(self):
        self.state["fault"] = {"method": "POST", "path": "/issues/1/comments", "mode": "after"}
        self.save()
        result = self.apply("comment-issue", "--issue", 1, "--body", "Same", code=3)
        state = self.load()
        state.pop("fault")
        repeated = copy.deepcopy(state["issue_comments"][0])
        repeated["id"] += 1
        state["issue_comments"].append(repeated)
        self.save()
        self.call("recover", "--operation-id", result["operation_id"], domain="issues", code=3)
        recovered = self.call("recover", "--operation-id", result["operation_id"], "--result-id", 5000, domain="issues")
        self.assertEqual(recovered["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_readback_failure_preserves_uncertainty(self):
        self.state["fault"] = {"method": "GET", "path": "/issues/comments/", "mode": "malformed"}
        self.save()
        result = self.apply("comment-issue", "--issue", 1, "--body", "Landed", code=3)
        self.assertEqual(result["steps"][0]["status"], "uncertain")
        self.assertEqual(len(self.load()["issue_comments"]), 1)

    def test_wrong_parent_in_comment_readback_is_uncertain(self):
        self.state["fault"] = {"method": "GET", "path": "/issues/comments/", "mode": "wrong-parent"}
        self.save()
        result = self.apply("comment-issue", "--issue", 1, "--body", "Exact parent", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.assertEqual(len(self.load()["issue_comments"]), 1)

    def test_conflicting_host_and_wrong_repository_identity_refuse(self):
        with self.assertRaises(runtime.Refusal):
            runtime.target("enterprise.invalid/example-owner/example-project", "github.com")
        self.state["repository"]["full_name"] = "other-owner/other-project"
        self.save()
        self.call("read-issue", "--issue", 1, code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_known_refusal_is_distinct_from_uncertain_send(self):
        self.state["fault"] = {"method": "POST", "path": "/issues/1/comments", "mode": "refuse"}
        self.save()
        result = self.apply("comment-issue", "--issue", 1, "--body", "Refused", code=1)
        self.assertEqual(result["outcome"], "failed")
        self.assertEqual(result["steps"][0]["status"], "refused")
        self.assertFalse(self.load()["issue_comments"])

    def test_bounded_comment_reads_report_incomplete_and_append_refuses(self):
        self.state["issue_comments"] = [{"id": n, "_number": 1, "body": "Existing", "user": self.state["actor"]} for n in range(100)]
        self.save()
        result = self.call("read-issue", "--issue", 1, "--item-limit", 1)
        self.assertFalse(result["coverage"]["comments"]["complete"])
        self.call("comment-issue", "--issue", 1, "--body", "More", "--item-limit", 1, code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_all_worktrees_share_one_journal_and_lock(self):
        self.git_commit("Initial")
        secondary = self.work / "worktree"
        subprocess.run(["git", "-C", str(self.checkout), "worktree", "add", "-q", "-b", "secondary", str(secondary)], check=True)
        context = SimpleNamespace(args=SimpleNamespace(project=str(self.checkout), state_dir=None), host="github.com", repo="example-owner/example-project", repository={"id": 10}, actor=self.state["actor"])
        primary = runtime.Journal(context)
        context.args.project = str(secondary)
        alternate = runtime.Journal(context)
        self.assertEqual(primary.directory, alternate.directory)
        with primary.locked():
            with self.assertRaisesRegex(runtime.Refusal, "holds"):
                with alternate.locked():
                    self.fail("Concurrent journal lock was acquired")

    def test_project_journal_handles_separate_git_metadata(self):
        checkout = self.work / "nested-project"
        metadata = self.work / "separate-git"
        subprocess.run(["git", "init", "-q", "--separate-git-dir", str(metadata), str(checkout)], check=True)
        subprocess.run(["git", "-C", str(checkout), "remote", "add", "origin", "https://github.com/example-owner/example-project.git"], check=True)
        (checkout / ".gitignore").write_text(".agent-hands/\n")
        result = self.apply("comment-issue", "--issue", 1, "--body", "Nested checkout", "--project", checkout)
        self.assertEqual(result["outcome"], "success")
        self.assertTrue(list((checkout / ".agent-hands/github").rglob("*.json")))
        self.assertFalse((metadata / ".agent-hands").exists())

    def git_commit(self, message):
        subprocess.run(["git", "-C", str(self.checkout), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.checkout), "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "commit", "-qm", message], check=True)
        return subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], text=True).strip()

    def test_history_verifier_uses_original_commits_from_real_git_graph(self):
        self.git_commit("Initial")
        initial_branch = subprocess.check_output(["git", "-C", str(self.checkout), "branch", "--show-current"], text=True).strip()
        subprocess.run(["git", "-C", str(self.checkout), "checkout", "-qb", "contribution"], check=True)
        source = self.checkout / "feature.txt"
        source.write_text("First\n")
        document = self.checkout / "docs/active-spikes/example.md"
        document.parent.mkdir(parents=True)
        document.write_text("Synthetic contribution reasoning.\n")
        first = self.git_commit("First atomic contribution")
        source.write_text("First\nSecond\n")
        head = self.git_commit("Second atomic contribution")
        subprocess.run(["git", "-C", str(self.checkout), "checkout", "-q", initial_branch], check=True)
        (self.checkout / "base.txt").write_text("Concurrent base work\n")
        base = self.git_commit("Advance base")
        subprocess.run(["git", "-C", str(self.checkout), "-c", "user.name=Synthetic", "-c", "user.email=synthetic@example.invalid", "merge", "--no-ff", "-qm", "Integrate", "contribution"], check=True)
        merged = subprocess.check_output(["git", "-C", str(self.checkout), "rev-parse", "HEAD"], text=True).strip()
        self.state.update(head=head, base=base, merge_sha=merged, commits=[first, head])
        self.state["prs"]["2"]["head"]["sha"] = head
        self.state["prs"]["2"]["base"]["sha"] = base
        self.state["prs"]["2"]["draft"] = False
        self.state["comparisons"] = {}
        self.state["tracked_files"] = subprocess.check_output(["git", "-C", str(self.checkout), "ls-tree", "-r", "--name-only", merged], text=True).splitlines()
        self.assertIn("docs/active-spikes/example.md", self.state["tracked_files"])
        for original in (first, head):
            subprocess.run(["git", "-C", str(self.checkout), "merge-base", "--is-ancestor", original, merged], check=True)
            ancestor = subprocess.check_output(["git", "-C", str(self.checkout), "merge-base", original, merged], text=True).strip()
            self.state["comparisons"][original + "..." + merged] = {"status": "ahead", "merge_base_commit": {"sha": ancestor}}
        self.save()
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", head, "--method", "merge", "--integration-discussed", "--preserve-history", "--require-path", "docs/active-spikes/example.md")
        self.assertEqual(result["outcome"], "success")

    def test_merge_pending_is_polled_without_repeating_mutation(self):
        self.state["prs"]["2"]["draft"] = False
        self.state["async_pending"] = True
        self.save()
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed")
        self.assertEqual(result["outcome"], "success")
        state = self.load()
        self.assertEqual(len(state["mutations"]), 1)
        self.assertTrue(any(c["method"] == "GET" and c["path"].endswith("/merge-async/merge-request-1") for c in state["calls"]))

    def test_selected_nonpreserving_methods_require_accepted_request_evidence(self):
        for method in ("squash", "rebase"):
            self.state = fixture()
            self.state["prs"]["2"]["draft"] = False
            self.state["async_pending"] = True
            self.save()
            result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", method, "--integration-discussed")
            self.assertEqual(result["outcome"], "success")
            self.assertEqual(self.load()["mutations"][0]["payload"]["merge_method"], method)

    def test_history_failure_after_merge_reports_uncertain(self):
        self.state["prs"]["2"]["draft"] = False
        self.state["missing_commit"] = self.state["commits"][0]
        self.save()
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed", "--preserve-history", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.assertTrue(self.load()["prs"]["2"]["merged"])

    def test_changed_base_in_result_is_not_claimed_as_discussed_integration(self):
        self.state["prs"]["2"]["draft"] = False
        self.state["integrated_base"] = "f" * 40
        self.save()
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed", code=3)
        self.assertIn("parents", result["message"])
        self.assertTrue(self.load()["prs"]["2"]["merged"])

    def test_selected_domain_runs_with_only_its_setup_sibling(self):
        for domain, command, options in (("issues", "read-issue", ("--issue", "1")), ("pull-requests", "read-pr", ("--pr", "2", "--fields", "pr"))):
            isolated = self.work / domain
            for skill in ("setup-github", "use-github-" + domain):
                shutil.copytree(ROOT / skill / "scripts", isolated / skill / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            result = subprocess.run(["bash", str(isolated / ("use-github-" + domain) / "scripts/github"), command, "--repo", "example-owner/example-project", "--json", *options], cwd=self.checkout, env=self.env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["outcome"], "success")

    def test_stale_state_is_rechecked_inside_execution_lock(self):
        preview = self.call("edit-issue", "--issue", 1, "--body", "Replacement")
        self.load()["race"] = {"path": "repos/example-owner/example-project/issues/1", "occurrence": 3}
        self.save()
        self.call("edit-issue", "--issue", 1, "--body", "Replacement", "--execute", "--expect", preview["plan"]["fingerprint"], "--operation-id", preview["operation_id"], code=2)
        self.assertFalse(self.load().get("mutations"))

    def test_private_body_preserves_crlf_and_empty_rest_body_is_semantic_empty(self):
        source = self.work / "body.md"
        source.write_bytes(b"Literal\r\nContent\r\n")
        self.apply("create-issue", "--title", "CRLF body", "--body-file", source)
        self.assertEqual(self.load()["issues"]["3"]["body"], "Literal\r\nContent\r\n")
        self.state["issues"]["1"]["body"] = None
        self.save()
        result = self.apply("edit-issue", "--issue", 1, "--body", "")
        self.assertTrue(result["already_satisfied"])

    def test_approve_can_have_no_comment_and_does_not_review_moved_head(self):
        self.apply("review-pr", "--pr", 2, "--expected-head", HEAD, "--event", "APPROVE")
        self.state = self.load()
        self.state["head_changes_after_send"] = True
        self.save()
        result = self.apply("review-pr", "--pr", 2, "--expected-head", HEAD, "--event", "COMMENT", "--body", "Revision review", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.state = self.load()
        self.state.pop("head_changes_after_send")
        self.save()
        self.call("recover", "--operation-id", result["operation_id"], code=3)

    def test_unchanged_pr_metadata_is_verified_noop(self):
        result = self.apply("edit-pr", "--pr", 2, "--add-label", "keep")
        self.assertTrue(result["already_satisfied"])
        self.assertFalse(self.load().get("mutations"))

    def test_automatic_deletion_stacks_and_unknown_rules_refuse_integration(self):
        for setting in ("delete", "stack", "unknown_rule"):
            self.state = fixture()
            self.state["prs"]["2"]["draft"] = False
            if setting == "delete":
                self.state["repository"]["delete_branch_on_merge"] = True
            elif setting == "stack":
                self.state["merge_metadata"] = {"stack": {"id": "STACK_1"}}
            else:
                self.state["rules"] = [{"type": "required_deployments", "parameters": {}}]
            self.save()
            self.call("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed", code=2)
            self.assertFalse(self.load().get("mutations"))

    def test_required_review_resolution_and_check_app_are_verified(self):
        self.state["prs"]["2"]["draft"] = False
        self.state["rules"] = [{"type": "pull_request", "parameters": {"required_approving_review_count": 1, "required_review_thread_resolution": True}}]
        self.save()
        options = ("--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed")
        self.call("merge-pr", *options, code=2)
        self.state = self.load()
        self.state["thread"]["isResolved"] = True
        self.state["rules"].append({"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "unit", "integration_id": 88}]}})
        self.save()
        self.call("merge-pr", *options, code=2)
        self.state = self.load()
        self.state["checks"][0]["app"] = {"id": 88}
        self.save()
        self.apply("merge-pr", *options)

    def test_pending_integration_remains_uncertain_then_recovers(self):
        self.state["prs"]["2"]["draft"] = False
        self.state.update(async_pending=True, async_still_pending=True)
        self.save()
        result = self.apply("merge-pr", "--pr", 2, "--expected-head", HEAD, "--method", "merge", "--integration-discussed", code=3)
        self.assertEqual(result["outcome"], "uncertain")
        self.assertEqual(len(self.load()["mutations"]), 1)
        self.state["prs"]["2"].update(merged=True, merge_commit_sha=MERGE)
        self.save()
        self.assertEqual(self.call("recover", "--operation-id", result["operation_id"])["outcome"], "success")
        self.assertEqual(len(self.load()["mutations"]), 1)

    def test_journal_failure_before_and_after_send_has_truthful_outcome(self):
        context = SimpleNamespace(args=SimpleNamespace(project=str(self.checkout), state_dir=None, execute=True, operation_id="journal-failure-1", expect="fingerprint", command="comment-issue"), host="github.com", repo="example-owner/example-project", repository={"id": 10}, actor=self.state["actor"], expected_actor="example-user")
        context.identity = lambda: context.actor
        context.prefix = "repos/example-owner/example-project"
        context.client = SimpleNamespace(writes_sent=0, get=lambda path: {"id": 10})
        def send(method, path, payload):
            context.client.writes_sent += 1
            return {"id": 123}
        context.client.request = send
        step = runtime.Step("comment", "POST", context.prefix + "/issues/1/comments", {"body": "Private text"}, {"kind": "rest", "path": context.prefix + "/issues/comments/123", "fields": ["body"], "digest": "digest"}, lambda response: {"kind": "rest", "path": "resource", "fields": [], "digest": "digest"})
        plan = {"fingerprint": "fingerprint", "changes": [{"body": "Private text"}]}
        original = runtime.Journal.write
        with patch.object(runtime.Journal, "write", side_effect=OSError("Synthetic pre-send disk failure")):
            with self.assertRaises(OSError):
                runtime.execute(context, plan, [step])
        self.assertEqual(context.client.writes_sent, 0)
        count = 0
        def interrupted(journal, record):
            nonlocal count
            count += 1
            if count >= 3:
                raise OSError("Synthetic disk failure")
            original(journal, record)
        with patch.object(runtime.Journal, "write", interrupted):
            result = runtime.execute(context, plan, [step])
        self.assertEqual(result["outcome"], "uncertain")
        self.assertEqual(context.client.writes_sent, 1)
        record = next((self.checkout / ".agent-hands/github").rglob("*.json"))
        self.assertEqual(json.loads(record.read_text())["steps"][0]["status"], "uncertain")

    def test_journal_failure_between_steps_reports_verified_partial(self):
        context = SimpleNamespace(args=SimpleNamespace(project=str(self.checkout), state_dir=None, execute=True, operation_id="between-steps-1", expect="fingerprint", command="edit-pr"), host="github.com", repo="example-owner/example-project", repository={"id": 10}, actor=self.state["actor"], expected_actor="example-user")
        context.identity = lambda: context.actor
        context.prefix = "repos/example-owner/example-project"
        context.client = SimpleNamespace(writes_sent=0, get=lambda path: {"id": 10})
        def send(method, path, payload):
            context.client.writes_sent += 1
            return {"id": 123}
        context.client.request = send
        proof = {"kind": "rest", "path": "resource", "fields": [], "digest": "digest"}
        step = runtime.Step("selected change", "PATCH", context.prefix + "/pulls/2", {"title": "Title"}, proof, lambda response: proof)
        original = runtime.Journal.write
        count = 0
        def interrupted(journal, record):
            nonlocal count
            count += 1
            if count == 5:
                raise OSError("Synthetic next-intent disk failure")
            original(journal, record)
        with patch.object(runtime.Journal, "write", interrupted):
            result = runtime.execute(context, {"fingerprint": "fingerprint", "changes": []}, [step, step])
        self.assertTrue(result["partial"])
        self.assertEqual(result["steps"][0]["status"], "verified")
        self.assertEqual(result["steps"][1]["status"], "not_sent")
        self.assertEqual(context.client.writes_sent, 1)


if __name__ == "__main__":
    if "--domain" in sys.argv:
        position = sys.argv.index("--domain")
        domain = sys.argv[position + 1]
        del sys.argv[position:position + 2]
        issue_names = {"test_actor_mismatch_and_missing_fingerprint_refuse", "test_closed_issue_can_be_read_and_pr_is_not_issue", "test_ignored_journal_required", "test_preview_never_writes_or_creates_journal", "test_stale_field_refuses_before_mutation", "test_unrelated_issue_field_change_does_not_invalidate", "test_uncertain_comment_reconciles_without_resending", "test_intentional_repeated_comment_gets_new_id", "test_journal_has_digests_not_bodies_and_refuses_reuse", "test_external_state_directory_without_checkout", "test_wrong_project_and_symlink_journal_refuse", "test_uncertain_intent_cannot_be_retried_with_another_operation_id", "test_ambiguous_recovery_requires_explicit_result", "test_readback_failure_preserves_uncertainty", "test_known_refusal_is_distinct_from_uncertain_send", "test_bounded_comment_reads_report_incomplete_and_append_refuses", "test_all_worktrees_share_one_journal_and_lock", "test_stale_state_is_rechecked_inside_execution_lock", "test_private_body_preserves_crlf_and_empty_rest_body_is_semantic_empty", "test_project_journal_handles_separate_git_metadata", "test_wrong_parent_in_comment_readback_is_uncertain", "test_conflicting_host_and_wrong_repository_identity_refuse"}
        names = unittest.defaultTestLoader.getTestCaseNames(CollaborationTests)
        selected = [name for name in names if (name.startswith("test_issue_") or name in issue_names) == (domain == "issues") and name not in {"test_selected_domain_runs_with_only_its_setup_sibling", "test_uncertain_creates_recover_by_exact_new_item"}]
        suite = unittest.TestSuite(CollaborationTests(name) for name in selected)
        sys.exit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
    unittest.main()
