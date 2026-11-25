"""Verify saved cell hyperlink destinations without modifying workbook bytes."""
import json,posixpath,sys,zipfile,xml.etree.ElementTree as E
n={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
expected=json.load(open(sys.argv[2]));found={}
with zipfile.ZipFile(sys.argv[1]) as z:
 if sum(x.file_size for x in z.infolist())>64000000:raise ValueError('Workbook expansion exceeds bound')
 rels={r.get('Id'):posixpath.normpath('xl/'+r.get('Target')) for r in E.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
 for s in E.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',n):
  f=rels[s.get('{'+n['r']+'}id')];rp=posixpath.dirname(f)+'/_rels/'+posixpath.basename(f)+'.rels'
  if rp not in z.namelist():continue
  links={r.get('Id'):r.get('Target') for r in E.fromstring(z.read(rp))}
  for h in E.fromstring(z.read(f)).findall('m:hyperlinks/m:hyperlink',n):found[(s.get('name'),h.get('ref'))]=links.get(h.get('{'+n['r']+'}id'))
missing=[{'sheet':x['sheet'],'cell':x['cell']} for x in expected if found.get((x['sheet'],x['cell']))!=x['newAddress']]
print(json.dumps({'status':'saved_links_verified' if not missing else 'saved_links_unverified','expected':len(expected),'verified':len(expected)-len(missing),'missing':missing,'replayAllowed':False}))
