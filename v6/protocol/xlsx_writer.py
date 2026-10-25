from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import math,xml.etree.ElementTree as E

def write_workbook(output_path,sheets):
    MAIN='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    PKG='http://schemas.openxmlformats.org/package/2006/relationships'
    CT='http://schemas.openxmlformats.org/package/2006/content-types'
    E.register_namespace('',MAIN); E.register_namespace('r',REL)
    def tag(name):return '{'+MAIN+'}'+name
    def xml(root):return E.tostring(root,encoding='utf-8',xml_declaration=True)
    def col(n):
     out=''
     while n:
      n,r=divmod(n-1,26);out=chr(65+r)+out
     return out
    styles=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{MAIN}"><fonts count="3"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Microsoft YaHei"/></font><font><color rgb="FF0563C1"/><u/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF2F6FA"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left style="thin"><color rgb="FFD8E1EB"/></left><right style="thin"><color rgb="FFD8E1EB"/></right><top style="thin"><color rgb="FFD8E1EB"/></top><bottom style="thin"><color rgb="FFD8E1EB"/></bottom><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'''
    wb=E.Element(tag('workbook')); views=E.SubElement(wb,tag('bookViews'));E.SubElement(views,tag('workbookView'),activeTab='0');ws=E.SubElement(wb,tag('sheets'))
    wrels=E.Element('Relationships',xmlns=PKG)
    types=E.Element('Types',xmlns=CT)
    E.SubElement(types,'Default',Extension='rels',ContentType='application/vnd.openxmlformats-package.relationships+xml')
    E.SubElement(types,'Default',Extension='xml',ContentType='application/xml')
    E.SubElement(types,'Override',PartName='/xl/workbook.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    E.SubElement(types,'Override',PartName='/xl/styles.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')
    rootrels=E.Element('Relationships',xmlns=PKG);E.SubElement(rootrels,'Relationship',Id='rId1',Type=REL+'/officeDocument',Target='xl/workbook.xml')
    out=Path(output_path)
    out.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
     z.writestr('_rels/.rels',xml(rootrels));z.writestr('xl/styles.xml',styles)
     for idx,(name,headers,rows,widths) in enumerate(sheets,1):
      E.SubElement(ws,tag('sheet'),name=name,sheetId=str(idx),attrib={'{'+REL+'}id':f'rId{idx}'})
      E.SubElement(wrels,'Relationship',Id=f'rId{idx}',Type=REL+'/worksheet',Target=f'worksheets/sheet{idx}.xml')
      E.SubElement(types,'Override',PartName=f'/xl/worksheets/sheet{idx}.xml',ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
      root=E.Element(tag('worksheet'));E.SubElement(root,tag('dimension'),ref=f'A1:{col(len(headers))}{len(rows)+1}')
      sv=E.SubElement(E.SubElement(root,tag('sheetViews')),tag('sheetView'),workbookViewId='0',showGridLines='0')
      E.SubElement(sv,tag('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
      E.SubElement(root,tag('sheetFormatPr'),defaultRowHeight='18')
      cols=E.SubElement(root,tag('cols'))
      for j,w in enumerate(widths,1):E.SubElement(cols,tag('col'),min=str(j),max=str(j),width=str(w),customWidth='1')
      data=E.SubElement(root,tag('sheetData'));links=[]
      for rn,values in enumerate([headers]+rows,1):
       lines=1
       for value,w in zip(values,widths):
        parts=str(value).split('\n');lines=max(lines,sum(max(1,math.ceil(sum(2 if ord(ch)>127 else 1 for ch in part)/(w-2))) for part in parts))
       row=E.SubElement(data,tag('row'),r=str(rn),ht=str(32 if rn==1 else min(220,max(32,lines*17+8))),customHeight='1')
       for cn,value in enumerate(values,1):
        value=str(value);addr=f'{col(cn)}{rn}';isurl=value.startswith('https://') and '\n' not in value
        style='1' if rn==1 else ('3' if isurl else ('2' if rn%2==0 else '0'))
        c=E.SubElement(row,tag('c'),r=addr,t='inlineStr',s=style)
        text=E.SubElement(E.SubElement(c,tag('is')),tag('t'));text.set('{http://www.w3.org/XML/1998/namespace}space','preserve');text.text=value
        if isurl:links.append((addr,value))
      E.SubElement(root,tag('autoFilter'),ref=f'A1:{col(len(headers))}{len(rows)+1}')
      if links:
       hs=E.SubElement(root,tag('hyperlinks'));rels=E.Element('Relationships',xmlns=PKG)
       for li,(addr,url) in enumerate(links,1):
        E.SubElement(hs,tag('hyperlink'),ref=addr,attrib={'{'+REL+'}id':f'rId{li}'})
        E.SubElement(rels,'Relationship',Id=f'rId{li}',Type=REL+'/hyperlink',Target=url,TargetMode='External')
       z.writestr(f'xl/worksheets/_rels/sheet{idx}.xml.rels',xml(rels))
      E.SubElement(root,tag('pageMargins'),left='0.25',right='0.25',top='0.5',bottom='0.5',header='0.2',footer='0.2')
      E.SubElement(root,tag('pageSetup'),orientation='landscape',paperSize='9',fitToWidth='1',fitToHeight='0')
      z.writestr(f'xl/worksheets/sheet{idx}.xml',xml(root))
     E.SubElement(wrels,'Relationship',Id='rIdStyles',Type=REL+'/styles',Target='styles.xml')
     z.writestr('xl/workbook.xml',xml(wb));z.writestr('xl/_rels/workbook.xml.rels',xml(wrels));z.writestr('[Content_Types].xml',xml(types))
    with ZipFile(out) as z:
     assert z.testzip() is None
     for name in z.namelist():
      if name.endswith(('.xml','.rels')):E.fromstring(z.read(name))
     for idx,(_,headers,rows,_) in enumerate(sheets,1):
      root=E.fromstring(z.read(f'xl/worksheets/sheet{idx}.xml'))
      assert len(root.findall('s:sheetData/s:row',{'s':MAIN}))==len(rows)+1
    print('OUTPUT',out)
    print('SHEETS',[(name,len(rows)) for name,headers,rows,widths in sheets])
    print('VALIDATED: ZIP integrity, every XML/rels part, worksheet row counts; original preserved')
