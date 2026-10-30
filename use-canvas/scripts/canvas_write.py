"""Computed Canvas write plans, fresh-state fingerprints and journaled execution."""
import argparse
import datetime as dt
import difflib
import hashlib
import json
import math
import mimetypes
import re
import sys
import uuid
import zoneinfo
from pathlib import Path
from urllib.parse import urlsplit,urljoin,quote

from canvas_auth import CanvasError, id_string, parse_json, verify_identity

COMMANDS=('create-page','edit-page','revert-page','create-assignment','edit-assignment','create-module','edit-module','add-module-item','edit-module-item','create-announcement','edit-announcement','upload-file','submit-assignment','comment-submission','reply-discussion')
PAGE_COMMANDS={'create-page','edit-page','revert-page'}
VOLATILE={'read_state','unread_count','subscribed','last_reply_at','url','preview_url','thumbnail_url','avatar_url','avatar_image_url','edited_by','last_edited_by'}


def add_commands(commands, canvas_id):
    for name in COMMANDS:
        p=commands.add_parser(name,help='preview, then execute a reviewed '+name+' plan')
        p.add_argument('alias')
        target=p.add_mutually_exclusive_group(required=True)
        target.add_argument('--course',type=canvas_id)
        if name in PAGE_COMMANDS|{'upload-file','reply-discussion'}:
            target.add_argument('--group',type=canvas_id)
        if name=='upload-file':
            target.add_argument('--personal',action='store_true')
        p.add_argument('--history-dir',type=Path)
        p.add_argument('--json',action='store_true')
        p.add_argument('--execute',action='store_true')
        p.add_argument('--expect')
        p.add_argument('--allow-duplicate',action='store_true')
        p.add_argument('--tz')
        if name in PAGE_COMMANDS|{'create-assignment','edit-assignment','reply-discussion','create-announcement','edit-announcement'}:
            if name!='revert-page': p.add_argument('--body-file',type=Path)
            p.add_argument('--accept-loss',action='store_true')
        if name in {'create-page','edit-page','create-assignment','edit-assignment'}:
            p.add_argument('--notify',action='store_true')
        if name in {'create-page','edit-page','create-announcement','edit-announcement'}:
            p.add_argument('--title',required=name.startswith('create-'))
        if name in {'edit-page','revert-page'}: p.add_argument('--page',type=canvas_id,required=True)
        if name in PAGE_COMMANDS:
            if name=='revert-page': p.add_argument('--revision',type=canvas_id,required=True)
            else:
                p.add_argument('--editing-roles')
                p.add_argument('--front-page',action=argparse.BooleanOptionalAction,default=None)
        if name in {'create-page','edit-page','create-assignment','edit-assignment','create-module','edit-module','edit-module-item'}:
            p.add_argument('--published',action=argparse.BooleanOptionalAction,default=None)
        if name in {'create-assignment','edit-assignment','create-module','edit-module'}:
            p.add_argument('--name',required=name.startswith('create-'))
        if name in {'edit-assignment','submit-assignment','comment-submission'}:
            p.add_argument('--assignment',type=canvas_id,required=True)
        if name in {'create-assignment','edit-assignment'}:
            for flag in ('due-at','unlock-at','lock-at'): p.add_argument('--'+flag)
            p.add_argument('--points',type=float)
            p.add_argument('--submission-type',action='append',choices=['online_text_entry','online_url','online_upload','none','not_graded','on_paper'])
            p.add_argument('--assignment-group',type=canvas_id)
        if name in {'edit-module','add-module-item','edit-module-item'}: p.add_argument('--module',type=canvas_id,required=True)
        if name in {'create-module','edit-module','add-module-item','edit-module-item'}: p.add_argument('--position',type=int)
        if name in {'create-module','edit-module'}:
            p.add_argument('--unlock-at')
            p.add_argument('--sequential',action=argparse.BooleanOptionalAction,default=None)
            p.add_argument('--prerequisite',type=canvas_id,action='append')
        if name in {'add-module-item','edit-module-item'}:
            p.add_argument('--title')
            p.add_argument('--indent',type=int)
        if name=='add-module-item':
            p.add_argument('--type',choices=['Page','Assignment','File','Discussion','Quiz','ExternalUrl','SubHeader'],required=True)
            p.add_argument('--content-id',type=canvas_id)
            p.add_argument('--page',type=canvas_id)
            p.add_argument('--url')
        if name=='edit-module-item':
            p.add_argument('--item',type=canvas_id,required=True)
            p.add_argument('--move-to-module',type=canvas_id)
            p.add_argument('--completion',choices=['must_view','must_submit','must_contribute','min_score','min_percentage','must_mark_done'])
            p.add_argument('--minimum',type=float)
        if name in {'edit-announcement','reply-discussion'}:
            p.add_argument('--topic',type=canvas_id,required=True)
        if name in {'create-announcement','edit-announcement'}: p.add_argument('--delayed-post-at')
        if name=='create-announcement': p.add_argument('--notify-course',action='store_true')
        if name=='reply-discussion': p.add_argument('--entry',type=canvas_id)
        if name in {'upload-file','submit-assignment'}:
            p.add_argument('--file',type=Path,action='append' if name=='submit-assignment' else 'store')
        if name=='upload-file':
            p.add_argument('--folder',type=canvas_id)
            p.add_argument('--name')
            collision=p.add_mutually_exclusive_group()
            collision.add_argument('--replace',type=canvas_id)
            collision.add_argument('--rename-on-conflict',action='store_true')
            p.add_argument('--verify-content',action='store_true')
        if name=='submit-assignment': p.add_argument('--url')
        if name in {'submit-assignment','comment-submission'}:
            p.add_argument('--comment-file',type=Path,required=name=='comment-submission')
        if name=='submit-assignment':
            p.add_argument('--body-file',type=Path)


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def stable(value):
    if isinstance(value,dict): return {k:stable(v) for k,v in value.items() if k not in VOLATILE}
    if isinstance(value,list): return sorted((stable(v) for v in value),key=canonical)
    return value


