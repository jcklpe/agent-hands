#!/usr/bin/env python3
"""Exercise the real CLI through a stateful synthetic HTTP boundary."""
from pathlib import Path
import json,os,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
BOARD='a'*24; LIST='b'*24; CARD='c'*24; NEXT='d'*24; LABEL='e'*24; CHECK='f'*24; ITEM='1'*24
class MutationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.dir=Path(self.temp.name);self.state=self.dir/'state.json';self.bin=self.dir/'bin';self.bin.mkdir()
  fixture=Path(__file__).with_name('trello_http_fixture.py');(self.bin/'curl').write_text('#!/bin/sh\nexec '+__import__('shlex').quote(__import__('sys').executable)+' '+__import__('shlex').quote(str(fixture))+' "$@"\n');(self.bin/'curl').chmod(0o755)
  (self.dir/'empty.env').touch();self.env=dict(os.environ,PATH=str(self.bin)+':/opt/homebrew/bin:/usr/bin:/bin',TRELLO_ENV_FILE=str(self.dir/'empty.env'),TRELLO_TEST_STATE=str(self.state),TRELLO_API_KEY='synthetic-key',TRELLO_TOKEN='synthetic-read',TRELLO_BOARD_IDS=BOARD)
  self.env.pop('TRELLO_WRITE_TOKEN',None);self.reset()
 def reset(self,**extra):
  cards={x:dict(id=x,idBoard=BOARD,idList=LIST,name='Original '+x[0],desc='Original text',start=None,idLabels=[LABEL],closed=False,url='https://trello.com/c/'+x) for x in [CARD,NEXT]}
  self.state.write_text(json.dumps(dict(sequence=256,cards=cards,boards={BOARD:dict(id=BOARD,name='Board',closed=False)},lists={LIST:dict(id=LIST,idBoard=BOARD,name='Ready',closed=False)},labels={LABEL:dict(id=LABEL,idBoard=BOARD,name='Label',color='blue')},checklists={CHECK:dict(id=CHECK,idCard=CARD,name='Checklist',pos=1)},items={CHECK:[dict(id=ITEM,name='Item',state='incomplete',pos=1)]},comments={},aliases={'card':CARD,'next':NEXT},**extra)))
  Path(str(self.state)+'.requests').write_text('')
 def run_cli(self,args,execute=False,success=True):
  env=dict(self.env)
  if execute:env['TRELLO_WRITE_TOKEN']='synthetic-write'
  r=subprocess.run(['/bin/bash',str(ROOT/'scripts/trello'),*args],env=env,text=True,capture_output=True,timeout=60)
  if success:self.assertEqual(r.returncode,0,r.stderr+r.stdout)
  else:self.assertNotEqual(r.returncode,0,r.stdout)
  return r
 def writes(self):return [json.loads(x) for x in Path(str(self.state)+'.requests').read_text().splitlines() if json.loads(x)['method']!='GET']
 def cases(self):
  f=self.dir/'text.md';f.write_text('Description with newline\nand literal $(never-run).')
  return [
   ['add-card','--list','Ready','--name','New','--desc-file',str(f)],
   ['move-card','--card','card','--list',LIST],
   ['schedule-card','--card',CARD,'--list','Ready','--until','2026-12-03'],
   ['rename-card','--card',CARD,'--name','New name'],
   ['set-desc','--card',CARD,'--file',str(f)],
   ['comment','--card',CARD,'--text','Hello'],
   ['add-checklist','--card','card','--name','New checklist','--item','First','--item','Second'],
   ['add-checklist-item','--card',CARD,'--checklist',CHECK,'--text','First','--text','Second'],
   ['check-item','--card',CARD,'--item','Item'],
   ['uncheck-item','--card',CARD,'--item',ITEM,'--checklist','Checklist'],
   ['create-label','--name','New label'],
   ['add-label','--card',CARD,'--label','Label'],
   ['remove-label','--card',CARD,'--label',LABEL],
   ['delete-label','--label',LABEL],
   ['supersede','--from','card','--to','next'],
   ['supersede','--create','--from',CARD,'--list',LIST,'--name','Successor']]
 def test_all_mutations_preview_without_any_write_token_or_mutation_request(self):
  for args in self.cases():
   with self.subTest(command=args[0],create='--create' in args):
    self.reset();r=self.run_cli(args+['--json']);plan=json.loads(r.stdout);self.assertEqual(plan['mode'],'preview');self.assertEqual(plan['writes_sent'],0);self.assertEqual(self.writes(),[]);self.assertGreater(len(plan['steps']),0)
    if args[0]=='add-checklist':self.assertEqual(len(plan['steps']),3);self.assertEqual([s['fields'].get('name') for s in plan['steps']],['New checklist','First','Second'])
    if '--create' in args:self.assertEqual(len(plan['steps']),3)
 def test_all_execute_paths_and_readback(self):
  for args in self.cases():
   with self.subTest(command=args[0],create='--create' in args):
    self.reset();plan=json.loads(self.run_cli(args+['--json']).stdout)
    result=json.loads(self.run_cli(args+['--execute','--expect',plan['preview_hash'],'--json'],execute=True).stdout)
    self.assertEqual(result['mode'],'executed');self.assertEqual(len(result['verified_steps']),len(self.writes()));self.assertEqual(len(self.writes()),len(plan['steps']))
 def test_stale_hash_and_revalidation_race_send_zero_writes(self):
  args=['rename-card','--card',CARD,'--name','Updated'];plan=json.loads(self.run_cli(args+['--json']).stdout)
  state=json.loads(self.state.read_text());state['cards'][CARD]['name']='Changed';self.state.write_text(json.dumps(state))
  self.run_cli(args+['--execute','--expect',plan['preview_hash']],execute=True,success=False);self.assertEqual(self.writes(),[])
  self.reset(race=True);self.run_cli(args+['--execute'],execute=True,success=False);self.assertEqual(self.writes(),[])
 def test_partial_failure_stops_sequence_without_retry(self):
  self.reset(fail_write=2);r=self.run_cli(['add-checklist','--card',CARD,'--name','New','--item','First','--item','Second','--execute'],execute=True,success=False)
  self.assertEqual(len(self.writes()),2);self.assertIn('PARTIAL or uncertain',r.stderr);self.assertIn('Verified prior steps',r.stderr)
 def test_readback_and_malformed_response_cannot_report_success(self):
  for flag in ['readback_fail','invalid_response']:
   with self.subTest(flag=flag):
    self.reset(**{flag:True});r=self.run_cli(['add-card','--list',LIST,'--name','New','--execute'],execute=True,success=False)
    self.assertEqual(len(self.writes()),1);self.assertIn('PARTIAL or uncertain',r.stderr);self.assertNotIn('"mode": "executed"',r.stdout)
 def test_wrong_checklist_card_and_closed_target_refuse_without_writes(self):
  self.run_cli(['add-checklist-item','--card',NEXT,'--checklist',CHECK,'--text','No'],success=False);self.assertEqual(self.writes(),[])
  state=json.loads(self.state.read_text());state['cards'][CARD]['closed']=True;self.state.write_text(json.dumps(state))
  self.run_cli(['rename-card','--card',CARD,'--name','No','--execute'],execute=True,success=False);self.assertEqual(self.writes(),[])
 def test_invalid_date_and_reserved_file_content_send_zero_writes(self):
  for date in ['2026-02-29','2026-04-31','2026-13-01']:
   self.run_cli(['schedule-card','--card',CARD,'--list',LIST,'--until',date,'--execute'],execute=True,success=False)
  f=self.dir/'literal.md';f.write_text('Literal __AH_PLAN_1_ID__ text')
  self.run_cli(['set-desc','--card',CARD,'--file',str(f),'--execute'],execute=True,success=False);self.assertEqual(self.writes(),[])
 def test_incomplete_label_listing_and_wrong_board_send_zero_writes(self):
  state=json.loads(self.state.read_text());state['labels']={f'{i:024x}':dict(id=f'{i:024x}',idBoard=BOARD,name='Label',color='blue') for i in range(1000)};self.state.write_text(json.dumps(state))
  self.run_cli(['add-label','--card',CARD,'--label','Label','--execute'],execute=True,success=False);self.assertEqual(self.writes(),[])
  self.reset();self.run_cli(['add-label','--card',CARD,'--label',LABEL,'--board','9'*24,'--execute'],execute=True,success=False);self.assertEqual(self.writes(),[])
 def test_remote_marker_text_is_not_interpreted_as_plan_input(self):
  state=json.loads(self.state.read_text());state['cards'][CARD]['desc']='Remote __AH_PLAN_1_ID__ text';self.state.write_text(json.dumps(state))
  self.run_cli(['rename-card','--card',CARD,'--name','New','--execute'],execute=True);self.assertEqual(len(self.writes()),1)
 def test_successful_empty_delete_response_is_verified_by_readback(self):
  for args in [['remove-label','--card',CARD,'--label',LABEL],['delete-label','--label',LABEL]]:
   with self.subTest(command=args[0]):
    self.reset(empty_delete_response=True);self.run_cli(args+['--execute'],execute=True);self.assertEqual(len(self.writes()),1)
if __name__=='__main__':unittest.main()
