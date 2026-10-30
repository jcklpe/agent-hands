import datetime as dt
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from unittest.mock import patch

from canvas_write_fixture import WriteFixture,NOW
from canvas_auth import CanvasError
from canvas_history import History
from canvas_write import Builder,run_write,date_input
import canvas


class WritesTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name).resolve();self.fixture=WriteFixture()
        self.html=self.root/'body.html';self.html.write_text('<p>New content.</p>')
        self.md=self.root/'body.md';self.md.write_text('New **content**.')
        self.comment=self.root/'comment.txt';self.comment.write_text('A submission comment.')
        self.file=self.root/'file.txt';self.file.write_bytes(b'file content')
        self.history=History(self.root/'history',now=NOW)

    def args(self,command,*options):
        return canvas.parser().parse_args([command,'example','--course','123',*options])

    def run_command(self,args):
        return run_write(self.fixture.reader(),args,self.history,NOW,self.fixture.upload_sender)

    def preview(self,command,*options):
        args=self.args(command,*options);result,code=self.run_command(args)
        self.assertEqual(code,0)
        self.assertEqual(result['writes_sent'],0)
        return args,result

    def execute(self,command,*options):
        args,preview=self.preview(command,*options)
        args.execute=True;args.expect=preview['preview_hash']
        result,code=self.run_command(args)
        self.assertEqual(code,0,result)
        return result

    def test_all_fifteen_commands_preview_without_writes(self):
        self.fixture.data['announcements'][0].update(delayed_post_at='2026-12-01T12:00:00Z',posted_at=None)
        cases={
            'create-page':['--title','A page','--body-file',str(self.html)],
            'edit-page':['--page','789','--title','New title'],
            'revert-page':['--page','789','--revision','11'],
            'create-assignment':['--name','A task','--body-file',str(self.md)],
            'edit-assignment':['--assignment','456','--name','New assignment'],
            'create-module':['--name','A module'],
            'edit-module':['--module','10','--name','New module'],
            'add-module-item':['--module','10','--type','SubHeader','--title','Section'],
            'edit-module-item':['--module','10','--item','101','--title','New item'],
            'create-announcement':['--title','A notice','--body-file',str(self.html)],
            'edit-announcement':['--topic','111','--title','New notice'],
            'upload-file':['--file',str(self.file)],
            'submit-assignment':['--assignment','456','--body-file',str(self.md)],
            'comment-submission':['--assignment','456','--comment-file',str(self.comment)],
            'reply-discussion':['--topic','222','--body-file',str(self.md)]}
        for command,options in cases.items():
            with self.subTest(command=command): self.preview(command,*options)
        self.assertEqual(self.fixture.writes,[]);self.assertEqual(self.fixture.uploads,[])

    def test_create_edit_revert_pages_and_revision_history(self):
        self.execute('create-page','--title','A page','--body-file',str(self.md))
        self.execute('edit-page','--page','789','--body-file',str(self.html))
        self.execute('revert-page','--page','789','--revision','11')
        self.assertEqual(self.fixture.data['pages'][0]['body'],'<p>Old revision.</p>')
        records=list(self.history.rows())
        self.assertTrue(any(r.get('target_ids') for r in records if r['outcome']=='verified'))
        self.assertNotIn('<p>',json.dumps(records))

    def test_create_and_edit_assignments_preserve_overrides(self):
        self.execute('create-assignment','--name','New task','--due-at','2026-11-12T10:00:00-06:00','--points','5')
        args,result=self.preview('edit-assignment','--assignment','456','--due-at','2026-11-15T10:00:00-06:00')
        self.assertIn('overrides',str(result['warnings']))
        args.execute=True;args.expect=result['preview_hash'];self.assertEqual(self.run_command(args)[1],0)
        for method,path,fields in self.fixture.writes:
            self.assertNotIn('assignment_overrides',json.dumps(fields))
            if 'assignment' in fields: self.assertIs(fields['assignment']['notify_of_update'],False)

    def test_modules_order_publishing_and_items(self):
        self.execute('create-module','--name','Inserted','--position','2','--published','--prerequisite','10')
        self.assertEqual(self.fixture.data['modules'][1]['name'],'Inserted')
        self.assertIs(self.fixture.data['modules'][1]['published'],True)
        self.execute('edit-module','--module','10','--name','Renamed')
        self.execute('add-module-item','--module','10','--type','SubHeader','--title','New section','--position','1')
        self.execute('edit-module-item','--module','10','--item','101','--move-to-module','11','--completion','must_view')
        self.assertTrue(any(i['id']=='101' for i in self.fixture.items['11']))

    def test_announcements_need_ack_and_posted_edits_refuse(self):
        args,preview=self.preview('create-announcement','--title','A notice','--body-file',str(self.html))
        args.execute=True;args.expect=preview['preview_hash']
        with self.assertRaises(CanvasError): self.run_command(args)
        self.assertEqual(self.fixture.writes,[])
        args.notify_course=True;self.assertEqual(self.run_command(args)[1],0)
        with self.assertRaises(CanvasError): self.preview('edit-announcement','--topic','111','--title','Too late')
        self.fixture.data['announcements'][0].update(delayed_post_at='2026-12-01T00:00:00Z',posted_at=None)
        self.execute('edit-announcement','--topic','111','--title','Future notice')

    def test_student_submission_comment_and_discussion_reply(self):
        self.execute('submit-assignment','--assignment','456','--body-file',str(self.md),'--comment-file',str(self.comment))
        self.assertEqual(self.fixture.submission['attempt'],2)
        self.comment.write_text('Another comment.')
        self.execute('comment-submission','--assignment','456','--comment-file',str(self.comment))
        self.execute('reply-discussion','--topic','222','--entry','700','--body-file',str(self.md))
        self.assertTrue(any('/entries/700/replies' in p for _,p,_ in self.fixture.writes))

    def test_hash_is_required_and_stale_page_assignment_module_refuse(self):
        for command,options,mutate in (
            ('edit-page',['--page','789','--title','New'],lambda:self.fixture.data['pages'][0].update(body='Changed elsewhere')),
            ('edit-assignment',['--assignment','456','--name','New'],lambda:self.fixture.data['assignments'][0].update(updated_at='2026-10-30T11:00:00Z')),
            ('edit-module',['--module','10','--name','New'],lambda:self.fixture.data['modules'][0].update(name='Elsewhere'))):
            with self.subTest(command=command):
                args,plan=self.preview(command,*options);args.execute=True
                with self.assertRaises(CanvasError): self.run_command(args)
                args.expect=plan['preview_hash'];mutate()
                with self.assertRaises(CanvasError) as error:self.run_command(args)
                self.assertEqual(error.exception.kind,'preview_stale')
        self.assertEqual(self.fixture.writes,[])

    def test_new_duplicate_after_preview_blocks_create(self):
        args,plan=self.preview('create-page','--title','New')
        self.fixture.data['pages'].append({'page_id':'999','title':'New','url':'new','body':''})
        args.execute=True;args.expect=plan['preview_hash']
        with self.assertRaises(CanvasError):self.run_command(args)
        self.assertEqual(self.fixture.writes,[])

    def test_scalar_mismatch_and_sanitized_html_are_distinct(self):
        args,plan=self.preview('edit-page','--page','789','--title','New')
        original=self.fixture.mutate
        def mutate(method,path,fields):
            result=original(method,path,fields);result['title']='Wrong';return result
        self.fixture.mutate=mutate;args.execute=True;args.expect=plan['preview_hash']
        result,code=self.run_command(args);self.assertEqual(code,3);self.assertEqual(result['error_kind'],'readback_mismatch')
        self.fixture.mutate=original;self.fixture.sanitize=True;self.html.write_text('<p>Safe.</p><script>x</script>')
        result=self.execute('edit-page','--page','789','--body-file',str(self.html))
        self.assertEqual(result['outcome'],'verified_with_sanitizer_changes');self.assertTrue(result['warnings'])

    def test_partial_publish_keeps_created_module_id_and_blocks_duplicate(self):
        args,plan=self.preview('create-module','--name','New module','--published')
        # Fail the dynamic publish request after the create succeeds.
        self.fixture.fail_before['/api/v1/courses/123/modules/10001']=403
        args.execute=True;args.expect=plan['preview_hash'];result,code=self.run_command(args)
        self.assertEqual(code,3);self.assertIn('module.id',result['target_ids'])
        with self.assertRaises(CanvasError): self.preview('create-module','--name','New module','--published')

    def test_transport_uncertainty_is_not_retried_and_history_blocks_prune(self):
        args,plan=self.preview('edit-page','--page','789','--title','New')
        self.fixture.fail_after.add('/api/v1/courses/123/pages/page_id:789')
        args.execute=True;args.expect=plan['preview_hash'];result,code=self.run_command(args)
        self.assertEqual(code,3);self.assertEqual(len(self.fixture.writes),1)
        rows=list(self.history.rows());self.assertTrue(any(r['outcome']=='uncertain' for r in rows))
        with self.assertRaises(CanvasError):self.history.prune('example','2099-01',True)

    def test_markdown_loss_dates_and_unsupported_input_refuse(self):
        with self.assertRaises(CanvasError):self.preview('edit-page','--page','789','--body-file',str(self.md))
        self.execute('edit-page','--page','789','--body-file',str(self.md),'--accept-loss')
        self.fixture.data['pages'][0]['body']='<p style="color:red">Styled text.</p>'
        with self.assertRaises(CanvasError):self.preview('edit-page','--page','789','--body-file',str(self.md))
        for value,zone in [('2026-11-01T01:30:00','America/Chicago'),('2026-03-08T02:30:00','America/Chicago'),('2026-11-01T12:00:00',None)]:
            with self.assertRaises(CanvasError):date_input(value,zone)
        self.assertEqual(date_input('2026-11-01T01:30:00-06:00'),'2026-11-01T07:30:00Z')
        self.assertEqual(date_input('2026-11-01T12:00:00','America/Chicago'),'2026-11-01T18:00:00Z')

    def test_concluded_permissions_and_unknown_permissions(self):
        self.fixture.data['course']['workflow_state']='completed'
        with self.assertRaises(CanvasError):self.preview('create-page','--title','New')
        self.fixture.data['course']['workflow_state']='available';self.fixture.permissions['manage_wiki_create']=False
        with self.assertRaises(CanvasError):self.preview('create-page','--title','New')
        del self.fixture.permissions['manage_wiki_create']
        _,plan=self.preview('create-page','--title','New');self.assertIn('not reported',str(plan['warnings']))

    def test_attempt_drift_locked_types_and_duplicate_posts_refuse(self):
        args,plan=self.preview('submit-assignment','--assignment','456','--body-file',str(self.md))
        self.fixture.submission['attempt']+=1;args.execute=True;args.expect=plan['preview_hash']
        with self.assertRaises(CanvasError):self.run_command(args)
        self.fixture.data['assignments'][0]['locked_for_user']=True
        with self.assertRaises(CanvasError):self.preview('submit-assignment','--assignment','456','--body-file',str(self.md))
        self.execute('reply-discussion','--topic','222','--body-file',str(self.md))
        with self.assertRaises(CanvasError):self.preview('reply-discussion','--topic','222','--body-file',str(self.md))

    def test_unwritable_history_refuses_before_write(self):
        args,plan=self.preview('edit-page','--page','789','--title','New')
        args.execute=True;args.expect=plan['preview_hash']
        with patch.object(self.history,'_append',side_effect=OSError('unwritable')),self.assertRaises(CanvasError):self.run_command(args)
        self.assertEqual(self.fixture.writes,[])

    def test_wrong_hash_throttling_and_readback_denial(self):
        args,plan=self.preview('edit-page','--page','789','--title','New')
        args.execute=True;args.expect='0'*64
        with self.assertRaises(CanvasError):self.run_command(args)
        self.assertEqual(self.fixture.writes,[])
        args.expect=plan['preview_hash'];self.fixture.fail_before['/api/v1/courses/123/pages/page_id:789']=429
        result,code=self.run_command(args)
        self.assertEqual(code,1,result);self.assertEqual(len(self.fixture.writes),1)
        self.fixture.fail_before.clear();self.fixture.writes.clear()
        original=self.fixture.mutate
        def mutate(method,path,fields):
            value=original(method,path,fields);self.fixture.failures[path]=(403,{})
            return value
        self.fixture.mutate=mutate
        result,code=self.run_command(args)
        self.assertEqual(code,3,result)
        self.assertTrue(list(self.history.rows(outcome='uncertain')))

    def test_verified_journal_events_do_not_remain_uncertain(self):
        self.execute('edit-page','--page','789','--title','New')
        self.assertEqual(list(self.history.rows(outcome='uncertain')),[])
        self.assertEqual(self.history.prune('example','2099-01')['mode'],'preview')

    def test_writes_do_not_require_export_selection(self):
        from dataclasses import replace
        reader=self.fixture.reader();reader.client.account=replace(reader.client.account,courses=())
        args=self.args('create-page','--title','Outside export selection')
        result,code=run_write(reader,args,self.history,NOW)
        self.assertEqual(code,0);self.assertEqual(result['writes_sent'],0)

    def test_initial_discussion_post_and_explicit_reply_context(self):
        self.fixture.data['discussions'][0].update(require_initial_post=True,user_can_see_posts=False)
        self.fixture.failures['/api/v1/courses/123/discussion_topics/222/view']=(403,{})
        self.preview('reply-discussion','--topic','222','--body-file',str(self.md))
        with self.assertRaises(CanvasError):self.preview('reply-discussion','--topic','222','--entry','700','--body-file',str(self.md))
        self.fixture.failures.clear()
        _,plan=self.preview('reply-discussion','--topic','222','--entry','700','--body-file',str(self.md))
        self.assertEqual(plan['target']['reply_to']['message'],'<p>Existing entry.</p>')

    def test_preview_displays_local_dates_and_utf8_rejection(self):
        _,plan=self.preview('edit-assignment','--assignment','456','--due-at','2026-11-15T10:00:00-06:00')
        date=next(c for c in plan['changes'] if c['field']=='due_at')
        self.assertIn('10:00:00-06:00',date['after_local'])
        self.assertEqual(date['after'],'2026-11-15T16:00:00Z')
        self.md.write_bytes(b'\xff')
        with self.assertRaises(CanvasError):self.preview('create-page','--title','New','--body-file',str(self.md))

    def test_duplicate_submission_comments_and_unaccepted_type(self):
        self.execute('comment-submission','--assignment','456','--comment-file',str(self.comment))
        with self.assertRaises(CanvasError):self.preview('comment-submission','--assignment','456','--comment-file',str(self.comment))
        with self.assertRaises(CanvasError):self.preview('submit-assignment','--assignment','456','--url','https://example.net/result')

    def test_cli_preview_execution_and_refusal_codes(self):
        import os
        from canvas_fixture import TOKEN,ORIGIN
        env=self.root/'.env';env.write_text('CANVAS_TOKEN_EXAMPLE='+TOKEN+'\n');env.chmod(0o600)
        (self.root/'canvas-accounts.json').write_text(json.dumps({'accounts':[{'alias':'example','base_url':ORIGIN,'user_id':'1001','token_env':'CANVAS_TOKEN_EXAMPLE','courses':['123']}]}))
        options=['create-page','example','--course','123','--title','CLI page','--json']
        with patch.dict(os.environ,{'CANVAS_CONFIG_DIR':str(self.root),'CANVAS_HISTORY_DIR':str(self.root/'cli-history')},clear=True):
            output=io.StringIO()
            with redirect_stdout(output):code=canvas.main(options,transport=self.fixture,now=NOW)
            self.assertEqual(code,0);plan=json.loads(output.getvalue());self.assertEqual(self.fixture.writes,[])
            output=io.StringIO()
            with redirect_stdout(output):code=canvas.main(options+['--execute','--expect',plan['preview_hash']],transport=self.fixture,now=NOW)
            self.assertEqual(code,0);self.assertEqual(json.loads(output.getvalue())['outcome'],'verified')
            self.assertNotIn(TOKEN,output.getvalue())

    def test_each_module_item_reference_type_and_nested_completion(self):
        for kind,options in [('Page',['--page','789']),('Assignment',['--content-id','456','--allow-duplicate']),('File',['--content-id','900']),('Quiz',['--content-id','501']),('ExternalUrl',['--url','https://example.net/material','--title','External material'])]:
            with self.subTest(kind=kind):
                self.execute('add-module-item','--module','11','--type',kind,*options)
        self.execute('edit-module-item','--module','10','--item','101','--completion','min_percentage','--minimum','80')
        item=next(i for i in self.fixture.items['10'] if i['id']=='101')
        self.assertEqual(item['completion_requirement'],{'type':'min_percentage','min_percentage':80})

    def test_history_failure_after_send_stays_uncertain(self):
        args,plan=self.preview('edit-page','--page','789','--title','New')
        args.execute=True;args.expect=plan['preview_hash'];append=self.history._append;count=0
        def failing(row):
            nonlocal count
            count+=1
            if count==3:raise OSError('Synthetic history failure after sending')
            return append(row)
        with patch.object(self.history,'_append',side_effect=failing):result,code=self.run_command(args)
        self.assertEqual(code,3,result);self.assertEqual(len(self.fixture.writes),1)
        self.assertTrue(list(self.history.rows(outcome='uncertain')))

    def test_group_discussion_reply_uses_group_route(self):
        args=canvas.parser().parse_args(['reply-discussion','example','--group','77','--topic','222','--body-file',str(self.md)])
        plan,_=self.run_command(args);args.execute=True;args.expect=plan['preview_hash']
        result,code=self.run_command(args);self.assertEqual(code,0,result)
        self.assertEqual(self.fixture.writes[-1][1],'/api/v1/groups/77/discussion_topics/222/entries')

    def test_module_page_reference_checks_stable_id_after_write(self):
        args,plan=self.preview('add-module-item','--module','11','--type','Page','--page','789')
        original=self.fixture.mutate
        def mutate(method,path,fields):
            self.fixture.data['pages'][0]['url']='renamed-during-write'
            self.fixture.data['pages'].append({'page_id':'999','url':'overview','title':'Another page','body':'Other'})
            return original(method,path,fields)
        self.fixture.mutate=mutate;args.execute=True;args.expect=plan['preview_hash']
        result,code=self.run_command(args)
        self.assertEqual(code,3,result);self.assertEqual(result['error_kind'],'readback_mismatch')


if __name__=='__main__':unittest.main()
