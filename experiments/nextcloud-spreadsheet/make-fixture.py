from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.worksheet.table import Table,TableStyleInfo
from openpyxl.cell.rich_text import CellRichText,TextBlock
from openpyxl.cell.text import InlineFont
from pathlib import Path
p=Path('/private/tmp/spreadsheet-engines');p.mkdir(exist_ok=True)
w=Workbook();s=w.active;s.title='Review'
s.append(['ID','Answer','Amount'])
s.append(['R001','Original wording',7]);s.append(['R002','Unchanged answer',11])
s['B2'].comment=Comment('Synthetic source note. Preserve this.','Fixture')
s['B3'].hyperlink='https://example.com/source';s['B3'].style='Hyperlink'
s.add_table(Table(displayName='ReviewData',ref='A1:C3'))
s['E1']='Formula control';s['E2']='=SUM(C2:C3)'
s['B5']=CellRichText(TextBlock(InlineFont(color='FFC00000'),'Old '),TextBlock(InlineFont(color='FF008000'),'New'))
s.column_dimensions['B'].width=40
w.create_sheet('Providers').append(['Provider','Synthetic organization'])
w.save(p/'baseline.xlsx')
print(p/'baseline.xlsx')
