"""Read-only XLSX preservation and layout checks, using the standard library."""
import copy
import json
import posixpath
import re
import sys
import zipfile
import xml.etree.ElementTree as E

N = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main', 'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def snapshot(file):
    with zipfile.ZipFile(file) as z:
        if len(z.infolist()) > 10000 or sum(i.file_size for i in z.infolist()) > 64000000:
            raise ValueError('Oversized package')
        def xml(p):
            raw = z.read(p)
            if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
                raise ValueError('Unsupported XML')
            return E.fromstring(raw)
        def tree(e):
            return [e.tag, dict(sorted(e.attrib.items())), e.text or '', [tree(c) for c in e]]
        def resolve(base, target):
            return posixpath.normpath(posixpath.join(posixpath.dirname(base), target)).lstrip('/')
        wb = xml('xl/workbook.xml')
        relationships = {r.get('Id'): resolve('xl/workbook.xml', r.get('Target')) for r in xml('xl/_rels/workbook.xml.rels')}
        strings = list(xml('xl/sharedStrings.xml')) if 'xl/sharedStrings.xml' in z.namelist() else []
        styles = xml('xl/styles.xml')
        xfs, fonts, fills = [list(styles.find('m:'+tag, N)) for tag in ['cellXfs', 'fonts', 'fills']]
        result = {'order': [], 'sheets': {}, 'comments': {}}
        for s in wb.findall('m:sheets/m:sheet', N):
            name = s.get('name'); result['order'].append(name)
            part = relationships[s.get('{'+N['r']+'}id')]; root = xml(part)
            relpart = posixpath.dirname(part)+'/_rels/'+posixpath.basename(part)+'.rels'
            rels = {r.get('Id'): r for r in xml(relpart)} if relpart in z.namelist() else {}
            cells = {}
            for c in root.findall('m:sheetData/m:row/m:c', N):
                xf = xfs[int(c.get('s', '0'))]; font = fonts[int(xf.get('fontId', '0'))]
                t = c.get('t'); f = c.find('m:f', N)
                node = strings[int(c.findtext('m:v', namespaces=N))] if t == 's' else c.find('m:is', N) if t == 'inlineStr' else None
                value = ''.join(node.itertext()) if node is not None else c.findtext('m:v', default='', namespaces=N)
                if f is not None: value = None
                alignment = xf.find('m:alignment', N)
                cells[c.get('r')] = {'value': value, 'formula': tree(f) if f is not None else None, 'rich': tree(node) if node is not None and node.find('m:r', N) is not None else None, 'font': tree(font), 'fill': tree(fills[int(xf.get('fillId', '0'))]), 'alignment': dict(alignment.attrib) if alignment is not None else {}}
            tab = root.find('m:sheetPr/m:tabColor', N); pane = root.find('m:sheetViews/m:sheetView/m:pane', N)
            tables = {}
            for entry in root.findall('m:tableParts/m:tablePart', N):
                rel = rels[entry.get('{'+N['r']+'}id')]; table = xml(resolve(part, rel.get('Target')))
                info = table.find('m:tableStyleInfo', N)
                tables[table.get('name')] = {'ref': table.get('ref'), 'columns': tree(table.find('m:tableColumns', N)), 'style': info.get('name') if info is not None else None, 'bandedRows': info.get('showRowStripes') in ['1', 'true'] if info is not None else False}
            links = {h.get('ref'): rels[h.get('{'+N['r']+'}id')].get('Target') for h in root.findall('m:hyperlinks/m:hyperlink', N) if h.get('{'+N['r']+'}id') in rels}
            result['sheets'][name] = {'cells': cells, 'tabColor': tab.get('rgb')[-6:].upper() if tab is not None and tab.get('rgb') else None, 'pane': dict(pane.attrib) if pane is not None else None, 'tables': tables, 'links': links, 'merges': [m.get('ref') for m in root.findall('m:mergeCells/m:mergeCell', N)]}
        for part in z.namelist():
            if re.match(r'xl/(comments[^/]*\.xml|comments/[^/]+\.xml|threadedComments/[^/]+\.xml)$', part):
                result['comments'][part] = tree(xml(part))
        return result


