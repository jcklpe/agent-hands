"""Mutable synthetic Canvas for write plans, readback and interrupted upload tests."""
import copy
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

from canvas_fixture import CanvasFixture,ORIGIN,TOKEN
from canvas_auth import CanvasError,Response
from canvas_read import PERMISSIONS

NOW=dt.datetime(2026,10,30,12,tzinfo=dt.timezone.utc)


def reply(body,status=200):
    return Response(status,{'content-type':'application/json'},json.dumps(body).encode())


def form(body):
    result={}
    for key,values in parse_qs((body or b'').decode(),keep_blank_values=True).items():
        names=re.findall(r'[^\[\]]+',key)
        value=values if key.endswith('[]') else values[0]
        if value in ('true','false'): value=value=='true'
        if names[-1] in {'position','indent','size','points_possible','min_score','min_percentage'}: value=float(value) if '.' in str(value) else int(value)
        if names[-1].endswith('_at') and value=='': value=None
        target=result
        for name in names[:-1]: target=target.setdefault(name,{})
        target[names[-1]]=value
    return result


class WriteFixture(CanvasFixture):
    def __init__(self):
        super().__init__(staff=True)
        self.permissions={k:True for k in PERMISSIONS}
        self.data['course']['permissions']={'create_announcement':True,'create_discussion_topic':True}
        self.data['modules'][0]['published']=False
        self.data['modules'][1]['published']=False
        self.items={'10':self.data['items'],'11':self.data['modules'][1]['items']}
        for mid,items in self.items.items():
            for item in items: item.update(module_id=mid,indent=0)
        self.writes=[];self.uploads=[];self.sequence=10000
        self.revisions={('courses','123','789'):[{'revision_id':'11','body':'<p>Old revision.</p>'},{'revision_id':'12','body':self.data['pages'][0]['body']}]}
        for revision in self.revisions[('courses','123','789')]: revision.update(title=self.data['pages'][0]['title'],url=self.data['pages'][0]['url'])
        self.submission=copy.deepcopy(self.data['assignments'][0]['submission'])
        self.submission.update(body='<p>Previous submission.</p>',submission_comments=[])
        self.entries=[{'id':'700','user_id':'2002','message':'<p>Existing entry.</p>'}]
        self.pending={};self.file_context={'900':('courses','123')}
        self.fail_before={};self.fail_after=set();self.overrides={}
        self.off_origin=False;self.bad_size=False;self.sanitize=False

    def new_id(self):
        self.sequence+=1
        return str(self.sequence)

    def send(self,method,url,headers,body=None,token=None):
        if method=='GET': return super().send(method,url,headers,body,token)
        assert token==TOKEN
        assert urlsplit(url).netloc==urlsplit(ORIGIN).netloc
        path=urlsplit(url).path
        fields=form(body)
        self.writes.append((method,path,fields))
        if path in self.fail_before: return reply({'message':'synthetic refusal'},self.fail_before[path])
        value=self.mutate(method,path,fields)
        if path in self.fail_after: raise CanvasError('network_error','Synthetic connection closed after sending')
        return reply(value)

    def route(self,path,params):
        if path in self.overrides: return self.overrides[path]
        if path.startswith('/api/v1/files/'):
            fid=path.split('/')[4]
            return next(f for f in self.data['files'] if f['id']==fid)
        if path=='/api/v1/users/self/files': return [f for f in self.data['files'] if self.file_context[f['id']]==('users','self')]
        if path.startswith('/api/v1/groups/') and len(path.split('/'))==5:
            return next(g for g in self.data['groups'] if g['id']==path.split('/')[-1])
        bits=path.split('/')
        if len(bits)<6: return super().route(path,params)
        context,cid=bits[3:5];tail='/'.join(bits[5:])
        if tail=='files/quota': return {'quota':1000000,'quota_used':380}
        if tail=='files': return [f for f in self.data['files'] if self.file_context[f['id']]==(context,cid)]
        if tail.startswith('folders/'):
            return next(f for f in self.data['folders'] if f['id']==tail.split('/')[-1])
        if tail.startswith('assignment_groups/'):
            return next(g for g in self.data['assignment_groups'] if g['id']==tail.split('/')[-1])
        if tail.startswith('quizzes/'): return {'id':tail.split('/')[-1],'title':'Synthetic quiz metadata'}
        if tail=='front_page': return {'page_id':'789','title':'Current front page'}
        if tail.startswith('pages/'):
            pieces=tail.split('/');pid=pieces[1].removeprefix('page_id:')
            pages=self.data['pages'] if context=='courses' else self.data['group_pages']
            page=next((p for p in pages if p.get('url')==pid),None) if not pieces[1].startswith('page_id:') else None
            page=page or next(p for p in pages if p['page_id']==pid)
            if len(pieces)>2:
                revisions=self.revisions.setdefault((context,cid,pid),[{'revision_id':'12',**{k:page.get(k,'') for k in ('body','title','url')}}])
                return revisions[-1] if pieces[-1]=='latest' else next(r for r in revisions if r['revision_id']==pieces[-1])
            return page
        if tail.startswith('modules/'):
            pieces=tail.split('/');mid=pieces[1]
            if len(pieces)==2: return next(m for m in self.data['modules'] if m['id']==mid)
            if len(pieces)==3: return self.items[mid]
            return next(i for i in self.items[mid] if i['id']==pieces[-1])
        if tail.startswith('assignments/'):
            if '/submissions/' in tail: return self.submission
            return next(a for a in self.data['assignments'] if a['id']==tail.split('/')[-1])
        if tail.startswith('discussion_topics/'):
            pieces=tail.split('/')
            if pieces[-1]=='view': return {'view':self.entries,'new_entries':[]}
            if pieces[-1]=='entry_list': return [e for e in self.entries if e['id'] in params['ids[]']]
            return next(t for t in self.data['announcements']+self.data['discussions'] if t['id']==pieces[1])
        return super().route(path,params)

    def reposition(self,rows,row,position):
        rest=[r for r in rows if r is not row]
        rest.sort(key=lambda r:r.get('position') or 0)
        rest.insert(len(rest) if position is None else position-1,row)
        for number,item in enumerate(rest,1): item['position']=number
        rows[:]=rest

    def mutate(self,method,path,fields):
        bits=path.split('/');context,cid=bits[3:5];tail='/'.join(bits[5:])
        if tail=='files' or tail.endswith('/submissions/self/files'):
            fid=next((f['id'] for f in self.data['files'] if f['display_name']==fields['name'] and fields['on_duplicate']=='overwrite' and self.file_context[f['id']]==(context,cid)),None) or self.new_id()
            meta={'id':fid,'display_name':fields['name'],'filename':fields['name'],'size':fields['size'],'content-type':fields['content_type'],'folder_id':fields.get('parent_folder_id','80'),'url':ORIGIN+'/files/'+fid+'/download'}
            meta.update(created_at='2026-10-30T12:01:00Z',updated_at='2026-10-30T12:01:00Z',modified_at='2026-10-30T12:01:00Z',locked=False,hidden=False,lock_at=None,unlock_at=None)
            if fields['on_duplicate']=='rename' and any(f['display_name']==meta['display_name'] and self.file_context[f['id']]==(context,cid) for f in self.data['files']): meta['display_name']='renamed-'+meta['display_name']
            self.pending[fid]=(meta,context,cid)
            return {'upload_url':'https://storage.example.net/'+fid,'upload_params':{'key':'opaque-key','signature':'synthetic-signature'}}
        if tail.startswith('pages'):
            pages=self.data['pages'] if context=='courses' else self.data['group_pages']
            pieces=tail.split('/')
            if len(pieces)==1:
                page={'page_id':self.new_id(),'url':re.sub(r'[^a-z0-9]+','-',fields['wiki_page']['title'].lower()),'published':False}
                pages.append(page)
            else: page=next(p for p in pages if p['page_id']==pieces[1].removeprefix('page_id:'))
            revisions=self.revisions.setdefault((context,cid,page['page_id']),[])
            if 'revisions' in pieces:
                old=next(r for r in revisions if r['revision_id']==pieces[-1]);page.update({k:old[k] for k in ('body','title','url')})
            else:
                page.update({k:v for k,v in fields['wiki_page'].items() if k!='notify_of_update'})
                if self.sanitize and 'body' in page: page['body']=page['body'].replace('<script>x</script>','')
            revision={'revision_id':self.new_id(),**{k:page.get(k,'') for k in ('body','title','url')}};revisions.append(revision)
            page['updated_at']='2026-10-30T12:01:00Z'
            return revision if 'revisions' in pieces else page
        if tail=='assignments' or tail.startswith('assignments/'):
            if tail.endswith('/submissions'):
                sub=fields['submission'];self.submission.update(sub,attempt=self.submission['attempt']+1)
                if 'file_ids' in sub: self.submission['attachments']=[next(f for f in self.data['files'] if f['id']==fid) for fid in sub['file_ids']]
                if fields.get('comment'): self.add_comment(fields['comment']['text_comment'])
                return self.submission
            if tail.endswith('/submissions/self'):
                self.add_comment(fields['comment']['text_comment']);return self.submission
            if tail=='assignments':
                assignment={'id':self.new_id(),'created_at':'2026-10-30T12:01:00Z','has_submitted_submissions':False};self.data['assignments'].append(assignment)
            else: assignment=next(a for a in self.data['assignments'] if a['id']==tail.split('/')[-1])
            assignment.update({k:v for k,v in fields['assignment'].items() if k!='notify_of_update'})
            if assignment.get('submission_types')==['not_graded']:
                assignment['points_possible']=None
                assignment.setdefault('grading_type','points')
            assignment['updated_at']='2026-10-30T12:01:00Z'
            return assignment
        if tail=='modules' or tail.startswith('modules/'):
            pieces=tail.split('/')
            if len(pieces)<3:
                if tail=='modules':
                    module={'id':self.new_id(),'published':False};self.data['modules'].append(module);self.items[module['id']]=[]
                else: module=next(m for m in self.data['modules'] if m['id']==pieces[1])
                module.update(fields['module']);self.reposition(self.data['modules'],module,fields['module'].get('position',module.get('position')))
                return module
            mid=pieces[1]
            if len(pieces)==3:
                item={'id':self.new_id(),'module_id':mid};self.items[mid].append(item)
            else: item=next(i for i in self.items[mid] if i['id']==pieces[-1])
            item.update(fields['module_item'])
            if method=='PUT' and 'title' in fields['module_item'] and item.get('type') in {'Assignment','File','Page'}:
                kind=item['type'];key={'Assignment':'name','File':'display_name','Page':'title'}[kind]
                rows=self.data[{'Assignment':'assignments','File':'files','Page':'pages'}[kind]]
                source=next(r for r in rows if (r.get('url')==item.get('page_url') if kind=='Page' else r['id']==item.get('content_id')))
                source.update({key:fields['module_item']['title'],'updated_at':'2026-10-30T12:02:00Z'})
                if kind=='Page':
                    revisions=self.revisions.setdefault((context,cid,source['page_id']),[])
                    revisions.append({'revision_id':self.new_id(),'body':source['body']})
            destination=fields['module_item'].get('module_id',mid)
            if destination!=mid: self.items[mid].remove(item);self.items[destination].append(item)
            self.reposition(self.items[destination],item,fields['module_item'].get('position',item.get('position')))
            return item
        if tail.startswith('discussion_topics'):
            pieces=tail.split('/')
            if 'entries' in pieces:
                entry={'id':self.new_id(),'message':fields['message'],'user_id':'1001'};self.entries.append(entry);return entry
            if len(pieces)==1:
                topic={'id':self.new_id(),'posted_at':'2026-10-30T12:00:00Z'};self.data['announcements'].append(topic)
            else: topic=next(t for t in self.data['announcements'] if t['id']==pieces[1])
            topic.update(fields);return topic
        raise AssertionError('Unexpected write: '+path)

    def add_comment(self,text):
        self.submission['submission_comments'].append({'id':self.new_id(),'author_id':'1001','comment':text})

    def upload_sender(self,url,params,path,name,content_type):
        from canvas_upload import Multipart
        packet=Multipart(params,path,name,content_type)
        parts=list(packet)
        assert len(b''.join(parts))==packet.length
        self.uploads.append({'url':url,'params':params,'chunks':parts})
        fid=urlsplit(url).path.strip('/')
        metadata,context,cid=self.pending[fid]
        if self.bad_size: metadata['size']+=1
        self.data['files'][:]=[f for f in self.data['files'] if f['id']!=fid]
        self.data['files'].append(metadata);self.file_context[fid]=(context,cid)
        return Response(302,{'location':('https://other.example.net' if self.off_origin else ORIGIN)+'/api/v1/files/'+fid+'/create_success?uuid=synthetic'},b'')
