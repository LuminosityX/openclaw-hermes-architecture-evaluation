"""Real-model native plumbing check; never counted as frozen scenario coverage."""
import hashlib
import http.client
import json
from pathlib import Path
import resource
import sys
import time

import pilot
from provider_bridge import bridge


def configure(root):
    config=pilot.configuration(root,tool_search=False)
    provider=config['models']['providers']['fixture']
    provider.update(baseUrl='http://127.0.0.1:18081/v1',apiKey='synthetic-relay-placeholder')
    provider['models'][0].update(id='deepseek-flash',name='User selected DeepSeek Flash',maxTokens=4096)
    config['agents']['defaults']['model']['primary']='fixture/deepseek-flash'
    pilot.save(root/'config.json',config)
    return config


def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_FSIZE,(16*1024**2,16*1024**2))
    for name in ['tmp','home','cache','run']:
        (Path('/scratch')/name).mkdir(exist_ok=True)
    pilot.storage_guard_check()
    server=bridge()
    fixture=pilot.Fixture()
    gateway=None
    report=dict(kind='real-model-harness-validation',product='openclaw',studies=[],full_campaign_coverage=False,
                purpose='Verify native Gateway/provider/tool/receipt/usage plumbing before the full campaign',
                model='deepseek-flash',provider='deepseek',credentials_inside_namespace=False,
                namespace_profile='Owned SSH-compatible root UID profile: separate network/PID/mount namespaces; no user namespace')
    try:
        gateway=pilot.Gateway(Path('/scratch/model-validation'),configurer=configure)
        gateway.ready()
        token='PILOT_REAL_PROVIDER_CHECK'
        prompt='EVAL_PROVIDER_VALIDATION Use eval_probe exactly once with token "'+token+'" and action "effect". Read its receipt, then reply with ACCEPTED:'+token+'. Do not call any other tool.'
        connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=150)
        started=time.monotonic_ns()
        try:
            connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',stream=False,messages=[dict(role='user',content=prompt)])),
                {'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':'agent:main:eval:provider-validation'})
            response=connection.getresponse()
            raw=response.read(1024**2+1)
            if len(raw)>1024**2: raise ValueError('Native response exceeds bounded plumbing check limit')
            data=json.loads(raw)
        finally: connection.close()
        effect_count=sum(e['kind']=='effect-commit' and e.get('token')==token for e in fixture.events)
        content=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]))
        report.update(native_http_status=response.status,response_sha256=hashlib.sha256(raw).hexdigest(),
                      response_bytes=len(raw),accepted_marker_visible='ACCEPTED:'+token in content,
                      committed_effects=effect_count,completion_ms=(time.monotonic_ns()-started)/1e6,
                      independent_receipts=[e for e in fixture.events if e['kind'] in {'effect-start','effect-commit'}],
                      native_records=pilot.native_evidence(gateway.root,[token]),resources=gateway.sampler.summary())
        report['plumbing_valid']=response.status==200 and report['accepted_marker_visible'] and effect_count==1
        if not report['plumbing_valid']: report['harness_error']='Real-provider plumbing acceptance failed; no campaign results awarded'
    except Exception as error:
        report['harness_error']=type(error).__name__+': '+str(error)[:2000]
    finally:
        if gateway: gateway.stop()
        fixture.close()
        server.shutdown()
        server.server_close()
    print(json.dumps(report,ensure_ascii=False),flush=True)
    if report.get('harness_error'): sys.exit(1)


if __name__=='__main__': main()