def verify(before, after, spec):
    before = copy.deepcopy(before)
    issues = []
    def coordinates(address):
        m = re.fullmatch(r'([A-Z]+)([0-9]+)', address)
        col = 0
        for letter in m[1]: col = col * 26 + ord(letter) - 64
        return col, int(m[2])
    def address(col, row):
        letters = ''
        while col:
            col, rem = divmod(col - 1, 26); letters = chr(65 + rem) + letters
        return letters + str(row)
    for change in spec['tables']:
        if not change.get('removeColumns') and not change.get('removeRows'): continue
        matches = [(s, s['tables'][change['name']]) for s in before['sheets'].values() if change['name'] in s['tables']]
        if len(matches) != 1:
            issues.append('missing structural target'); continue
        sheet, table = matches[0]
        c1, r1 = coordinates(table['ref'].split(':')[0]); c2, r2 = coordinates(table['ref'].split(':')[1])
        columns = table['columns'][3]
        removed_cols = {c1 + i for i, c in enumerate(columns) if c[1].get('name') in change.get('removeColumns', [])}
        removed_rows = {r1 + 1 + i for i in change.get('removeRows', [])}
        moved = {}
        for cell, value in list(sheet['cells'].items()):
            c, r = coordinates(cell)
            if c1 <= c <= c2 and r1 <= r <= r2:
                del sheet['cells'][cell]
                if c not in removed_cols and r not in removed_rows:
                    moved[address(c - sum(x < c for x in removed_cols), r - sum(x < r for x in removed_rows))] = value
        sheet['cells'].update(moved)
        table['ref'] = address(c1, r1) + ':' + address(c2 - len(removed_cols), r2 - len(removed_rows))
        table['columns'][3] = [c for i, c in enumerate(columns) if c1 + i not in removed_cols]
        table['columns'][1]['count'] = str(len(table['columns'][3]))
    edits = {(x['sheet'], x['cell']): x for x in spec['cells']}
    if set(before['sheets']) != set(after['sheets']): issues.append('sheet identities changed')
    if before['comments'] != after['comments']: issues.append('comment parts changed; inspect independently')
    for name, old in before['sheets'].items():
        new = after['sheets'].get(name, {})
        for address in set(old['cells']) | set(new.get('cells', {})):
            a = old['cells'].get(address, {'value': '', 'formula': None, 'rich': None})
            b = new.get('cells', {}).get(address, {'value': '', 'formula': None, 'rich': None})
            edit = edits.get((name, address))
            if b['value'] != (edit['after'] if edit else a['value']) or b['formula'] != a['formula']: issues.append(name+'!'+address+' content differs')
            if not edit and a['rich'] != b['rich']: issues.append(name+'!'+address+' rich text changed')
        if old['links'] != new.get('links'): issues.append(name+' hyperlinks changed')
        unmerged = {r['range'] for r in spec['ranges'] if r['sheet']==name and r.get('unmerge')}
        if [m for m in old['merges'] if m not in unmerged] != new.get('merges'): issues.append(name+' merged ranges changed')
        for table, prior in old['tables'].items():
            current = new.get('tables', {}).get(table, {})
            def definition(node):
                if not node: return node
                return [node[0], {k:v for k,v in node[1].items() if not k.endswith('DxfId')}, node[2], [definition(c) for c in node[3]]]
            if prior['ref'] != current.get('ref') or definition(prior['columns']) != definition(current.get('columns')): issues.append(table+' definition changed')
    for s in spec['sheets']:
        state = after['sheets'].get(s['sheet'], {})
        if 'position' in s and after['order'].index(s['sheet']) != s['position']: issues.append(s['sheet']+' order unverified')
        if 'tabColor' in s and state.get('tabColor') != s['tabColor'][1:].upper(): issues.append(s['sheet']+' color unverified')
        if 'freeze' in s:
            pane = state.get('pane')
            if s['freeze'] is None and pane is not None: issues.append(s['sheet']+' unfrozen state unverified')
            if s['freeze'] and (not pane or pane.get('state') != 'frozen'): issues.append(s['sheet']+' freeze unverified')
    tables = {k:v for s in after['sheets'].values() for k,v in s['tables'].items()}
    for t in spec['tables']:
        current = tables.get(t['name'], {})
        if current.get('style') != t['style'] or current.get('bandedRows') != t['bandedRows']: issues.append(t['name']+' style unverified')
    # Range formatting is checked separately through the native readback; preservation and target sheet/table changes are checked here.
    return {'status': 'saved_layout_verified' if not issues else 'saved_layout_unverified', 'issues': issues[:30], 'issueCount': len(issues), 'rangeVisualAcceptanceRequired': True, 'replayAllowed': False}


if __name__ == '__main__':
    if sys.argv[1] == 'snapshot': print(json.dumps(snapshot(sys.argv[2])))
    else: print(json.dumps(verify(json.load(open(sys.argv[2])), snapshot(sys.argv[3]), json.load(open(sys.argv[4])))))
