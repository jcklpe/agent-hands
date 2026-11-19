import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('planner_comments', pathlib.Path(__file__).parents[1] / 'scripts/comments.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

class ContentTests(unittest.TestCase):
    def test_markdown_link_is_real_safe_html(self):
        prepared = c.prepare('Read [A & B](https://example.test/?a=1&b="two")')
        self.assertIn('<a href="https://example.test/?a=1&amp;b=&quot;two&quot;">A &amp; B</a>', prepared['content'])
        self.assertEqual(prepared['fingerprint']['links'], [{'label': 'A & B', 'href': 'https://example.test/?a=1&b="two"'}])
    def test_plain_and_literal_html_are_escaped(self):
        self.assertEqual(c.prepare('<script>alert(1)</script>')['fingerprint']['text'], '<script>alert(1)</script>')
        self.assertNotIn('<script>', c.prepare('<script>alert(1)</script>')['content'])
        self.assertEqual(c.prepare('[x](https://example.test)', 'plain')['fingerprint']['links'], [])
    def test_html_link_entity_roundtrip(self):
        source='<p>Read <a href="https://example.test/?a=1&amp;b=2">Shared notes</a></p>'
        self.assertEqual(c.prepare(source, 'html')['content'], source)
        self.assertEqual(c.fingerprint(source), c.prepare('Read [Shared notes](https://example.test/?a=1&b=2)')['fingerprint'])
    def test_unsafe_html_and_links_refused(self):
        for source in ['<img src="x">', '<a href="javascript:alert(1)">X</a>', '<a href="https://example.test" onclick="x()">X</a>', '<script>x</script>', '<p>unclosed', '<p><!--hidden--></p>', '<a href="//example.test">X</a>']:
            with self.subTest(source=source), self.assertRaises(ValueError): c.prepare(source,'html')
        for url in ['javascript:alert', 'data:text/plain,secret', 'file:///tmp/x', 'https://user:pass@example.test', 'https://example.test/\n']:
            with self.subTest(url=url), self.assertRaises(ValueError): c.safe_url(url)
    def test_link_loss_or_destination_change_is_not_equal(self):
        wanted=c.prepare('Read [notes](https://example.test/one)')['fingerprint']
        self.assertNotEqual(wanted,c.fingerprint('<p>Read notes</p>'))
        self.assertNotEqual(wanted,c.prepare('Read [notes](https://example.test/two)')['fingerprint'])
    def test_whitespace_and_html_wrapping_are_equivalent(self):
        self.assertEqual(c.fingerprint('<p>A</p><p>B</p>'),c.fingerprint('<div>A<br>B</div>'))
    def test_legacy_plain_angle_brackets_are_literal(self):
        self.assertEqual(c.body({'body':{'contentType':'text','content':'Literal <tag> &amp; text'}})['text'],'Literal <tag> &amp; text')
    def test_current_task_url(self):
        self.assertEqual(c.task_url({'planId':'plan/x','id':'task?'},'11111111-2222-3333-4444-555555555555'),'https://planner.cloud.microsoft/ui/web/plan/plan%2Fx/view/board/task/task%3F?tid=11111111-2222-3333-4444-555555555555')
        self.assertNotIn('?tid=',c.task_url({'planId':'plan','id':'task'},'organizations'))
    def test_deleted_messages_not_active(self):
        self.assertFalse(c.active({'deletedDateTime':'2026-01-01'}))
        self.assertFalse(c.active({'deletedTime':'2026-01-01'}))
    def test_blank_and_size_rejected(self):
        for s in [' ', 'x'*10001]:
            with self.assertRaises(ValueError):c.prepare(s)

if __name__ == '__main__':unittest.main()
