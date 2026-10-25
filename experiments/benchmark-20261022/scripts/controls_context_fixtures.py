import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'fixtures/extended-context';D.mkdir(parents=True,exist_ok=True)
cases=[]
for context in [32000,128000]:
 for size in [20000,100000,500000]:
  for alphabet,unit in [('ascii','sample data abcdefghijklmnopqrstuvwxyz\n'),('unicode','中英文测试🙂 sample数据段落\n')]:
   name=f'{context}-{size}-{alphabet}';content=(unit*(size//len(unit)+1))[:size]
   markers={p:f'BENCH_{p.upper()}_{hashlib.sha256((name+p).encode()).hexdigest()[:16]}' for p in ['head','middle','tail']}
   for p,start in [('head',0),('middle',size//2),('tail',size-len(markers['tail'])-9)]:
    marker=markers[p];content=content[:start]+marker+content[start+len(marker):]
   content=content[:-8]+'summary\n'
   file=D/f'{name}.txt';file.write_text(content)
   cases.append(dict(name=name,context=context,codepoints=len(content),utf8_bytes=len(content.encode()),alphabet=alphabet,path=str(file),sha256=hashlib.sha256(content.encode()).hexdigest(),markers=markers))
(D/'manifest.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
print(json.dumps({'cases':len(cases),'bytes':sum(x['utf8_bytes'] for x in cases)}))
