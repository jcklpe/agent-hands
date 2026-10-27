"""Real CLI with synthetic gh responses only; never contacts GitHub."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / 'use-github-projects/scripts/github'


def page(nodes, more=False, cursor=None):
    return {'data': {'node': {'id': 'PROJECT_NODE', 'items': {
        'nodes': nodes, 'pageInfo': {'hasNextPage': more, 'endCursor': cursor}}}}}


class MoveCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='github-move-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'requests.jsonl'
        self.fixture = self.root / 'responses.json'
        shutil.copy(ROOT / 'setup-github/github-repos.example.json', self.root / 'github-repos.json')
        # The double records requests, enforces balanced GraphQL selection braces,
        # and models gh's JSON error output plus nonzero status on a bad query.
        fake = self.bin / 'gh'
        fake.write_text('#!'+sys.executable+'\n'+'''import json,os,re,sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['MOVE_LOG'],'a') as log: log.write(json.dumps(args)+'\\n')
f=json.loads(Path(os.environ['MOVE_FIXTURE']).read_text())
if args[:2]==['auth','status']: sys.exit(0)
if args[:2]==['issue','view']:
    print(f['issue']); sys.exit(f.get('issue_exit',0))
assert args[:2]==['api','graphql'],args
query=next(a[6:] for a in args if a.startswith('query='))
shape=re.sub(r'"(?:[^"\\\\]|\\\\.)*"','""',query)
if shape.count('{')!=shape.count('}'):
    print(json.dumps({'errors':[{'message':'Synthetic malformed query'}]})); sys.exit(1)
kind='mutation' if 'updateProjectV2ItemFieldValue' in query else ('meta' if 'organization(login:' in query else 'items')
if kind=='items':
    assert '--paginate' in args
    assert '$endCursor' in query and 'pageInfo' in query
value=f[kind]
if kind=='items' and isinstance(value,list):
    for p in value: print(json.dumps(p))
elif isinstance(value,str): print(value)
else: print(json.dumps(value))
sys.exit(f.get(kind+'_exit',0))
''')
        fake.chmod(0o755)
        # Only the double can satisfy gh; config is a temporary synthetic example.
        self.env = {k: v for k,v in os.environ.items() if not k.startswith(('GH_', 'GITHUB_'))}
        self.env.update(PATH=str(self.bin)+':'+os.environ['PATH'], BASH_ENV='/dev/null',
                        GITHUB_CONFIG_DIR=str(self.root), MOVE_LOG=str(self.log), MOVE_FIXTURE=str(self.fixture))
        self.item = {'id': 'ITEM_NODE', 'content': {'id': 'ISSUE_NODE'},
                     'fieldValueByName': {'optionId': 'OLD_OPTION', 'name': 'Waiting'}}
        self.responses = {'meta': {'data': {'organization': {'projectV2': {
            'id': 'PROJECT_NODE', 'field': {'id': 'FIELD_NODE', 'options': [
                {'id': 'OPTION_NODE', 'name': 'Ready'}, {'id': 'OLD_OPTION', 'name': 'Waiting'}]}}}}},
            'issue': 'ISSUE_NODE', 'items': [page([self.item])],
            'mutation': {'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'ITEM_NODE'}}}}}

    def run_cli(self, *extra):
        self.fixture.write_text(json.dumps(self.responses))
        self.log.write_text('')
        run = subprocess.run(['/bin/bash', str(CLI), 'move-card', '--repo', 'example',
                              '--issue', '1', '--status', 'Ready', *extra], env=self.env,
                             capture_output=True, text=True, timeout=10)
        self.requests = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.mutations = [r for r in self.requests if any('updateProjectV2ItemFieldValue' in a for a in r)]
        return run

    def fail_closed(self):
        for flags in [[], ['--execute']]:
            with self.subTest(flags=flags):
                run = self.run_cli(*flags)
                self.assertNotEqual(run.returncode, 0, run.stdout+run.stderr)
                self.assertEqual(self.mutations, [])
                self.assertNotIn('GitHub board move plan:', run.stdout)
                self.assertNotIn('No Status', run.stdout)

    def test_preview_preserves_actual_status_and_never_mutates(self):
        for flags in [[], ['--dry-run'], ['--execute', '--dry-run']]:
            run = self.run_cli(*flags)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Status: Waiting -> Ready', run.stdout)
            self.assertIn('DRY RUN', run.stdout)
            self.assertEqual(self.mutations, [])

    def test_execute_uses_resolved_ids(self):
        run = self.run_cli('--execute')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(self.mutations), 1)
        for argument in ['project=PROJECT_NODE', 'item=ITEM_NODE', 'field=FIELD_NODE', 'option=OPTION_NODE']:
            self.assertIn(argument, self.mutations[0])
        self.assertIn('Moved #1 to Ready', run.stdout)

    def test_already_matching_status_is_noop_even_with_execute(self):
        self.item['fieldValueByName'] = {'optionId': 'OPTION_NODE', 'name': 'Ready'}
        run = self.run_cli('--execute')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('nothing to do', run.stdout)
        self.assertEqual(self.mutations, [])

    def test_explicit_null_status_is_legitimate(self):
        self.item['fieldValueByName'] = None
        run = self.run_cli()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('Status: No Status -> Ready', run.stdout)
        self.assertEqual(self.mutations, [])

    def test_target_on_later_page(self):
        self.responses['items'] = [page([{'id': 'OTHER_ITEM', 'content': None}], True, 'CURSOR_1'), page([self.item])]
        run = self.run_cli('--execute')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('item=ITEM_NODE', self.mutations[0])

    def test_graphql_error_or_transport_failure_never_becomes_no_status(self):
        original = copy.deepcopy(self.responses)
        for kind in ['meta', 'items']:
            for status in [0, 1]:
                with self.subTest(kind=kind, status=status):
                    self.responses = copy.deepcopy(original)
                    self.responses[kind] = {'errors': [{'message': 'Synthetic request error'}]}
                    self.responses[kind+'_exit'] = status
                    self.fail_closed()
        self.responses = copy.deepcopy(original)
        self.responses['items_exit'] = 1  # A partial valid page must not be accepted.
        self.fail_closed()

    def test_missing_duplicate_or_invalid_target(self):
        variants = [[], [self.item, self.item]]
        for key, value in [('id', None), ('id', ''), ('id', 'null'), ('fieldValueByName', {}),
                           ('fieldValueByName', {'optionId': 'OLD_OPTION', 'name': 'Wrong'}),
                           ('fieldValueByName', {'optionId': None, 'name': 'Waiting'})]:
            item = copy.deepcopy(self.item); item[key] = value; variants.append([item])
        missing_status = copy.deepcopy(self.item); del missing_status['fieldValueByName']; variants.append([missing_status])
        for nodes in variants:
            with self.subTest(nodes=nodes):
                self.responses['items'] = [page(nodes)]
                self.fail_closed()

    def test_invalid_or_incomplete_pages(self):
        for value in ['not-json', [], [page([] ,True, 'LAST')], [page([self.item]), page([])],
                      [{'data': {'node': None}}], [page(None)]]:
            with self.subTest(value=value):
                self.responses['items'] = value
                self.fail_closed()

    def test_invalid_metadata_and_option(self):
        base = copy.deepcopy(self.responses['meta'])
        for key in ['project', 'field', 'option', 'duplicate', 'missing']:
            self.responses['meta'] = copy.deepcopy(base)
            p = self.responses['meta']['data']['organization']['projectV2']
            if key=='project': p['id'] = None
            elif key=='field': p['field']['id'] = 'null'
            elif key=='option': p['field']['options'][0]['id'] = ''
            elif key=='duplicate': p['field']['options'].append(p['field']['options'][0])
            else: p['field']['options'] = []
            with self.subTest(key=key): self.fail_closed()

    def test_invalid_issue_ids_and_failed_lookup(self):
        for value in ['', 'null', 'bad\nID']:
            self.responses['issue'] = value
            with self.subTest(value=value): self.fail_closed()
        self.responses['issue'] = 'ISSUE_NODE'; self.responses['issue_exit'] = 1
        self.fail_closed()

    def test_bad_mutation_response_is_uncertain_never_retried(self):
        for value in [{}, {'errors': [{'message': 'Synthetic mutation failure'}]},
                      {'data': {'updateProjectV2ItemFieldValue': {'projectV2Item': {'id': 'WRONG_ITEM'}}}}]:
            self.responses['mutation'] = value
            run = self.run_cli('--execute')
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(len(self.mutations), 1)
            self.assertNotIn('Moved #1', run.stdout)
            self.assertIn('outcome is uncertain', run.stderr)

    def test_malformed_error_envelope_fails_closed(self):
        self.responses['meta']['errors'] = False
        self.fail_closed()

    def test_failed_mutation_transport_is_uncertain_never_retried(self):
        self.responses['mutation_exit'] = 1
        run = self.run_cli('--execute')
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(len(self.mutations), 1)
        self.assertNotIn('Moved #1', run.stdout)
        self.assertIn('outcome is uncertain', run.stderr)


if __name__ == '__main__':
    unittest.main()
