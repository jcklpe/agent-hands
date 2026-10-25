"""Exercise composition boundaries using synthetic exports, with no provider runtime."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/render.py'
START, END = '2030-01-01T00:00:00Z', '2030-02-01T00:00:00Z'


class RenderChecks(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.output = self.root / 'agenda.md'
        self.google = dict(schema_version=1, provider='google', source='example', start=START, end=END, complete=True, calendars=[dict(calendar=dict(id='primary', summary='Calendar'), events=dict(items=[dict(id='same-local-id', iCalUID='shared-invitation', summary='Example invitation', start=dict(dateTime='2030-01-02T15:00:00Z'), end=dict(dateTime='2030-01-02T16:00:00Z'))]))])
        self.microsoft = dict(schema_version=1, provider='microsoft', source='work', start=START, end=END, timezone='UTC', complete=True, calendars=[dict(id='primary', name='Calendar', events=[dict(id='same-local-id', iCalUId='shared-invitation', subject='Example invitation', start=dict(dateTime='2030-01-02T15:00:00.0000000', timeZone='UTC'), end=dict(dateTime='2030-01-02T16:00:00.0000000', timeZone='UTC'))])])

    def run_render(self, bundles, *extra):
        command = [sys.executable, str(SCRIPT), '--from', START, '--to', END, '--timezone', 'America/Chicago', '--output', str(self.output), '--expect-source', 'google:example', '--expect-source', 'microsoft:work']
        for index, bundle in enumerate(bundles):
            path = self.root / f'input-{index}.json'
            path.write_text(json.dumps(bundle))
            command += ['--input', str(path)]
        return subprocess.run(command + list(extra), text=True, capture_output=True)

    def test_merge_and_timezone(self):
        result = self.run_render([self.google, self.microsoft])
        self.assertEqual(result.returncode, 0, result.stderr)
        output = self.output.read_text()
        self.assertIn('09:00-10:00', output)
        self.assertEqual(output.count('Example invitation'), 1)
        self.assertIn('google:example: included', output)
        self.assertIn('microsoft:work: included', output)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_equal_local_ids_are_not_a_shared_identity(self):
        del self.google['calendars'][0]['events']['items'][0]['iCalUID']
        del self.microsoft['calendars'][0]['events'][0]['iCalUId']
        result = self.run_render([self.google, self.microsoft])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_text().count('Example invitation'), 2)

    def test_missing_source_preserves_old_output_unless_explicit(self):
        self.output.write_text('previous')
        result = self.run_render([self.google], '--force')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.output.read_text(), 'previous')
        result = self.run_render([self.google], '--force', '--allow-missing')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('microsoft:work: MISSING', self.output.read_text())
        self.assertIn('INCOMPLETE', self.output.read_text())

    def test_invalid_inputs_and_existing_target_are_preserved(self):
        self.output.write_text('previous')
        self.assertNotEqual(self.run_render([self.google, self.microsoft]).returncode, 0)
        invalid = []
        short = copy.deepcopy(self.google); short['start'] = '2030-01-02T00:00:00Z'; invalid.append(short)
        incomplete = copy.deepcopy(self.google); incomplete['complete'] = False; invalid.append(incomplete)
        empty = copy.deepcopy(self.google); empty['calendars'] = []; invalid.append(empty)
        malformed = copy.deepcopy(self.google); malformed['calendars'][0]['events']['items'][0]['end'] = {}; invalid.append(malformed)
        duplicate = copy.deepcopy(self.google); duplicate['calendars'] *= 2; invalid.append(duplicate)
        for bundle in invalid:
            with self.subTest(bundle=bundle):
                self.assertNotEqual(self.run_render([bundle, self.microsoft], '--force').returncode, 0)
                self.assertEqual(self.output.read_text(), 'previous')
        self.assertNotEqual(self.run_render([self.google, self.google, self.microsoft], '--force').returncode, 0)
        self.assertEqual(self.output.read_text(), 'previous')
        self.output.unlink()
        target = self.root / 'protected'; target.write_text('protected')
        self.output.symlink_to(target)
        self.assertNotEqual(self.run_render([self.google, self.microsoft], '--force').returncode, 0)
        self.assertEqual(target.read_text(), 'protected')

    def test_compact_and_no_sources(self):
        self.assertEqual(self.run_render([self.google, self.microsoft], '--compact').returncode, 0)
        self.assertIn('Long-Horizon Agenda', self.output.read_text())
        self.assertEqual(self.run_render([], '--force', '--allow-missing').returncode, 2)
        self.assertIn('not an empty calendar', self.output.read_text())


if __name__ == '__main__':
    unittest.main()