def date_input(value, timezone=None):
    if value.lower() in {'none','null','clear'}: return None
    try:
        instant=dt.datetime.fromisoformat(value)
        if instant.tzinfo is None:
            if not timezone: raise ValueError('An explicit UTC offset or --tz is required')
            zone=zoneinfo.ZoneInfo(timezone)
            candidates={instant.replace(tzinfo=zone,fold=f).astimezone(dt.timezone.utc) for f in (0,1) if instant.replace(tzinfo=zone,fold=f).astimezone(dt.timezone.utc).astimezone(zone).replace(tzinfo=None)==instant}
            if len(candidates)!=1: raise ValueError('Local time is nonexistent or ambiguous; supply an explicit offset')
            instant=candidates.pop()
        return instant.astimezone(dt.timezone.utc).isoformat().replace('+00:00','Z')
    except (ValueError,zoneinfo.ZoneInfoNotFoundError) as error:
        raise CanvasError('date_invalid',str(error)) from None


def file_facts(path,name=None):
    if path is None: raise CanvasError('input_invalid','A local --file is required')
    path=Path(path).expanduser().absolute()
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        size=0
        while block:=stream.read(1024*1024): sha.update(block);size+=len(block)
    name=name or path.name
    if not name or any(c in name for c in '/\\\r\n'): raise CanvasError('input_invalid','Upload name must be a plain filename')
    return {'path':str(path),'name':name,'size':size,'sha256':sha.hexdigest(),'content_type':mimetypes.guess_type(name)[0] or 'application/octet-stream'}


def html_normalized(text):
    from bs4 import BeautifulSoup, NavigableString
    soup=BeautifulSoup(text or '', 'html.parser')
    for tag in soup.find_all(True): tag.attrs=dict(sorted(tag.attrs.items()))
    for node in list(soup.find_all(string=True)):
        if isinstance(node,NavigableString) and not node.find_parent(['pre','code']): node.replace_with(re.sub(r'\s+',' ',str(node)))
    return str(soup).strip()


