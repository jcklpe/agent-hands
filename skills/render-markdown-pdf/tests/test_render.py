"""Exercise output preservation and resource boundaries with synthetic documents."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("markdown_renderer", SKILL / "scripts" / "render.py")
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RenderChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source.md"
        self.output = self.root / "result.pdf"
        self.theme = SKILL / "assets" / "themes" / "plain.css"
        self.source.write_text("# A synthetic document\n\nComplete body.\n")

    def render(self, roots=(), force=False):
        return renderer.render(self.source, self.output, self.theme, roots, force)

    def assert_preserved(self):
        self.assertEqual(self.output.read_bytes(), b"previous output")
        self.assertEqual(list(self.root.glob(".markdown-pdf-*")), [])

    def test_frontmatter_and_incomplete_block(self):
        self.assertEqual(renderer.strip_frontmatter("\ufeff---\r\nprivate: omitted\r\n...\r\n# Body\r\n"), "# Body\r\n")
        self.output.write_bytes(b"previous output")
        self.source.write_text("---\nprivate: incomplete\n")
        with self.assertRaisesRegex(ValueError, "Unclosed"):
            self.render(force=True)
        self.assert_preserved()

    def test_existing_output_requires_force_and_failed_resources_preserve_it(self):
        self.output.write_bytes(b"previous output")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.render()
        for resource in ("https://example.invalid/tracker.png", "file:///nonexistent.png", "missing.png", "data:image/png;base64,bm90YW5pbWFnZQ=="):
            with self.subTest(resource=resource):
                self.source.write_text(f"# Document\n\n![asset]({resource})\n")
                with self.assertRaises(Exception):
                    self.render(force=True)
                self.assert_preserved()

    def test_asset_grant_does_not_allow_symlink_escape_or_env_files(self):
        assets = self.root / "assets"
        assets.mkdir()
        outside = self.root / "outside.svg"
        outside.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
        (assets / "escape.svg").symlink_to(outside)
        (assets / ".env").write_text("SYNTHETIC_ONLY=not-a-secret\n")
        self.output.write_bytes(b"previous output")
        for resource in ("assets/escape.svg", "assets/.env"):
            with self.subTest(resource=resource):
                self.source.write_text(f"![asset]({resource})")
                with self.assertRaises(Exception):
                    self.render([assets], force=True)
                self.assert_preserved()

    def test_refuse_output_symlink_and_source_overwrite(self):
        original = self.source.read_bytes()
        self.output.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.render(force=True)
        self.assertEqual(self.source.read_bytes(), original)
        self.output.unlink()
        self.output.hardlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "input or theme"):
            self.render(force=True)
        self.assertEqual(self.source.read_bytes(), original)

    def test_relative_image_and_compact_theme_import(self):
        self.source = SKILL / "tests" / "fixtures" / "report.md"
        self.theme = SKILL / "assets" / "themes" / "compact.css"
        self.render([self.source.parent / "images"])
        self.assertTrue(self.output.read_bytes().startswith(b"%PDF-"))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob(".markdown-pdf-*")), [])

    def test_failed_pdf_write_cleans_partial_file_and_preserves_output(self):
        self.render()
        self.output.write_bytes(b"previous output")

        def interrupted_write(document, stream):
            stream.write(b"%PDF-partial")
            raise OSError("Synthetic write failure")

        with patch("weasyprint.document.Document.write_pdf", interrupted_write):
            with self.assertRaisesRegex(OSError, "Synthetic write failure"):
                self.render(force=True)
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
