import tempfile
import unittest
from pathlib import Path

from canvas_fixture import ORIGIN
from canvas_auth import CanvasError
from canvas_html import analyse, body_file, markdown_to_html
from canvas_export import date_text, zone_for


class HtmlTest(unittest.TestCase):
    def convert(self, value, **options):
        return analyse(value, ORIGIN, "courses", "123", **options)

    def test_fixed_corpus_and_style_only_hash_change(self):
        body, gaps, images, refs = self.convert('<h1>Title</h1><p>A <strong>bold</strong> word.</p>')
        self.assertEqual(body["markdown"], '# Title\n\nA **bold** word.\n')
        self.assertEqual((gaps, images, refs), ([], [], []))
        changed = self.convert('<h1 style="color:red">Title</h1><p>A <strong>bold</strong> word.</p>')[0]
        self.assertEqual(body["markdown"], changed["markdown"])
        self.assertNotEqual(body["html_sha256"], changed["html_sha256"])
        self.assertEqual(markdown_to_html('| A | B |\n|---|---|\n| 1 | 2 |\n').count('<table>'), 1)
        self.assertIn('<s>gone</s>', markdown_to_html('~~gone~~'))

    def test_images_and_explicit_embeds(self):
        html = '<img src="/courses/123/files/900/download?verifier=secret" alt="Diagram"><img src="/files/901" alt=""><img src="/files/902" width="32" height="20"><iframe src="https://media.example.net/1"></iframe>'
        body, gaps, images, refs = self.convert(html)
        self.assertIn('html', body)
        self.assertEqual([x["file_id"] for x in images], ["900"])
        self.assertEqual(refs, ["900","901","902"])
        self.assertIn('External content', body["markdown"])
        self.assertEqual(gaps[0]["kind"], "iframe")
        self.assertNotIn('verifier', body["html"])
        decorative = self.convert('<img src="/files/1" role="presentation">')[0]
        self.assertNotIn('html', decorative)
        self.assertIn('html', self.convert('<p>text</p>', include_html=True)[0])

    def test_external_images_and_other_course_images_are_gaps(self):
        _, gaps, images, _ = self.convert('<img src="https://assets.example.net/x.png" alt="Diagram"><img src="/courses/999/files/900" alt="Other">')
        self.assertEqual(images, [])
        self.assertEqual(len(gaps), 2)

    def test_body_file_is_utf8_and_has_no_size_cap(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'large.md'
            path.write_text('a' * (1024 * 1024 + 1))
            self.assertGreater(len(body_file(path)), 1024 * 1024)
            path.write_bytes(b'\xff')
            with self.assertRaises(CanvasError):
                body_file(path)

    def test_timezone_fallback_and_repeated_hour_keep_offset_and_source(self):
        zone = zone_for({"time_zone":"America/Chicago"}, "America/New_York")
        first = date_text('2026-11-01T06:30:00Z', zone)
        second = date_text('2026-11-01T07:30:00Z', zone)
        self.assertIn('01:30:00-05:00', first)
        self.assertIn('01:30:00-06:00', second)
        self.assertIn('2026-11-01T07:30:00Z', second)
        self.assertEqual(str(zone_for({"time_zone":"invalid"}, "America/New_York")), 'America/New_York')


if __name__ == '__main__':
    unittest.main()