class Builder:
    def __init__(self,reader,args,now=None):
        self.reader,self.client,self.args=reader,reader.client,args
        self.now=now or dt.datetime.now(dt.timezone.utc)
        self.dependencies={}
        self.steps=[]
        self.plan={'command':args.command,'account':{'alias':self.client.account.alias,'origin':self.client.origin,'user_id':self.client.account.user_id},'context':{},'changes':[],'effects':[],'warnings':[]}
        self.base=None

    def get(self,path,params=None):
        value=self.reader.object(path,params)
        self.dependencies[path+'?'+canonical(params or {})]=digest(stable(value))
        return value

    def listing(self,path,params=None):
        result=self.client.paginate(path,params).items
        if not all(isinstance(x,dict) for x in result): raise CanvasError('malformed','Canvas returned an invalid listing')
        self.dependencies[path+'?'+canonical(params or {})]=digest(stable(result))
        return result

    def permission(self,key):
        value=self.plan['permissions'].get(key)
        if value is False: raise CanvasError('permission_denied','Canvas reports '+key+' as false')
        if value is None: self.plan['warnings'].append(key+' is not reported; Canvas decides whether the operation is allowed')

    def context(self):
        from canvas_read import PERMISSIONS, permission_value
        verify_identity(self.client)
        a=self.args
        if getattr(a,'personal',False):
            self.base='/api/v1/users/self';self.plan['context']={'type':'personal'};self.plan['permissions']={};return
        if getattr(a,'group',None):
            self.base='/api/v1/groups/'+a.group
            group=self.get(self.base)
            if id_string(group.get('id'))!=a.group: raise CanvasError('malformed','Canvas returned the wrong group')
            own=self.listing('/api/v1/users/self/groups')
            if not any(id_string(g.get('id'))==a.group for g in own): raise CanvasError('permission_denied','The group is not among this user\'s own groups')
            cid=id_string(group['course_id']) if group.get('course_id') is not None else None
            self.plan['context']={'type':'group','id':a.group,'course_id':cid,'name':group.get('name')}
        else:
            cid=a.course;self.base='/api/v1/courses/'+cid
            self.plan['context']={'type':'course','id':cid,'course_id':cid}
        if cid:
            course=self.get('/api/v1/courses/'+cid,{'include[]':'permissions'})
            if id_string(course.get('id'))!=cid: raise CanvasError('malformed','Canvas returned the wrong course')
            if course.get('workflow_state') in {'completed','deleted'} or (course.get('end_at') and course.get('restrict_enrollments_to_course_dates') and dt.datetime.fromisoformat(course['end_at'])<=self.now):
                raise CanvasError('course_concluded','Writes to a concluded course are refused')
            self.plan['course']={k:course.get(k) for k in ('id','name','workflow_state','time_zone')}
        try:
            permissions=self.get(self.base+'/permissions',{'permissions[]':list(PERMISSIONS)})
        except CanvasError as error:
            if error.kind=='token_rejected' or error.status not in (401,403,404): raise
            permissions={}
            self.dependencies[self.base+'/permissions']=digest({'status':error.status,'kind':error.kind})
            self.plan['warnings'].append('Permission reporting is unavailable; unknown permissions do not establish write readiness')
        self.plan['permissions']={k:permission_value(permissions.get(k)) for k in PERMISSIONS}
        if cid:
            self.plan['permissions'].update({k:permission_value((course.get('permissions') or {}).get(k)) for k in ('create_announcement','create_discussion_topic')})

    def change(self,key,before,after):
        if key in {'body','description','message'}:
            diff='\n'.join(difflib.unified_diff((before or '').splitlines(),(after or '').splitlines(),fromfile='before',tofile='after',lineterm=''))
            self.plan['changes'].append({'field':key,'before_sha256':hashlib.sha256((before or '').encode()).hexdigest(),'after_sha256':hashlib.sha256((after or '').encode()).hexdigest(),'diff':diff,'converted_html':after})
        elif before!=after:
            change={'field':key,'before':before,'after':after}
            if key.endswith('_at'):
                from canvas_export import zone_for,date_text
                zone=zone_for(self.plan.get('course') or {},self.reader.user_zone)
                change.update(time_zone=str(zone),before_local=date_text(before,zone),after_local=date_text(after,zone))
            self.plan['changes'].append(change)

    def body(self,current=''):
        from canvas_html import body_file
        from bs4 import BeautifulSoup
        path=getattr(self.args,'body_file',None)
        if path is None: return None
        if path.suffix.lower()=='.md' and not getattr(self.args,'accept_loss',False):
            soup=BeautifulSoup(current or '','html.parser')
            lost=sorted({tag.name for tag in soup.find_all(['iframe','video','audio','object','embed'])}|{'inline styles' for tag in soup.find_all(style=True)})
            if lost: raise CanvasError('body_loss','Markdown replacement may lose '+', '.join(lost)+'; use HTML or review with --accept-loss')
        return body_file(path)

    def step(self,method,path,fields,expected,resource='id',out=None,**checks):
        encoded={}
        prefix=checks.pop('prefix',None)
        for key,value in fields.items():
            param=f'{prefix}[{key}]' if prefix else key
            if isinstance(value,list) and not param.endswith('[]'): param+='[]'
            encoded[param]='' if value is None else value
        step={'method':method,'path':path,'fields':encoded,'readback':{'path':checks.pop('read_path',path),'fields':expected,'resource':resource,**checks}}
        if out: step['out']=out
        self.steps.append(step)

    def unique(self,rows,key,value):
        if not self.args.allow_duplicate and any(r.get(key)==value for r in rows): raise CanvasError('duplicate','A resource with the same name already exists; inspect before allowing a duplicate')

    def pages(self):
        a=self.args;create=a.command=='create-page';revert=a.command=='revert-page'
        self.permission('manage_wiki_create' if create else 'manage_wiki_update')
        path=self.base+'/pages'
        current={} if create else self.get(path+'/page_id:'+a.page)
        if current and id_string(current.get('page_id'))!=a.page: raise CanvasError('malformed','Canvas returned the wrong page')
        latest=None
        if not create:
            path+='/page_id:'+a.page
            latest=id_string(self.get(path+'/revisions/latest').get('revision_id'))
            self.plan['target']={'page_id':a.page,'latest_revision_id':latest,'title':current.get('title')}
        if revert:
            revision=self.get(path+'/revisions/'+a.revision)
            desired={'body':revision.get('body')}
            if not isinstance(desired['body'],str): raise CanvasError('malformed','Revision body is missing')
            self.change('body',current.get('body'),desired['body'])
            self.plan['effects'].append('Restores the selected page revision; notification behavior for revision reverts is unverified')
            self.step('POST',path+'/revisions/'+a.revision,{},dict(desired,page_id=a.page),resource='revision_id',read_path=path,latest_revision=latest)
            return
        fields={key:getattr(a,key,None) for key in ('title','published','editing_roles','front_page') if getattr(a,key,None) is not None}
        body=self.body(current.get('body'))
        if body is not None: fields['body']=body
        if create:
            fields.setdefault('published',False);fields.setdefault('body','')
            self.unique(self.listing(path),'title',a.title)
        elif not fields: raise CanvasError('input_invalid','No page changes supplied')
        if fields.get('editing_roles') and any(role not in {'teachers','students','members','public'} for role in fields['editing_roles'].split(',')): raise CanvasError('input_invalid','Editing roles must use the documented Canvas role names')
        if fields.get('front_page') and fields.get('published',current.get('published')) is not True: raise CanvasError('input_invalid','A front page must be published; review --published explicitly')
        if fields.get('front_page'):
            try: previous=self.get(self.base+'/front_page')
            except CanvasError as error:
                if error.status!=404: raise
                previous=None
            self.plan['effects'].append('Sets the front page; previous page ID: '+str(previous.get('page_id') if previous else None))
        for key,value in fields.items(): self.change(key,current.get(key),value)
        self.plan['effects'].append('notify_of_update='+str(a.notify).lower())
        fields['notify_of_update']=a.notify
        expected={k:v for k,v in fields.items() if k!='notify_of_update'}
        expected['page_id']='$page.id' if create else a.page
        self.step('POST' if create else 'PUT',path,fields,expected,resource='page_id',out='page' if create else None,prefix='wiki_page',read_path=self.base+'/pages/page_id:$page.id' if create else path,latest_revision=latest)

    def assignments(self):
        a=self.args;create=a.command=='create-assignment'
        self.permission('manage_assignments_add' if create else 'manage_assignments_edit')
        path=self.base+'/assignments'+('' if create else '/'+a.assignment)
        current={} if create else self.get(path,{'include[]':['all_dates','overrides']})
        if not create and id_string(current.get('id'))!=a.assignment: raise CanvasError('malformed','Canvas returned the wrong assignment')
        fields={k:getattr(a,k) for k in ('name','published') if getattr(a,k) is not None}
        for arg,key in (('points','points_possible'),('assignment_group','assignment_group_id'),('submission_type','submission_types')):
            value=getattr(a,arg)
            if value is not None: fields[key]=value
        if a.points is not None and (not math.isfinite(a.points) or a.points<0): raise CanvasError('input_invalid','Points must be a nonnegative finite number')
        if a.assignment_group: self.get(self.base+'/assignment_groups/'+a.assignment_group)
        for key in ('due_at','unlock_at','lock_at'):
            if getattr(a,key) is not None: fields[key]=date_input(getattr(a,key),a.tz)
        dates={k:fields.get(k,current.get(k)) for k in ('unlock_at','due_at','lock_at')}
        present=[dt.datetime.fromisoformat(dates[k]) for k in dates if dates[k]]
        if present!=sorted(present): raise CanvasError('date_invalid','Dates must satisfy available from <= due <= available until')
        body=self.body(current.get('description'))
        if body is not None: fields['description']=body
        if create:
            self.unique(self.listing(path),'name',a.name)
            fields.setdefault('published',False)
        elif not fields: raise CanvasError('input_invalid','No assignment changes supplied')
        if current.get('has_overrides') and any(k in fields for k in ('due_at','unlock_at','lock_at')): self.plan['warnings'].append('Base dates change; existing overrides retain their own dates')
        for key,value in fields.items(): self.change(key,current.get(key),value)
        fields['notify_of_update']=a.notify
        expected={k:v for k,v in fields.items() if k!='notify_of_update'};expected['id']='$assignment.id' if create else a.assignment
        self.plan['effects'].append('notify_of_update='+str(a.notify).lower())
        self.step('POST' if create else 'PUT',path,fields,expected,out='assignment' if create else None,prefix='assignment',read_path=self.base+'/assignments/$assignment.id' if create else path)

    def ordered(self,rows,target,position):
        ids=[id_string(r.get('id')) for r in sorted(rows,key=lambda r:(r.get('position') or 0,id_string(r.get('id')))) if str(r.get('id'))!=target]
        index=len(ids) if position is None else position-1
        if not 0<=index<=len(ids): raise CanvasError('input_invalid','Position is outside this collection')
        ids.insert(index,target)
        return ids

    def modules(self):
        a=self.args;create=a.command=='create-module'
        self.permission('manage_course_content_add' if create else 'manage_course_content_edit')
        collection=self.base+'/modules';rows=self.listing(collection)
        path=collection+('' if create else '/'+a.module)
        current={} if create else self.get(path)
        if current and id_string(current.get('id'))!=a.module: raise CanvasError('malformed','Canvas returned the wrong module')
        fields={key:getattr(a,arg) for arg,key in (('name','name'),('position','position'),('sequential','require_sequential_progress'),('prerequisite','prerequisite_module_ids')) if getattr(a,arg) is not None}
        if a.unlock_at is not None: fields['unlock_at']=date_input(a.unlock_at,a.tz)
        if a.published is not None and not create: fields['published']=a.published
        if create: self.unique(rows,'name',a.name)
        elif not fields: raise CanvasError('input_invalid','No module changes supplied')
        order=self.ordered(rows,'$module.id' if create else a.module,a.position if a.position is not None else current.get('position'))
        prerequisites=fields.get('prerequisite_module_ids',current.get('prerequisite_module_ids') or [])
        before=order[:order.index('$module.id' if create else a.module)]
        if any(p not in before for p in prerequisites): raise CanvasError('input_invalid','Prerequisite modules must precede this module')
        for key,value in fields.items(): self.change(key,current.get(key),value)
        self.plan['effects'].append({'module_order':order})
        expected=dict(fields,id='$module.id' if create else a.module)
        if create: expected['published']=False
        self.step('POST' if create else 'PUT',path,fields,expected,out='module' if create else None,prefix='module',read_path=collection+'/$module.id' if create else path,order={'path':collection,'expected':order})
        if create and a.published:
            self.step('PUT',collection+'/$module.id',{'published':True},{'id':'$module.id','published':True},prefix='module')

    def module_items(self):
        a=self.args;create=a.command=='add-module-item'
        self.permission('manage_course_content_add' if create else 'manage_course_content_edit')
        self.get(self.base+'/modules/'+a.module)
        path=self.base+'/modules/'+a.module+'/items'
        rows=self.listing(path)
        current={} if create else self.get(path+'/'+a.item)
        if current and id_string(current.get('id'))!=a.item: raise CanvasError('malformed','Canvas returned the wrong module item')
        fields={key:getattr(a,key) for key in ('title','position','indent') if getattr(a,key) is not None}
        if a.indent is not None and not 0<=a.indent<=5: raise CanvasError('input_invalid','Indent must be between 0 and 5')
        if create:
            fields['type']=a.type
            if a.type=='Page':
                if not a.page: raise CanvasError('input_invalid','Page items require --page ID')
                resource=self.get(self.base+'/pages/page_id:'+a.page)
                if id_string(resource.get('page_id'))!=a.page: raise CanvasError('malformed','Canvas returned the wrong page')
                fields['page_url']=resource['url']
            elif a.type in {'Assignment','File','Discussion','Quiz'}:
                if not a.content_id: raise CanvasError('input_invalid','This module item requires --content-id')
                endpoint={'Assignment':'assignments','File':'files','Discussion':'discussion_topics','Quiz':'quizzes'}[a.type]
                resource=self.get(self.base+'/'+endpoint+'/'+a.content_id)
                if id_string(resource.get('id'))!=a.content_id: raise CanvasError('malformed','Canvas returned the wrong resource')
                fields['content_id']=a.content_id
            elif a.type=='ExternalUrl':
                if not a.title or not a.url or urlsplit(a.url).scheme not in {'https','http'} or not urlsplit(a.url).netloc: raise CanvasError('input_invalid','ExternalUrl requires --title and an HTTP(S) --url')
                fields['external_url']=a.url
            elif not a.title: raise CanvasError('input_invalid','SubHeader requires --title')
            if not a.allow_duplicate and any(r.get('type')==a.type and (r.get('page_url')==a.page and a.type=='Page' or a.type=='Page' and r.get('page_url')==fields.get('page_url') or a.content_id and str(r.get('content_id'))==a.content_id or a.type=='ExternalUrl' and r.get('external_url')==a.url or a.type=='SubHeader' and r.get('title')==a.title) for r in rows):
                raise CanvasError('duplicate','This content is already referenced in the module')
        else:
            if a.published is not None: fields['published']=a.published
            if a.minimum is not None and a.completion not in {'min_score','min_percentage'}: raise CanvasError('input_invalid','--minimum requires a score or percentage completion rule')
            if a.completion:
                fields['completion_requirement[type]']=a.completion
                if a.completion in {'min_score','min_percentage'}:
                    if a.minimum is None or not math.isfinite(a.minimum) or a.minimum<0: raise CanvasError('input_invalid','A finite nonnegative --minimum is required')
                    fields['completion_requirement['+a.completion+']']=a.minimum
            if a.move_to_module:
                self.get(self.base+'/modules/'+a.move_to_module)
                fields['module_id']=a.move_to_module
                rows=self.listing(self.base+'/modules/'+a.move_to_module+'/items')
            if not fields: raise CanvasError('input_invalid','No module item changes supplied')
        destination=getattr(a,'move_to_module',None) or a.module
        order=self.ordered(rows,'$item.id' if create else a.item,a.position if a.position is not None else current.get('position') if not getattr(a,'move_to_module',None) else None)
        self.plan['effects'].append({'module_item_order':order,'module_id':destination})
        for key,value in fields.items(): self.change(key,current.get(key),value)
        expected={k:v for k,v in fields.items() if not k.startswith('completion_requirement[')}
        if getattr(a,'completion',None):
            expected['completion_requirement']={'type':a.completion}
            if a.minimum is not None: expected['completion_requirement'][a.completion]=a.minimum
        expected.update(id='$item.id' if create else a.item)
        self.step('POST' if create else 'PUT',path if create else path+'/'+a.item,fields,expected,out='item' if create else None,prefix='module_item',read_path=self.base+'/modules/'+destination+'/items/'+('$item.id' if create else a.item),order={'path':self.base+'/modules/'+destination+'/items','expected':order})
        if create and a.type=='Page':
            self.steps[-1]['readback']['page_reference']={'path':self.base+'/pages/'+quote(resource['url'],safe=''),'page_id':a.page}
        # Rails nested keys need the bracket inside the outer module_item wrapper.
        step=self.steps[-1]
        for key in list(step['fields']):
            if '[completion_requirement[' in key: step['fields'][key.replace('[completion_requirement[','[completion_requirement][')[:-1]]=step['fields'].pop(key)

    def announcements(self):
        a=self.args;create=a.command=='create-announcement'
        self.permission('create_announcement' if create else 'moderate_forum')
        path=self.base+'/discussion_topics'
        rows=self.listing(path,{'only_announcements':True})
        current={} if create else next((r for r in rows if id_string(r.get('id'))==a.topic),None)
        if current is None: raise CanvasError('input_invalid','This topic is not a visible announcement')
        if not create:
            path+='/'+a.topic
            current=self.get(path)
            if id_string(current.get('id'))!=a.topic: raise CanvasError('malformed','Canvas returned the wrong announcement')
            posted=current.get('posted_at');delayed=current.get('delayed_post_at')
            if (posted and dt.datetime.fromisoformat(posted)<=self.now) or (delayed and dt.datetime.fromisoformat(delayed)<=self.now): raise CanvasError('announcement_posted','Posted announcements cannot be edited by this tool')
        body=self.body(current.get('message'))
        if create and body is None: raise CanvasError('input_invalid','Announcement creation requires --body-file')
        fields={}
        if a.title is not None: fields['title']=a.title
        if body is not None: fields['message']=body
        if a.delayed_post_at is not None: fields['delayed_post_at']=date_input(a.delayed_post_at,a.tz)
        if create:
            fields['is_announcement']=True
            if not a.allow_duplicate and any(r.get('title')==a.title and html_normalized(r.get('message'))==html_normalized(body) for r in rows): raise CanvasError('duplicate','This announcement already exists')
        elif not fields: raise CanvasError('input_invalid','No announcement changes supplied')
        for key,value in fields.items(): self.change(key,current.get(key),value)
        self.plan['effects'].append('Announcement can notify course members; creation execution requires --notify-course')
        expected={k:v for k,v in fields.items() if k!='is_announcement'};expected['id']='$announcement.id' if create else a.topic
        self.step('POST' if create else 'PUT',path,fields,expected,out='announcement' if create else None,read_path=self.base+'/discussion_topics/$announcement.id' if create else path,announcement=True)

    def upload_step(self,facts,path,folder=None,replace=None,rename=False,out='file',verify_content=False):
        fields={'name':facts['name'],'size':facts['size'],'content_type':facts['content_type'],'on_duplicate':'overwrite' if replace else 'rename'}
        if folder: fields['parent_folder_id']=folder
        self.steps.append({'method':'POST','path':path,'fields':fields,'upload':facts,'out':out,'replace':replace,'rename':rename,'verify_content':verify_content,'readback':{'path':'/api/v1/files/$'+out+'.id','fields':{'size':facts['size'],'content-type':facts['content_type'],**({'folder_id':folder} if folder else {})},'resource':'id'}})

    def uploads(self):
        a=self.args
        if not getattr(a,'personal',False): self.permission('manage_files_add')
        facts=file_facts(a.file,a.name)
        if a.folder:
            folder=self.get(self.base+'/folders/'+a.folder)
            if id_string(folder.get('id'))!=a.folder: raise CanvasError('malformed','Canvas returned the wrong folder')
        rows=self.listing(self.base+'/files')
        matches=[r for r in rows if r.get('display_name')==facts['name'] and (not a.folder or str(r.get('folder_id'))==a.folder)]
        if a.replace:
            if len(matches)!=1 or id_string(matches[0].get('id'))!=a.replace: raise CanvasError('duplicate','--replace must name the exact existing file in this destination')
            self.permission('manage_files_edit')
        elif matches and not a.rename_on_conflict: raise CanvasError('duplicate','A file with this name exists; choose --replace ID or --rename-on-conflict')
        if self.plan.get('course'):
            try:
                quota=self.get(self.base+'/files/quota');self.plan['quota']=quota
                if isinstance(quota.get('quota'),int) and isinstance(quota.get('quota_used'),int):
                    quota['remaining_bytes']=max(0,quota['quota']-quota['quota_used'])
                    if facts['size']>quota['remaining_bytes']: self.plan['warnings'].append('File exceeds the reported remaining course quota; Canvas decides whether it can be stored')
            except CanvasError as error:
                if error.status not in (401,403,404): raise
                self.plan['warnings'].append('Course file quota is not visible')
        self.plan['changes'].append({'field':'upload','file':facts,'replace_file_id':a.replace,'rename_on_conflict':a.rename_on_conflict})
        self.upload_step(facts,self.base+'/files',a.folder,a.replace,a.rename_on_conflict,verify_content=a.verify_content)

    def submission(self):
        a=self.args;path=self.base+'/assignments/'+a.assignment
        assignment=self.get(path,{'include[]':['submission','all_dates'],'override_assignment_dates':True})
        if id_string(assignment.get('id'))!=a.assignment: raise CanvasError('malformed','Canvas returned the wrong assignment')
        submission=self.get(path+'/submissions/self',{'include[]':'submission_comments'})
        if submission.get('user_id') is not None and id_string(submission['user_id'])!=self.client.account.user_id: raise CanvasError('malformed','Canvas returned another user\'s submission')
        comment=a.comment_file.read_text(encoding='utf-8') if a.comment_file else None
        comments=submission.get('submission_comments') or []
        comments=sorted(comments,key=lambda c:(c.get('created_at') or '',len(str(c.get('id') or '')),str(c.get('id') or '')))
        self.plan['recent_comments']=[{k:c.get(k) for k in ('id','author_id','comment','created_at')} for c in comments[-5:]]
        own=[c for c in comments if str(c.get('author_id'))==self.client.account.user_id]
        if comment is not None and own and own[-1].get('comment')==comment: raise CanvasError('duplicate','This is already the user\'s latest submission comment')
        if a.command=='comment-submission':
            if not comment: raise CanvasError('input_invalid','Comment cannot be empty')
            self.plan['changes'].append({'field':'submission_comment','text':comment})
            self.plan['effects'].append('Comment is visible to the instructor and may notify participants')
            self.step('PUT',path+'/submissions/self',{'comment[text_comment]':comment},{},read_path=path+'/submissions/self',comment=comment)
            return
        for field,test in (('unlock_at',lambda t:t>self.now),('lock_at',lambda t:t<=self.now)):
            if assignment.get(field) and test(dt.datetime.fromisoformat(assignment[field])): raise CanvasError('assignment_locked','Assignment is outside its availability window')
        if assignment.get('locked_for_user'): raise CanvasError('assignment_locked','Assignment is locked for this user')
        attempt=int(submission.get('attempt') or 0);allowed=assignment.get('allowed_attempts')
        if allowed is not None and allowed>=0 and attempt>=allowed: raise CanvasError('attempts_exhausted','No submission attempts remain')
        if sum(bool(x) for x in (a.body_file,a.url,a.file))!=1: raise CanvasError('input_invalid','Choose exactly one submission: --body-file, --url, or --file')
        kind='online_text_entry' if a.body_file else 'online_url' if a.url else 'online_upload'
        if kind not in (assignment.get('submission_types') or []): raise CanvasError('submission_type_refused','Assignment does not accept this submission type')
        fields={'submission[submission_type]':kind}
        expected={'submission_type':kind,'attempt':attempt+1}
        if a.body_file:
            from canvas_html import body_file
            body=body_file(a.body_file);fields['submission[body]']=body;expected['body']=body
            self.change('body',submission.get('body'),body)
        elif a.url:
            if urlsplit(a.url).scheme not in {'http','https'} or not urlsplit(a.url).netloc: raise CanvasError('input_invalid','Submission URL must use HTTP(S)')
            fields['submission[url]']=a.url;expected['url']=a.url
            self.change('url',submission.get('url'),a.url)
        else:
            files=[file_facts(p) for p in a.file]
            for index,facts in enumerate(files): self.upload_step(facts,path+'/submissions/self/files',out='attachment'+str(index))
            fields['submission[file_ids][]']=['$attachment'+str(i)+'.id' for i in range(len(files))]
            self.plan['changes'].append({'field':'submission_files','files':files})
            expected['attachments']=[{'id':'$attachment'+str(i)+'.id','display_name':f['name'],'size':f['size']} for i,f in enumerate(files)]
        if comment: fields['comment[text_comment]']=comment
        due=assignment.get('due_at')
        self.plan['submission']={'attempts_used':attempt,'allowed_attempts':allowed,'due_at':due,'unlock_at':assignment.get('unlock_at'),'lock_at':assignment.get('lock_at'),'late':bool(due and dt.datetime.fromisoformat(due)<self.now),'submission_type':kind}
        from canvas_export import zone_for,date_text
        zone=zone_for(self.plan.get('course') or {},self.reader.user_zone)
        self.plan['submission'].update(time_zone=str(zone),**{k+'_local':date_text(assignment.get(k+'_at'),zone) for k in ('due','unlock','lock')})
        self.plan['effects'].append('Uses an attempt, is visible to the instructor and cannot be withdrawn; notifications may occur')
        self.step('POST',path+'/submissions',fields,expected,read_path=path+'/submissions/self',comment=comment)

    def discussion(self):
        a=self.args;self.permission('post_to_forum')
        path=self.base+'/discussion_topics/'+a.topic
        topic=self.get(path)
        if topic.get('locked') or topic.get('locked_for_user'): raise CanvasError('discussion_locked','Discussion is locked')
        try: view=self.get(path+'/view',{'include_new_entries':True})
        except CanvasError as error:
            initial_hidden=topic.get('require_initial_post') is True and topic.get('user_can_see_posts') is False
            if error.status!=403 or not (initial_hidden or 'require_initial_post' in str(error)) or a.entry: raise
            view={'view':[],'new_entries':[]}
        entries=[];pending=list(view.get('view') or [])+list(view.get('new_entries') or [])
        while pending:
            entry=pending.pop();entries.append(entry);pending.extend(entry.get('replies') or [])
        body=self.body()
        if not body: raise CanvasError('input_invalid','Discussion reply requires --body-file')
        if any(str(e.get('user_id'))==self.client.account.user_id and html_normalized(e.get('message'))==html_normalized(body) for e in entries): raise CanvasError('duplicate','The user has already posted this message in the topic')
        if a.entry and not any(str(e.get('id'))==a.entry for e in entries): raise CanvasError('input_invalid','The entry being answered was not found')
        self.plan['target']={'topic_id':a.topic,'title':topic.get('title'),'entry_id':a.entry,'audience':'members of this '+self.plan['context']['type']}
        if a.entry:
            answered=next(e for e in entries if str(e.get('id'))==a.entry)
            self.plan['target']['reply_to']={k:answered.get(k) for k in ('id','user_id','message')}
        self.change('message','',body)
        self.plan['effects'].append('Reply is visible to participants and may notify them')
        write_path=path+'/entries'+('/'+a.entry+'/replies' if a.entry else '')
        self.step('POST',write_path,{'message':body},{'message':body,'id':'$entry.id'},out='entry',read_path=path+'/entry_list',entry_list=True)

    def build(self):
        self.context()
        self.plan['target']={key+'_id':getattr(self.args,key) for key in ('page','assignment','module','item','topic','folder','replace','revision') if getattr(self.args,key,None) is not None}
        command=self.args.command
        if command in PAGE_COMMANDS: self.pages()
        elif command in {'create-assignment','edit-assignment'}: self.assignments()
        elif command in {'create-module','edit-module'}: self.modules()
        elif command in {'add-module-item','edit-module-item'}: self.module_items()
        elif command in {'create-announcement','edit-announcement'}: self.announcements()
        elif command=='upload-file': self.uploads()
        elif command in {'submit-assignment','comment-submission'}: self.submission()
        else: self.discussion()
        self.plan['dependencies']=self.dependencies
        def describe(step):
            public={k:v for k,v in step.items() if k not in {'upload','readback','fields'}}
            public['fields']={k:({'bytes':len(v.encode()),'sha256':hashlib.sha256(v.encode()).hexdigest()} if isinstance(v,str) and any(x in k for x in ('[body]','[description]','[text_comment]')) or k=='message' and isinstance(v,str) else v) for k,v in step['fields'].items()}
            public['readback']={**step['readback'],'fields':list(step['readback']['fields'])}
            if 'comment' in public['readback']: public['readback']['comment']='verify own comment text'
            return public
        self.plan['steps']=[describe(step) for step in self.steps]
        self.plan['preview_hash']=digest({'plan':self.plan,'steps':self.steps})
        return self


