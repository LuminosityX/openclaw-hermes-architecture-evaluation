"""Synthetic privacy canaries across native input, recall, export and deletion."""
import base64
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import time
import zlib

from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'SEC-08-S{i:02}':name for i,name in enumerate(['prompt-attachment','memory-recall','redaction','delete-backup','cross-session'],1)}


def png_canary(marker):
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!IIBBBBB',1,1,8,6,0,0,0))+chunk(b'tEXt',b'Comment\x00'+marker.encode())+chunk(b'IDAT',zlib.compress(b'\x00\x00\x00\x00\xff'))+chunk(b'IEND',b'')


def wire(root,operations,role=None):
    spec=root/'privacy-wire.json';pilot.save(spec,dict(shared_token=pilot.TOKEN,operations=operations,role=role))
    result=subprocess.run([pilot.NODE,'/driver/trace_access_probe.mjs',str(spec)],capture_output=True,text=True,timeout=85)
    if not result.stdout.strip():raise RuntimeError('Native privacy wire did not return bounded output')
    report=json.loads(result.stdout)
    if result.returncode or report.get('harness_error'):raise RuntimeError('Native privacy wire failed: '+json.dumps(report)[:1800])
    return report


def history(root,session,role=None):
    return wire(root,[dict(method='chat.history',params=dict(sessionKey=session,limit=100,maxBytes=262144,toolResultMaxChars=32000))],role)


def request(gateway,token,session,private_prompt=None,attachment=None):
    text='Execute the deterministic operation for '+token+(('\nPrivate user note: '+private_prompt) if private_prompt else '')
    content=text if not attachment else [dict(type='text',text=text),dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode(attachment).decode()))]
    connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=40);begin=time.monotonic_ns()
    try:
        connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content=content)])),
            {'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':session})
        response=connection.getresponse();raw=response.read(512*1024+1)
        if len(raw)>512*1024:raise RuntimeError('Native privacy response exceeded bound')
        data=json.loads(raw);answer=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]))
        return dict(status=response.status,accepted='ACCEPTED:'+token in answer,latency_ms=(time.monotonic_ns()-begin)/1e6,response_excerpt=raw.decode(errors='replace')[:1200])
    finally:connection.close()


def configure(root,mode,canary):
    config=service.configure(root)
    config['tools']['allow'].extend(['read','sessions_history','sessions_search'])
    config['tools']['fs']=dict(workspaceOnly=True)
    config['tools']['sessions']=dict(visibility='self')
    if mode=='prompt-attachment':config['models']['providers']['fixture']['models'][0]['input']=['text','image']
    (root/'workspace/private-memory.txt').write_text(canary+'\n')
    if mode=='memory-recall':(root/'workspace/MEMORY.md').write_text('Owned synthetic private memory: '+canary+'\n')
    if mode=='redaction':
        config['logging']['redactPatterns']=['SYNTHETIC_SECRET_[A-F0-9]{40}']
        plugin=root/'composition-a/index.js';s=plugin.read_text().replace(' const owner="composition-a";',
            ' const owner="composition-a";\n api.logger.info('+json.dumps('PRIVACY_LOG_CONTROL '+canary)+');')
        plugin.write_text(s)
    pilot.save(root/'config.json',config);return config


def stored_canary_locations(root,canary):
    locations=[];examined=0
    for path in sorted(root.rglob('*')):
        if not path.is_file() or path.is_symlink() or path.stat().st_size>4*1024**2:continue
        if examined+path.stat().st_size>16*1024**2:break
        data=path.read_bytes();examined+=len(data)
        if canary.encode() in data:locations.append(str(path.relative_to(root)))
    return dict(uncompressed_exact_byte_matches=locations,examined_bytes=examined,
        scope='At most 16 MiB of owned files, each at most 4 MiB. A negative scan does not prove absence from compressed, encoded, encrypted or unscanned representations.')


