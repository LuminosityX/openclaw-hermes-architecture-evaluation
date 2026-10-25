"""Small review workbook using stdlib OOXML; no additional installations."""
import json,zipfile
from pathlib import Path
from xml.etree import ElementTree as E

R=Path('/root/output/oc-hermes-execution-20261024-v6')
S='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
E.register_namespace('',S);E.register_namespace('r',REL)

def q(name):return '{'+S+'}'+name
def xml(node):
    # Conventional default namespaces for each package part also work with
    # readers whose OPC relationship discovery ignores prefixed root names.
    E.register_namespace('',node.tag.split('}')[0].removeprefix('{'))
    return E.tostring(node,encoding='utf-8',xml_declaration=True)
def letters(n):
    text=''
    while n:n,r=divmod(n-1,26);text=chr(65+r)+text
    return text

def sheet(rows,widths,rich=False):
    root=E.Element(q('worksheet'))
    views=E.SubElement(root,q('sheetViews'));v=E.SubElement(views,q('sheetView'),workbookViewId='0')
    E.SubElement(v,q('pane'),ySplit='1',topLeftCell='A2',activePane='bottomLeft',state='frozen')
    cols=E.SubElement(root,q('cols'))
    for i,w in enumerate(widths,1):E.SubElement(cols,q('col'),min=str(i),max=str(i),width=str(w),customWidth='1')
    data=E.SubElement(root,q('sheetData'))
    colors={'强':'FF11754C','中':'FF805800','弱':'FFB42318','未定档':'FF68737D'}
    for i,values in enumerate(rows,1):
        row=E.SubElement(data,q('row'),r=str(i),ht='38' if i==1 else ('112' if rich else '68'),customHeight='1')
        for j,value in enumerate(values,1):
            cell=E.SubElement(row,q('c'),r=letters(j)+str(i),s='1' if i==1 else '2',t='inlineStr');inline=E.SubElement(cell,q('is'))
            if isinstance(value,tuple):
                grade,reason=value;r=E.SubElement(inline,q('r'));fmt=E.SubElement(r,q('rPr'));E.SubElement(fmt,q('b'));E.SubElement(fmt,q('color'),rgb=colors.get(grade,'FF68737D'));E.SubElement(r,q('t')).text=grade+'：'
                E.SubElement(E.SubElement(inline,q('r')),q('t')).text=reason
            else:E.SubElement(inline,q('t')).text=str(value)
    E.SubElement(root,q('autoFilter'),ref='A1:'+letters(len(widths))+str(len(rows)))
    return xml(root)

def styles():
    root=E.Element(q('styleSheet'));fonts=E.SubElement(root,q('fonts'),count='2')
    for bold in [False,True]:
        f=E.SubElement(fonts,q('font'));E.SubElement(f,q('sz'),val='11');E.SubElement(f,q('name'),val='Calibri')
        if bold:E.SubElement(f,q('b'));E.SubElement(f,q('color'),rgb='FFFFFFFF')
    fills=E.SubElement(root,q('fills'),count='3')
    for pat in ['none','gray125']:E.SubElement(E.SubElement(fills,q('fill')),q('patternFill'),patternType=pat)
    fill=E.SubElement(E.SubElement(fills,q('fill')),q('patternFill'),patternType='solid');E.SubElement(fill,q('fgColor'),rgb='FF22364D')
    borders=E.SubElement(root,q('borders'),count='2');E.SubElement(borders,q('border'));b=E.SubElement(borders,q('border'))
    for side in ['left','right','top','bottom']:E.SubElement(E.SubElement(b,q(side),style='thin'),q('color'),rgb='FFD2D9E2')
    base=E.SubElement(root,q('cellStyleXfs'),count='1');E.SubElement(base,q('xf'),numFmtId='0',fontId='0',fillId='0',borderId='0')
    xfs=E.SubElement(root,q('cellXfs'),count='3')
    for font,fill,border in [(0,0,0),(1,2,1),(0,0,1)]:
        xf=E.SubElement(xfs,q('xf'),numFmtId='0',fontId=str(font),fillId=str(fill),borderId=str(border),xfId='0',applyAlignment='1');E.SubElement(xf,q('alignment'),vertical='top',wrapText='1')
    named=E.SubElement(root,q('cellStyles'),count='1');E.SubElement(named,q('cellStyle'),name='Normal',xfId='0',builtinId='0')
    return xml(root)

