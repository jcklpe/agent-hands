import importlib.util
import tempfile
import unittest
from pathlib import Path
from email.parser import BytesParser
from email.policy import default

spec = importlib.util.spec_from_file_location('upload', Path(__file__).resolve().parents[1] / 'scripts/upload_payload.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class UploadPayloadTests(unittest.TestCase):
    def test_binary_roundtrip_and_source_change(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            source = p / 'source.pdf'
            data = bytes(range(256)) + b'\x00\r\n'
            source.write_bytes(data)
            module.prepare('example', source, 'folder', 'source.pdf', p)
            boundary = (p / 'upload.boundary').read_text()
            msg = BytesParser(policy=default).parsebytes(f'Content-Type: multipart/related; boundary={boundary}\r\n\r\n'.encode() + (p / 'upload.body').read_bytes())
            self.assertEqual(list(msg.iter_parts())[1].get_payload(decode=True), data)
            before = (p / 'upload.hash').read_text()
            source.write_bytes(b'changed')
            module.prepare('example', source, 'folder', 'source.pdf', p)
            self.assertNotEqual(before, (p / 'upload.hash').read_text())
            with self.assertRaises(ValueError):
                module.prepare('example', source, 'folder', '../unsafe', p)
            link = p / 'link'
            link.symlink_to(source)
            with self.assertRaises(ValueError):
                module.prepare('example', link, 'folder', 'link', p)