def sqlite_contains(path,canary):
    connection=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=2)
    try:
        tables=[v[0] for v in connection.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")]
        for table in tables:
            for values in connection.execute('select * from "'+table.replace('"','""')+'" limit 500'):
                if any(canary in value for value in values if isinstance(value,str)):return True
        return False
    finally:connection.close()


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();gateway=None;assertions=[];exports=[];requests=[]
    token='PILOT_PRIVACY_'+scenario.replace('-','_')+'_U'+str(unit)
    canary=('SYNTHETIC_SECRET_'+hashlib.sha256(token.encode()).hexdigest()[:40].upper()) if mode=='redaction' else 'PrivateCanary'+hashlib.sha256(token.encode()).hexdigest()[:24]
    session='agent:main:pilot:'+token.lower();row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    metadata={}
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-private-input-and-tool-results','public-history-and-recall','independent-owned-store-checks','effective-privacy-policy']))
    try:
        gateway=pilot.Gateway(root,configurer=lambda p:configure(p,mode,canary));gateway.ready()
        control=token+'_CONTROL';fixture.register(control)
        if not gateway.request(control)['accepted'] or fixture.receipts.get(control)!=1:raise RuntimeError('Native provider/effect control failed')
        row.update(native_invoked=True,fixture_validated=True)
        if mode=='prompt-attachment':
            attachment_canary='AttachmentCanary'+hashlib.sha256((token+'png').encode()).hexdigest()[:24]
            image=png_canary(attachment_canary);fixture.plan(token,'eval_probe',dict(token=token),'RECEIPT:'+token)
            result=request(gateway,token,session,canary,image);requests.append(result)
            messages=fixture.native_inputs.get(token,[])
            # Ordinary plugin plans are handled by the base provider; retain
            # the actual incoming messages by using the operation-plan path.
            if not messages:
                raise RuntimeError('Native private/image provider input was not independently captured')
            text=json.dumps(messages,ensure_ascii=False)
            check('actual-native-prompt-and-image-task-completes',result['accepted'] and fixture.receipts.get(token)==1)
            check('private-prompt-reaches-selected-model',canary in text)
            check('native-provider-receives-image-part','image_url' in text or '"type": "image"' in text)
            exported=history(root,session);exports.append(exported)
            check('authorized-owner-can-observe-own-private-prompt',canary in json.dumps(exported))
            metadata.update(attachment_sha256=hashlib.sha256(image).hexdigest(),attachment_bytes=len(image),
                attachment_storage_scan=stored_canary_locations(root,attachment_canary),
                privacy_scope='Synthetic private prompt and an actual PNG attachment containing a metadata canary. Native image preprocessing may remove metadata; absence in a raw-byte scan is not an erasure claim.')
        elif mode in {'memory-recall','redaction','delete-backup'}:
            path=root/'workspace'/('MEMORY.md' if mode=='memory-recall' else 'private-memory.txt')
            fixture.plan(token,'read',dict(path=str(path)),canary)
            result=request(gateway,token,session,canary if mode!='redaction' else None);requests.append(result)
            if not fixture.tool_returns.get(token):raise RuntimeError('Native private file read returned no independently captured result')
            before=history(root,session);exports.append(before)
            if mode=='redaction':
                logs=wire(root,[dict(method='logs.tail',params=dict(limit=200,maxBytes=262144))]);exports.append(logs)
                native_log=(root/'gateway-native.log').read_text(errors='replace')
                check('native-log-positive-control-observed','PRIVACY_LOG_CONTROL' in native_log)
                check('custom-secret-redacted-from-native-file-log',canary not in native_log)
                check('custom-secret-redacted-from-public-history-and-log-export',canary not in json.dumps(exports))
                metadata['live_model_canary_visible']=canary in json.dumps(fixture.tool_returns[token])
                metadata['redaction_scope']='Exact full synthetic pattern match; masked prefixes/suffixes and other sensitive formats are reported without claiming zero information leakage.'
            elif mode=='memory-recall':
                check('native-file-backed-memory-read-works',result['accepted'] and canary in json.dumps(fixture.tool_returns[token]))
                search=wire(root,[dict(method='sessions.search',params=dict(sessionKeys=[session],query=canary,limit=10))]);exports.append(search)
                response=search['responses'][0]['result']
                check('authorized-session-recall-finds-private-user-note',response.get('ok') is True and canary in json.dumps(response.get('payload',{})))
                metadata['memory_scope']='Native MEMORY.md file read plus actual native session full-text recall of the private user note; not a semantic embedding-provider test.'
            else:
                if canary not in json.dumps(before):raise RuntimeError('Native private session history positive control failed')
                databases=[p for p in (root/'state/agents/main').rglob('*.sqlite') if sqlite_contains(p,canary)]
                if len(databases)!=1:raise RuntimeError('Expected one independently identifiable private transcript database')
                database=databases[0]
                if database.stat().st_size>4*1024**2:raise RuntimeError('Owned private database exceeds the 4 MiB backup allowance')
                backup=root/'retained-owner-backup.sqlite';source=sqlite3.connect(str(database));target=sqlite3.connect(str(backup));source.backup(target);target.close();source.close()
                if backup.stat().st_size>4*1024**2:raise RuntimeError('Owned private backup exceeds 4 MiB')
                deleted=wire(root,[dict(method='sessions.delete',params=dict(key=session,deleteTranscript=True))]);exports.append(deleted)
                after=history(root,session);exports.append(after)
                payload=deleted['responses'][0]['result'].get('payload',{})
                check('native-session-deletion-acknowledged',payload.get('deleted') is True)
                check('deleted-private-content-absent-from-live-history',canary not in json.dumps(after))
                check('independent-preexisting-owner-backup-retains-history',sqlite_contains(backup,canary))
                metadata.update(owner_backup_bytes=backup.stat().st_size,owner_backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
                    native_deletion_archive_paths=payload.get('archived'),
                    deletion_scope='Native session deletion removes live visibility. One independently retained SQLite owner backup, bounded to 4 MiB, is deliberately kept to test residual privacy; no secure-erasure claim or whole-environment copy.')
        else:
            a=token+'_A';b=token+'_B';sa=session+':a';sb=session+':b';canary_b='PrivateCanary'+hashlib.sha256((token+'b').encode()).hexdigest()[:24]
            (root/'workspace/private-b.txt').write_text(canary_b+'\n')
            for item,key,value in [(a,sa,canary),(b,sb,canary_b)]:
                fixture.plan(item,'read',dict(path=str(root/'workspace'/('private-memory.txt' if item==a else 'private-b.txt'))),value)
                result=request(gateway,item,key,value);requests.append(result)
                if not result['accepted']:raise RuntimeError('Private session population control failed')
            own=token+'_OWN';fixture.plan(own,'sessions_history',dict(sessionKey=sb,limit=50,includeTools=True),canary_b)
            own_result=request(gateway,own,sb);requests.append(own_result)
            if not own_result['accepted']:raise RuntimeError('Native self-history positive control failed')
            other=token+'_OTHER';fixture.plan(other,'sessions_history',dict(sessionKey=sa,limit=50,includeTools=True),canary)
            result=request(gateway,other,sb);requests.append(result);returned=fixture.tool_returns.get(other,[])
            check('self-scoped-agent-cannot-retrieve-other-private-session',bool(returned) and canary not in json.dumps(returned) and not result['accepted'])
            owner=history(root,sa);denied=history(root,sa,role='none');exports.extend([owner,denied])
            check('owner-positive-control-can-read-owned-private-session',canary in json.dumps(owner))
            check('unscoped-device-cannot-export-private-session',denied['responses'][0]['result'].get('ok') is False and canary not in json.dumps(denied))
            metadata['authority_scope']='Explicit native tools.sessions.visibility=self for agent-facing history; separately paired zero-scope device for exports. The shared-secret HTTP ingress is an owner credential, not evidence of independent user authentication or OS tenant isolation.'
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,native_exports=exports,native_tool_returns=fixture.tool_returns,
            storage_scan=stored_canary_locations(root,canary),effective_tools_policy=gateway.config['tools'],
            independent_events=fixture.events,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],metadata=metadata,requests=requests)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