def substitute(value,variables):
    if isinstance(value,str):
        def replace(match):
            key=match[1]+'.id'
            if key not in variables: raise CanvasError('plan_invalid','A created-resource reference is unresolved')
            return variables[key]
        return re.sub(r'\$([a-z0-9]+)\.id',replace,value)
    if isinstance(value,list): return [substitute(x,variables) for x in value]
    if isinstance(value,dict): return {k:substitute(v,variables) for k,v in value.items()}
    return value


def matches(actual,expected,key=''):
    if isinstance(expected,dict): return isinstance(actual,dict) and all(matches(actual.get(k),v,k) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(actual,list) and len(actual)==len(expected) and all(any(matches(a,e,key) for a in actual) for e in expected)
    if isinstance(expected,bool): return actual is expected
    if expected is not None and (key=='id' or key.endswith('_id')): return str(actual)==str(expected)
    if key.endswith('_at') and actual and expected:
        try: return dt.datetime.fromisoformat(actual)==dt.datetime.fromisoformat(expected)
        except (ValueError,TypeError): return False
    return actual==expected


class Executor:
    def __init__(self,builder,history,upload_sender=None,downloader=None):
        self.builder,self.reader,self.client,self.history=builder,builder.reader,builder.client,history
        self.variables={key+'.id':str(getattr(builder.args,key)) for key in ('page','assignment','module','item','topic','folder','replace','revision') if getattr(builder.args,key,None) is not None}
        self.sent=0;self.verified=[];self.warnings=[]
        self.operation=uuid.uuid4().hex
        self.upload_sender=upload_sender
        self.downloader=downloader
        self.active_record=None
        self.current_step=0
        self.phase='before_send'

    def journal(self,outcome,**extra):
        self.history.now=dt.datetime.now(dt.timezone.utc)
        row={'schema_version':1,'record_id':uuid.uuid4().hex,'operation_id':self.operation,'time':self.history.now.isoformat().replace('+00:00','Z'),'account':self.client.account.alias,'kind':'write','command':self.builder.args.command,'preview_hash':self.builder.plan['preview_hash'],'course_ids':[self.builder.plan['context']['course_id']] if self.builder.plan['context'].get('course_id') else [],'outcome':outcome,'target_ids':sorted(set(self.variables.values())),'steps':[{'step':self.current_step}],**extra}
        self.history._append(row)
        return row['record_id']

    def request(self,method,path,fields=None,custom=None):
        self.current_step+=1
        record=self.journal('uncertain',steps=[{'step':self.current_step,'method':method,'path':urlsplit(path).path if path.startswith('/') else 'upload-storage'}])
        self.active_record=record
        self.sent+=1
        self.phase='sending'
        result=custom() if custom else parse_json(self.client.request(method,path,data=fields))
        self.phase='after_send'
        # Readback for a multi-request upload is deferred until all three requests complete.
        return result,record

    def resolved(self,record,outcome='verified',**more):
        self.journal(outcome,resolves=record,**more)
        self.active_record=None

    def readback(self,step):
        check=substitute(step['readback'],self.variables)
        if check.get('entry_list'):
            entries=self.client.paginate(check['path'],{'ids[]':check['fields']['id']}).items
            record=next((x for x in entries if str(x.get('id'))==check['fields']['id']),None)
            if record is None: raise CanvasError('readback_mismatch','New discussion entry was not found on readback')
        else:
            params={'include[]':'submission_comments'} if '/submissions/self' in check['path'] else None
            record=self.reader.object(check['path'],params)
        warnings=[]
        for key,value in check['fields'].items():
            if key in {'body','description','message'}:
                if not isinstance(record.get(key),str): raise CanvasError('readback_mismatch','Readback omitted the HTML field '+key)
                if html_normalized(record.get(key))!=html_normalized(value):
                    warnings.append({'field':key,'outcome':'verified_with_sanitizer_changes','diff':''.join(difflib.unified_diff((value or '').splitlines(True),(record.get(key) or '').splitlines(True),fromfile='sent',tofile='readback'))})
            elif not matches(record.get(key),value,key): raise CanvasError('readback_mismatch','Readback differs for '+key)
        if check.get('comment'):
            found=any(str(c.get('author_id'))==self.client.account.user_id and c.get('comment')==check['comment'] for c in record.get('submission_comments') or [])
            if not found: raise CanvasError('readback_mismatch','Submitted comment was not found on readback')
        if check.get('latest_revision'):
            latest=self.reader.object(check['path']+'/revisions/latest')
            rid=id_string(latest.get('revision_id'))
            if rid==check['latest_revision']: raise CanvasError('readback_mismatch','Page revision did not advance')
            self.variables['revision.id']=rid
            self.variables['prior_revision.id']=check['latest_revision']
        if check.get('page_reference'):
            referenced=self.reader.object(check['page_reference']['path'])
            if id_string(referenced.get('page_id'))!=check['page_reference']['page_id']: raise CanvasError('readback_mismatch','Module page reference resolves to a different page ID')
        if check.get('announcement'):
            rows=self.client.paginate(self.builder.base+'/discussion_topics',{'only_announcements':True}).items
            if not any(str(x.get('id'))==str(record.get('id')) for x in rows): raise CanvasError('readback_mismatch','Created topic is not in the announcements listing')
        if check.get('order'):
            rows=self.client.paginate(check['order']['path']).items
            order=[id_string(x.get('id')) for x in sorted(rows,key=lambda r:(r.get('position') or 0,id_string(r.get('id'))))]
            if order!=check['order']['expected']: raise CanvasError('readback_mismatch','Collection order differs on readback')
        self.warnings.extend(warnings)
        return record

    def upload(self,step):
        from canvas_upload import send_upload
        from canvas_export import download
        import tempfile
        facts=step['upload']
        if file_facts(facts['path'],facts['name'])!=facts: raise CanvasError('local_file_changed','Upload file changed after the reviewed plan')
        pending,first=self.request('POST',step['path'],step['fields'])
        if not isinstance(pending,dict): raise CanvasError('malformed','Canvas returned no upload instructions')
        self.resolved(first)
        response,second=self.request('POST','upload-storage',custom=lambda:(self.upload_sender or send_upload)(pending.get('upload_url'),pending.get('upload_params'),facts['path'],facts['name'],facts['content_type']))
        if response.status not in (200,201,301,302,303,307,308):
            raise CanvasError('upload_failed','Upload service refused the file',status=response.status)
        location=response.header('location')
        if not location: raise CanvasError('upload_uncertain','Upload service supplied no confirmation location')
        location=self.client.check_api_url(urljoin(self.client.origin+'/',location))
        # Confirmation is a GET that finalizes the upload, so it is journaled as a write and sent without retry.
        metadata,third=self.request('GET',location,custom=lambda:parse_json(self.client.transport.send('GET',location,{'Accept':'application/json+canvas-string-ids'},token=self.client._token)))
        if not isinstance(metadata,dict): raise CanvasError('malformed','Upload confirmation returned no file')
        fid=id_string(metadata.get('id'));self.variables[step['out']+'.id']=fid
        if step.get('replace') and fid!=step['replace']: raise CanvasError('readback_mismatch','Replacement returned a different file ID')
        if not step.get('rename') and metadata.get('display_name')!=facts['name']: raise CanvasError('readback_mismatch','Uploaded filename differs from the plan')
        record=self.readback(step)
        if step.get('verify_content'):
            with tempfile.TemporaryDirectory() as root:
                evidence=(self.downloader or download)(self.client,record,Path(root).resolve()/'content')
            if evidence['sha256']!=facts['sha256']: raise CanvasError('readback_mismatch','Uploaded content digest differs')
        if file_facts(facts['path'],facts['name'])!=facts: raise CanvasError('upload_uncertain','Local file changed during upload')
        self.resolved(second)
        self.resolved(third)
        return record

    def run(self):
        try:
            with self.history.locked():
                self.history.compress()
                self.journal('started')
                for original in self.builder.steps:
                    step={**original,'path':substitute(original['path'],self.variables),'fields':substitute(original['fields'],self.variables)}
                    try:
                        if 'upload' in step:
                            record=self.upload(step)
                        else:
                            response,pending=self.request(step['method'],step['path'],step['fields'])
                            if step.get('out'):
                                if not isinstance(response,dict): raise CanvasError('malformed','Canvas returned no created resource')
                                self.variables[step['out']+'.id']=id_string(response.get(step['readback']['resource']))
                            record=self.readback(step)
                            self.resolved(pending,'verified_with_sanitizer_changes' if self.warnings else 'verified')
                        self.verified.append({'step':len(self.verified)+1,'id':str(record.get('page_id') or record.get('id') or ''),'readback':'verified'})
                    except Exception as error:
                        known_refusal=isinstance(error,CanvasError) and error.status in {400,401,403,404,409,422,429} and self.active_record is not None and self.phase=='sending'
                        if known_refusal:
                            try: self.resolved(self.active_record,'not_landed')
                            except OSError: known_refusal=False
                        partial=bool(self.verified) or self.sent>1 or (self.sent>0 and not known_refusal)
                        return {'mode':'executed','outcome':'PARTIAL or uncertain' if partial else 'refused','preview_hash':self.builder.plan['preview_hash'],'writes_sent':self.sent,'verified_steps':self.verified,'target_ids':self.variables,'uncertain_step':self.current_step if partial else None,'error_kind':error.kind if isinstance(error,CanvasError) else 'transport_or_history_error','warnings':self.warnings},3 if partial else 1
                self.journal('verified')
        except OSError:
            if self.sent: return {'mode':'executed','outcome':'PARTIAL or uncertain','writes_sent':self.sent,'verified_steps':self.verified,'error_kind':'history_unwritable'},3
            raise CanvasError('history_unwritable','Write history is unavailable; no writes sent') from None
        return {'mode':'executed','outcome':'verified_with_sanitizer_changes' if self.warnings else 'verified','preview_hash':self.builder.plan['preview_hash'],'writes_sent':self.sent,'verified_steps':self.verified,'target_ids':self.variables,'warnings':self.warnings},0


def run_write(reader,args,history,now=None,upload_sender=None,downloader=None):
    if args.execute and (not args.expect or not re.fullmatch(r'[0-9a-f]{64}',args.expect)):
        raise CanvasError('preview_required','Execution requires the reviewed preview hash in --expect; no writes sent')
    builder=Builder(reader,args,now).build()
    if not args.execute:
        try: history.record(account=reader.client.account.alias,command=args.command,kind='write',course_ids=[builder.plan['context']['course_id']] if builder.plan['context'].get('course_id') else [],preview_hash=builder.plan['preview_hash'],outcome='preview')
        except (OSError,CanvasError):
            print('WARNING: Preview history is unavailable; execution requires writable history.',file=sys.stderr)
        return {'mode':'preview',**builder.plan,'writes_sent':0},0
    if args.expect!=builder.plan['preview_hash']: raise CanvasError('preview_stale','Fresh reads differ from the reviewed plan; no writes sent')
    if args.command=='create-announcement' and not args.notify_course: raise CanvasError('notification_ack_required','Execution requires --notify-course; no writes sent')
    return Executor(builder,history,upload_sender,downloader).run()
