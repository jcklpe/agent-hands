#!/usr/bin/env python3
"""Stateful synthetic Trello transport; never performs network requests."""
import json, os, sys
from pathlib import Path
args=sys.argv[1:]; root=Path(os.environ['TRELLO_TEST_STATE']); state=json.loads(root.read_text()); method='GET'; fields={}; path=''
for i,arg in enumerate(args):
    if arg == '-X': method=args[i+1]
    elif arg == '--data-urlencode':
        key,_,value=args[i+1].partition('=');fields[key]=value
    elif arg.startswith('https://api.trello.com/1'):path=arg.split('https://api.trello.com/1',1)[1]
fields.pop('key',None);fields.pop('token',None)
request={'method':method,'path':path,'fields':fields}
with Path(str(root)+'.requests').open('a') as f:f.write(json.dumps(request)+'\n')
def save():root.write_text(json.dumps(state))
def fail():save();sys.exit(22)
def output(value):save();print(json.dumps(value));sys.exit(0)
def select(value):
    if not isinstance(value,dict):return value
    keys=fields.get('fields','').split(',')
    return {k:v for k,v in value.items() if not fields.get('fields') or k in keys or k=='id'}
def ident(ref):return state.get('aliases',{}).get(ref,ref)
def new_id():
    state['sequence']+=1;return f"{state['sequence']:024x}"
parts=path.strip('/').split('/');kind=parts[0];key=ident(parts[1]) if len(parts)>1 else None
if method=='GET':
    signature=json.dumps(request,sort_keys=True);count=state.setdefault('reads',{}).get(signature,0)+1;state['reads'][signature]=count
    if state.get('race') and kind=='cards' and len(parts)==2 and count>=2:state['cards'][key]['name']='Concurrent edit'
    if state.get('readback_fail') and state.get('writes',0):fail()
    if kind=='cards':
        card=state['cards'].get(key)
        if not card:fail()
        if len(parts)==2:output(select(card))
        if parts[2]=='checklists':output([dict(c,checkItems=state['items'].get(c['id'],[])) for c in state['checklists'].values() if c['idCard']==key])
        if parts[2]=='actions':output(state['comments'].get(key,[]))
    elif kind=='lists' and len(parts)==2:output(select(state['lists'][key]))
    elif kind=='labels' and len(parts)==2:
        if key not in state['labels']:fail()
        output(select(state['labels'][key]))
    elif kind=='boards':
        if len(parts)==2:output(select(state['boards'][key]))
        if parts[2]=='lists':output([select(x) for x in state['lists'].values() if x['idBoard']==key])
        if parts[2]=='labels':output([select(x) for x in state['labels'].values() if x['idBoard']==key])
    elif kind=='checklists':
        if key not in state['checklists']:fail()
        if len(parts)==2:output(select(state['checklists'][key]))
        if parts[2]=='checkItems':output(state['items'].get(key,[]))
    raise SystemExit('Unexpected fixture GET '+path)
state['writes']=state.get('writes',0)+1
if state.get('fail_write')==state['writes']:fail()
result={}
if method=='POST' and path=='/cards':
    key=new_id();result=dict(fields,id=key,idBoard=state['lists'][fields['idList']]['idBoard'],closed=False,start=None,idLabels=[],url='https://trello.com/c/'+key);state['cards'][key]=result
elif kind=='cards':
    card=state['cards'][key]
    if len(parts)==2 and method=='PUT':card.update(fields);result=card
    elif parts[2]=='idLabels':
        label=fields.get('value') if method=='POST' else parts[3]
        if method=='POST' and label not in card['idLabels']:card['idLabels'].append(label)
        elif method=='DELETE':card['idLabels']=[x for x in card['idLabels'] if x!=label]
        result=card['idLabels']
    elif parts[2]=='actions':
        result={'id':new_id(),'date':'2026-01-01T00:00:00Z','data':{'text':fields['text']}};state['comments'].setdefault(key,[]).insert(0,result)
    elif parts[2]=='checkItem':
        for checklist in state['checklists'].values():
            if checklist['idCard']==key:
                for item in state['items'].get(checklist['id'],[]):
                    if item['id']==parts[3]:item.update(fields);result=item
elif path=='/checklists' and method=='POST':
    key=new_id();result=dict(fields,id=key,pos=len(state['checklists'])+1);state['checklists'][key]=result;state['items'][key]=[]
elif kind=='checklists' and parts[2]=='checkItems' and method=='POST':
    result={'id':new_id(),'name':fields['name'],'pos':len(state['items'][key])+1,'state':'incomplete'};state['items'][key].append(result)
elif path=='/labels' and method=='POST':
    key=new_id();result=dict(fields,id=key,color=fields.get('color') or None);state['labels'][key]=result
elif kind=='labels' and method=='DELETE':
    state['labels'].pop(key)
    for card in state['cards'].values():card['idLabels']=[x for x in card['idLabels'] if x!=key]
else:raise SystemExit('Unexpected fixture mutation '+method+' '+path)
if method=='DELETE' and state.get('empty_delete_response'):save();sys.exit(0)
if state.get('invalid_response'):output({'unexpected':'response'})
output(result)
