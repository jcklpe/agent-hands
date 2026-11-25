"""Verify exact saved threaded-comment text and cell anchors without modifying XLSX."""
import json,posixpath,sys,zipfile,xml.etree.ElementTree as ET
n={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships','t':'http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments'}
expected=json.load(open(sys.argv[2]));found={}
with zipfile.ZipFile(sys.argv[1]) as z:
 if sum(x.file_size for x in z.infolist())>64000000:raise ValueError('Workbook expansion exceeds bound')
 rels={r.get('Id'):posixpath.normpath('xl/'+r.get('Target')) for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
 for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',n):
  f=rels[s.get('{'+n['r']+'}id')];rp=posixpath.dirname(f)+'/_rels/'+posixpath.basename(f)+'.rels'
  if rp not in z.namelist():continue
  for r in ET.fromstring(z.read(rp)):
   if 'threadedComment' not in r.get('Type',''):continue
   for c in ET.fromstring(z.read(posixpath.normpath(posixpath.dirname(f)+'/'+r.get('Target')))):
    t=c.find('t:text',n);found.setdefault((s.get('name'),c.get('ref')),[]).append(''.join(t.itertext()) if t is not None else '')
missing=[{'sheet':x['sheet'],'cell':x['cell']} for x in expected if x['content'] not in found.get((x['sheet'],x['cell']),[])]
print(json.dumps({'status':'saved_comments_verified' if not missing else 'saved_comments_unverified','expected':len(expected),'verified':len(expected)-len(missing),'missing':missing,'replayAllowed':False}))
