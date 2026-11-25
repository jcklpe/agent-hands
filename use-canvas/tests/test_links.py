"""The offline link inventory over a synthetic export; it never opens an address."""
import json
import unittest

from canvas_fixture import ORIGIN
import test_cli

BODY = f"""<p>Read <a href="https://publisher.example/book?id=9&amp;token=secret"><em>Example</em> chapter</a> and <a href="/courses/123/files/900/download?verifier=ephemeral">the slides</a>.</p>
<ul><li><a href="/courses/123/assignments/456">the task</a></li><li><a href="https://proxy.example/login?url=https://journal.example/a">article</a></li></ul>
<table><tr><th>Week</th><th>Link</th></tr><tr><td>1</td><td><a href="/courses/123/external_tools/5">tool</a></td></tr></table>
<p><a href="mailto:teacher@example.edu">mail</a> <a href="#top">top</a> <a href="/courses/123/files/999">missing file</a> <a href="{ORIGIN}/about/1">profile</a></p>"""


class LinksTest(unittest.TestCase):
    run_cli = test_cli.CliTest.run_cli

    def setUp(self):
        test_cli.CliTest.setUp(self)
        self.fixture.data["pages"][0]["body"] = BODY
        self.fixture.data["items"].append({"id": "199", "type": "ExternalUrl", "title": "Example publisher", "external_url": "https://publisher.example/chapter", "position": 9})
        self.export = self.root / "snapshot"
        code, _, error = self.run_cli("export", "example", "--output", str(self.export))
        self.assertEqual(code, 0, error)
        self.before = {p: p.read_bytes() for p in self.export.rglob("*") if p.is_file()}
        self.sent = len(self.fixture.sent)

    def links(self, *args):
        code, output, error = self.run_cli("links", "--export", str(self.export), "--json", *args)
        self.assertEqual(code, 0, error)
        return json.loads(output)["courses"][0]

    def test_every_body_link_is_listed_with_its_category_and_place(self):
        rows = {r["title"]: r for r in self.links()["links"] if r["source"]["kind"] == "page"}
        self.assertEqual({t: r["category"] for t, r in rows.items()}, {"Example chapter": "external", "the slides": "canvas_file", "the task": "canvas_assignment", "article": "external", "tool": "external_tool", "mail": "other", "missing file": "canvas_file", "profile": "canvas_other"})
        self.assertEqual(rows["article"]["url"], "https://proxy.example/login?url=https%3A%2F%2Fjournal.example%2Fa")
        self.assertNotIn("secret", json.dumps(rows))
        self.assertNotIn("ephemeral", json.dumps(rows))
        self.assertEqual((rows["the slides"]["file"]["in_export"], rows["missing file"]["file"]), (True, {"id": "999", "in_export": False}))
        self.assertEqual((rows["article"]["source"]["title"], rows["article"]["source"]["modules"]), ("Overview", ["Week 1"]))

    def test_module_links_and_the_elsewhere_filter(self):
        course = self.links("--elsewhere", "--course", "123")
        self.assertEqual({r["category"] for r in course["links"]}, {"external", "external_tool"})
        module = next(r for r in course["links"] if r["title"] == "Example publisher")
        self.assertEqual((module["url"], module["source"]["kind"], module["source"]["modules"]), ("https://publisher.example/chapter", "module_item", ["Week 1"]))
        self.assertGreater(course["counts"]["canvas_file"], 0)
        self.assertEqual(course["coverage"]["pages"], "complete")

    def test_it_reads_only_the_export_and_needs_no_account(self):
        (self.root / "canvas-accounts.json").unlink()
        self.env.unlink()
        first = self.links()
        self.assertEqual(first, self.links())
        self.assertEqual(len(self.fixture.sent), self.sent)
        self.assertEqual({p: p.read_bytes() for p in self.export.rglob("*") if p.is_file()}, self.before)
        readable = self.run_cli("links", "--export", str(self.export))[1]
        self.assertIn("A link is not the reading it points to", readable)

    def test_unrecognized_exports_and_courses_are_refused(self):
        self.assertEqual(self.run_cli("links", "--export", str(self.root))[0], 1)
        self.assertEqual(self.run_cli("links", "--export", str(self.root / "absent"))[0], 1)
        self.assertEqual(self.run_cli("links", "--export", str(self.export), "--course", "999")[0], 1)


if __name__ == "__main__":
    unittest.main()
