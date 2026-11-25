"""Compare effective character formatting before/after native hyperlink edits."""
import importlib.util
import json
import pathlib
import sys
module = importlib.util.spec_from_file_location('layout', pathlib.Path(__file__).with_name('layout-readback.py'))
layout = importlib.util.module_from_spec(module)
module.loader.exec_module(layout)


def chars(cell, ignore_strike=False):
    def font(tree, base=None):
        out = dict(base or {})
        if base and tree[0].endswith('}rPr'):
            # An explicit run font defaults omitted toggles to off. Only a run without rPr inherits the complete cell font.
            for key in ['b', 'i', 'strike', 'outline', 'shadow', 'condense', 'extend', 'u', 'vertAlign']:
                out.pop(key, None)
        for tag, attrs, text, children in tree[3]:
            tag = tag.split('}')[-1]
            if tag in ['family', 'charset', 'scheme']: continue
            if ignore_strike and tag == 'strike': continue
            if tag == 'rFont': tag = 'name'
            value = attrs.get('val', '1') if tag != 'color' else attrs
            if tag in ['b','i','strike','outline','shadow','condense','extend']:
                value = value not in ['0','false','off']
                if not value: out.pop(tag, None);continue
            if tag == 'sz': value = float(value)
            if tag == 'u' and value == 'none': out.pop(tag,None);continue
            out[tag] = value
        return out
    base = font(cell['font'])
    if not cell['rich']: return [(c,base) for c in (cell['value'] or '')]
    result = []
    for node in cell['rich'][3]:
        tag=node[0].split('}')[-1]
        if tag=='t': result.extend((c,base) for c in node[2]);continue
        if tag!='r': continue
        prop=next((x for x in node[3] if x[0].endswith('}rPr')),None)
        fmt=font(prop,base) if prop else base
        value=''.join(x[2] for x in node[3] if x[0].endswith('}t'))
        result.extend((c,fmt) for c in value)
    return result


def verify(before, after, items):
    issues=[];targets={(x['sheet'],x['cell']):x for x in items}
    if before['order']!=after['order'] or before['comments']!=after['comments']:issues.append('sheets or comments changed')
    for name,old in before['sheets'].items():
        new=after['sheets'].get(name,{})
        if old['tables']!=new.get('tables') or old['merges']!=new.get('merges'):issues.append(name+' tables or merges changed')
        expected_links=dict(old['links'])
        for (sheet,address),x in targets.items():
            if sheet==name and x['newAddress'] is not None:expected_links[address]=x['newAddress']
        if new.get('links')!=expected_links:issues.append(name+' hyperlink mismatch')
        for address,a in old['cells'].items():
            b=new.get('cells',{}).get(address);x=targets.get((name,address))
            if not b:issues.append(name+'!'+address+' disappeared');continue
            if a['formula']!=b['formula']:issues.append(name+'!'+address+' formula changed')
            if not x:
                if a!=b:issues.append(name+'!'+address+' unexpected cell change')
                continue
            expected=chars(a,x.get('allowStrikeRemoval',False))
            for r in x['replacements']:
                text=''.join(c for c,f in expected);start=text.index(r['before']);fmt=expected[start][1]
                expected=expected[:start]+[(c,fmt) for c in r['after']]+expected[start+len(r['before']):]
            if expected!=chars(b,x.get('allowStrikeRemoval',False)):issues.append(name+'!'+address+' text or character formatting differs')
    return {'status':'saved_references_verified' if not issues else 'saved_references_unverified','count':len(items),'issues':issues[:20],'issueCount':len(issues),'replayAllowed':False}


if __name__=='__main__':print(json.dumps(verify(json.load(open(sys.argv[1])),layout.snapshot(sys.argv[2]),json.load(open(sys.argv[3])))))
