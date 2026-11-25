"""Read one XLSX cell from an independent download; never rewrite package bytes."""
import json, posixpath, sys, zipfile
import xml.etree.ElementTree as ET
NS = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
file, sheet, address = sys.argv[1:]
with zipfile.ZipFile(file) as z:
    infos=z.infolist()
    if len(infos)>10000 or sum(i.file_size for i in infos)>64000000 or len({i.filename for i in infos})!=len(infos):
        raise ValueError('Unsafe or oversized XLSX package')
    def xml(name):
        raw=z.read(name)
        if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw: raise ValueError('Unsupported XML')
        return ET.fromstring(raw)
    wb=xml('xl/workbook.xml')
    matches=[n for n in wb.findall('s:sheets/s:sheet',NS) if n.get('name')==sheet]
    if len(matches)!=1: raise ValueError('Unknown or ambiguous sheet')
    rid=matches[0].get('{'+NS['r']+'}id')
    rels=[n for n in xml('xl/_rels/workbook.xml.rels') if n.get('Id')==rid and n.get('TargetMode')!='External']
    if len(rels)!=1: raise ValueError('Missing worksheet relationship')
    part=posixpath.normpath(posixpath.join('xl',rels[0].get('Target'))).lstrip('/')
    if not part.startswith('xl/'): raise ValueError('Invalid sheet part')
    root=xml(part)
    cells=[n for n in root.findall('s:sheetData/s:row/s:c',NS) if n.get('r')==address]
    if len(cells)>1: raise ValueError('Duplicate cell')
    result={'text':'','runs':[], 'formula':False}
    if cells:
        c=cells[0];result['formula']=c.find('s:f',NS) is not None
        base_color=None
        if 'xl/styles.xml' in z.namelist():
            styles=xml('xl/styles.xml')
            xfs=styles.find('s:cellXfs',NS)
            fonts=styles.find('s:fonts',NS)
            if xfs is not None and fonts is not None:
                xf=xfs[int(c.get('s','0'))]
                base_color=fonts[int(xf.get('fontId','0'))].find('s:color',NS)
        if c.get('t')=='s':
            strings=xml('xl/sharedStrings.xml').findall('s:si',NS)
            node=strings[int(c.findtext('s:v',namespaces=NS))]
        elif c.get('t')=='inlineStr':node=c.find('s:is',NS)
        else:node=None
        if node is not None:
            runs=node.findall('s:r',NS)
            if runs:
                for run in runs:
                    color=run.find('s:rPr/s:color',NS)
                    if color is None: color=base_color
                    rgb=color.get('rgb') if color is not None else None
                    result['runs'].append({'text':run.findtext('s:t',default='',namespaces=NS),'font':{'color':'#'+rgb[-6:] if rgb else None}})
                result['text']=''.join(r['text'] for r in result['runs'])
            else: result['text']=node.findtext('s:t',default='',namespaces=NS)
        elif c.find('s:v',NS) is not None: raise ValueError('Non-text cell')
    print(json.dumps(result))
