#!/usr/bin/env python3
"""Bind investigation claims to exact release-source bytes and bounded excerpts."""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from suite import DIMENSIONS, ROOT, load_matrix, require, unique_object

REGISTRY=ROOT/'evaluation/design/source-investigations.json'


def validate_registry(registry,target):
    require(registry['schema_version']==1 and registry['product']=='openclaw','Expected source investigation schema')
    require(registry['source_commit']==target['source_commit'],'Source analysis must use the active campaign commit')
    sources=registry['sources']
    ids={s['id'] for s in sources}
    require(len(ids)==len(sources) and sources,'Duplicate or empty source bindings')
    for source in sources:
        require(re.fullmatch(r'(?:src/[A-Za-z0-9_./-]+\.ts|VISION\.md)',source['path']) and '..' not in Path(source['path']).parts,'Source path must stay inside the upstream code/design tree')
        require(re.fullmatch(r'[a-f0-9]{64}',source['sha256']),'Full source SHA-256 required')
        require(source['anchors'],'Source symbol/line anchors required')
        for anchor in source['anchors']:
            require(type(anchor['start']) is int and type(anchor['end']) is int and 1<=anchor['start']<=anchor['end'] and anchor['end']-anchor['start']<100,'Bounded positive source range required')
            require(anchor['symbol'],'Source symbol or ownership purpose required')
    findings=registry['investigations']
    require(len({f['id'] for f in findings})==len(findings) and findings,'Unique source investigations required')
    for finding in findings:
        require(finding['source_ids'] and set(finding['source_ids'])<=ids,'Unknown source binding in finding')
        require(finding['phenomenon'] and finding['hypotheses'] and finding['falsifiers'] and finding['followups'],'Observation, hypothesis, counterevidence and followup required')
        require(set(finding['dimensions'])==set(DIMENSIONS),'Every finding must consider the six reporting axes')
        require(finding['status']=='source-bound-followup-required','Registry records preregistered hypotheses, not automatic product conclusions')
    return registry


def load_registry():
    return validate_registry(json.loads(REGISTRY.read_text(),object_pairs_hook=unique_object),load_matrix()['target'])


def collect_one(source,commit):
    url='https://raw.githubusercontent.com/openclaw/openclaw/'+commit+'/'+source['path']
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'OpenClaw-architecture-evaluation'}),timeout=35) as response:
        data=response.read(2*1024**2+1)
    require(len(data)<=2*1024**2,'Source module exceeds collection bound')
    require(hashlib.sha256(data).hexdigest()==source['sha256'],'Pinned source bytes changed: '+source['path'])
    lines=data.decode().splitlines()
    anchors=[]
    for anchor in source['anchors']:
        require(anchor['end']<=len(lines),'Source range exceeds module')
        anchors.append(dict(**anchor,url='https://github.com/openclaw/openclaw/blob/'+commit+'/'+source['path']+f'#L{anchor["start"]}-L{anchor["end"]}',
                            text='\n'.join(lines[anchor['start']-1:anchor['end']])))
    return dict(id=source['id'],path=source['path'],sha256=source['sha256'],full_module_bytes=len(data),anchors=anchors)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        registry=load_registry()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            sources=list(pool.map(lambda s:collect_one(s,registry['source_commit']),registry['sources']))
        result=dict(kind='pinned-source-anchors',source_commit=registry['source_commit'],sources=sources,
                    upstream_license='MIT',license_url='https://github.com/openclaw/openclaw/blob/'+registry['source_commit']+'/LICENSE',
                    limitation='Matching source explains a possible mechanism; an experiment and counterevidence are still required for causal effects and cross-dimension tradeoffs.')
        encoded=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
        require(len(encoded)<=200*1024,'Source excerpts exceed the 200 KiB retention budget')
        args.output.write_bytes(encoded)
        print(json.dumps(dict(output=str(args.output),bytes=len(encoded),modules=len(sources))))
    except (ValueError,KeyError,TypeError,OSError) as error:
        parser.exit(1,f'FAIL: {error}\n')


if __name__=='__main__':
    main()