def main():
    matrix=json.loads((R/'results/eleven-dimensions-review.json').read_text());rows=[['维度','OpenClaw 2026.10.6','Hermes Agent 0.22.5']]
    for x in matrix['rows']:rows.append([x['dimension'],(x['openclaw_grade'] or '未定档',x['openclaw_reason']),(x['hermes_grade'] or '未定档',x['hermes_reason'])])
    notes=[['字段','审阅说明'],['范围','两产品、固定版本下的 Linux CLI 与完整 Gateway；不代表五产品归一化或完整桌面/移动家族排名。'],['模型','真实推理均为 DeepSeek Flash high；固定协议响应只验证原生机制，不替代模型质量实验。'],['真实模型样本','48 次首次交付、16 次对抗任务、36 次复用执行；复用含12次训练、24次新交付，不是100个独立新业务任务。'],['观测样本','36个原始观测配置；另有6个会话片段关闭能力补测及同一原始单元的工具阶段断采控制，不膨胀原始独立样本数。'],['分档','按冻结33子项、权重、效应门槛和证据门禁折算。已知权重至少80%；未知项保留最坏/最好边界；净优势区间完全≥25/≤-25才定强/弱，完全在(-25,25)内定双方中。'],['定量规则','通常至少6个独立配对簇，2000次分层bootstrap；时间/资源实质门槛20%，费用10%，区间需支持方向；等效需要整个区间落入等效带。'],['同级含义','中可表示已验证的相当或优势互相抵消，不表示能力完全相同；未测或未能区分的整体档位不自动填中。'],['费用边界','费用依据完整API用量日志与固定单价估算，含辅助调用、失败、重试和训练摊销；不宣称已逐笔核对服务商扣费发票。'],['资源成本待定','默认混合权重下模型费用差异尚不确定；预先登记的内存优先口径支持OpenClaw弱/Hermes强，不替换主评分。'],['可移植性待定','Linux改逻辑路径迁移与依赖重建已测；Windows包已准备，原生Windows执行结果尚待回传，不能把文档支持当实测通过。'],['审计口径纠正','主评分采用冻结共同事件关联要求；把精确单次/会话授权选择另列为更严格需求。此前严格解释被放进主表，现已纠正并保留完整审阅记录。'],['人工审阅','作者已按原生数据与固定源码复核；同事尚未审核签认。'],['协议与计分器','../../oc-hermes-formal-design-20261024/protocol_v1.json；../../oc-hermes-formal-design-20261024/score_protocol.py'],['完整证据入口','eleven-dimensions-review.html；final-grades.json；../evidence/source-architecture-index.json']]
    notes.insert(7,['架构因果标记','支持句写成架构机制→有条件的典型表现。†表示结构已核实，但其解释首字、吞吐或内存差异的主导贡献尚未独立分解；MCP连接锁的串行效应已有直接对照。'])
    notes.insert(8,['资源机制边界','独立V8 Worker与共享解释器线程、Agent复用提供了资源成本取舍的机制解释；Worker可共享部分缓冲区，heap上限不等于分配量，不能据此声称已完整定位内存差距或语言固有优劣。'])
    evidence=[['维度','可判别权重','净优势区间（OC-H）','主要原生证据']]
    for x in matrix['rows']:evidence.append([x['dimension'],str(x['coverage'])+'%',str(x['interval']),'\n'.join(x['evidence'])])
    sheets=[('11维对比',rows,[23,73,73],True),('评分与边界',notes,[27,140],False),('证据索引',evidence,[25,18,24,112],False)]
    contents=E.Element('{http://schemas.openxmlformats.org/package/2006/content-types}Types')
    for ext,typ in [('rels','application/vnd.openxmlformats-package.relationships+xml'),('xml','application/xml')]:E.SubElement(contents,'{http://schemas.openxmlformats.org/package/2006/content-types}Default',Extension=ext,ContentType=typ)
    for part,typ in [('/xl/workbook.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'),('/xl/styles.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml')]+[(f'/xl/worksheets/sheet{i}.xml','application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml') for i in range(1,len(sheets)+1)]:E.SubElement(contents,'{http://schemas.openxmlformats.org/package/2006/content-types}Override',PartName=part,ContentType=typ)
    wb=E.Element(q('workbook'));ss=E.SubElement(wb,q('sheets'));rels=E.Element('{'+PKG+'}Relationships')
    for i,(name,_,_,_) in enumerate(sheets,1):E.SubElement(ss,q('sheet'),name=name,sheetId=str(i),attrib={'{'+REL+'}id':f'rId{i}'});E.SubElement(rels,'{'+PKG+'}Relationship',Id=f'rId{i}',Type=REL+'/worksheet',Target=f'worksheets/sheet{i}.xml')
    E.SubElement(rels,'{'+PKG+'}Relationship',Id=f'rId{len(sheets)+1}',Type=REL+'/styles',Target='styles.xml')
    rootrels=E.Element('{'+PKG+'}Relationships');E.SubElement(rootrels,'{'+PKG+'}Relationship',Id='rId1',Type=REL+'/officeDocument',Target='xl/workbook.xml')
    output=R/'results/OpenClaw_Hermes_11维实验对比.xlsx'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',xml(contents));z.writestr('_rels/.rels',xml(rootrels));z.writestr('xl/workbook.xml',xml(wb));z.writestr('xl/_rels/workbook.xml.rels',xml(rels));z.writestr('xl/styles.xml',styles())
        for i,(_,values,widths,rich) in enumerate(sheets,1):z.writestr(f'xl/worksheets/sheet{i}.xml',sheet(values,widths,rich))
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        for file in z.namelist():E.fromstring(z.read(file))
        main=E.fromstring(z.read('xl/worksheets/sheet1.xml'))
        assert len(main.findall('.//'+q('row')))==12
        text=''.join(main.itertext())
        for x in matrix['rows']:assert x['dimension'] in text and x['openclaw_reason'] in text and x['hermes_reason'] in text
    print('REVIEW_WORKBOOK_READY',output,output.stat().st_size)

if __name__=='__main__':main()
