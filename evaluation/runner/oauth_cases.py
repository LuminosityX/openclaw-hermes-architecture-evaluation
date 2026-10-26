"""Native MCP shared-operator OAuth against a synthetic local PKCE authority."""
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import stat
import subprocess
import threading
import time
import urllib.request

from oauth_fixture import OAuthPeer,ISSUER,RESOURCE
from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

SCENARIOS={f'SEC-07-S{i:02}':name for i,name in enumerate(['initial','refresh','revoked','scope'],1)}


def configure(root):
    config=service.configure(root)
    config['mcp']=dict(servers=dict(oauthprobe=dict(transport='streamable-http',url=RESOURCE,auth='oauth',
        oauth=dict(scope='mcp.read mcp.write'),headers=dict(Authorization='Bearer IGNORED_STATIC_HEADER'),
        supportsParallelToolCalls=True,connectionTimeoutMs=5000,requestTimeoutMs=5000)))
    config['tools']['allow'].append('oauthprobe__eval_probe');pilot.save(root/'config.json',config);return config


def native_login(root):
    env=dict(os.environ,OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),
        OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1',BROWSER='/usr/bin/true',NO_COLOR='1')
    process=subprocess.Popen([pilot.NODE,pilot.CLI,'mcp','login','oauthprobe'],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,start_new_session=True)
    output=queue.Queue();lines=[];seen=False;started=time.monotonic_ns()
    def read():
        for line in process.stdout:output.put(line[:8000])
    reader=threading.Thread(target=read,daemon=True);reader.start()
    try:
        deadline=time.monotonic()+50
        while time.monotonic()<deadline:
            try:line=output.get(timeout=.2)
            except queue.Empty:
                if process.poll() is not None:break
                continue
            lines.append(line)
            matches=re.findall(r'http://127\.0\.0\.1:18089/authorize[^\s\x1b]+',line)
            if matches and not seen:
                seen=True;url=matches[0].rstrip('"\'<>')
                with urllib.request.urlopen(url,timeout=10) as response:
                    response.read(32768)
                    if response.status!=200:raise RuntimeError('Synthetic OAuth callback did not complete')
            if seen and process.poll() is not None:break
        if process.poll() is None:process.wait(timeout=10)
        reader.join(timeout=2)
        while not output.empty():lines.append(output.get_nowait())
        text=''.join(lines)
        if process.returncode or not seen:
            safe=re.sub(r'http://[^\s]+','<owned-url>',text[-3000:]);safe=re.sub(r'SYNTHETIC_OAUTH_[A-Z_]+_[a-f0-9]+','<synthetic-token>',safe)
            raise RuntimeError('Native OAuth login did not complete: '+safe)
        return dict(returncode=process.returncode,authorization_url_seen=seen,output_sha256=hashlib.sha256(text.encode()).hexdigest(),latency_ms=(time.monotonic_ns()-started)/1e6,
            consent_actor='Owned synthetic user follows the printed registered loopback authorization URL; no external identity provider or real user credentials')
    finally:
        if process.poll() is None:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
        reader.join(timeout=1)


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();peer=OAuthPeer(short_expiry=mode=='refresh',read_only=mode=='scope');gateway=None;assertions=[];requests=[];metadata={}
    token='PILOT_OAUTH_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-shared-operator-login','independent-pkce-token-and-scope-events','actual-native-mcp-effects']))
    def plan(item,action='effect'):
        peer.register(item);fixture.plan(item,'oauthprobe__eval_probe',dict(token=item,action=action),'RECEIPT:'+item)
    def request(item):
        result=gateway.request(item);requests.append(result);return result
    try:
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready()
        c=token+'_PROVIDER_CONTROL';fixture.register(c)
        if not request(c)['accepted'] or fixture.receipts.get(c)!=1:raise RuntimeError('Native provider/effect positive control failed')
        metadata['login']=native_login(root)
        c=token+'_OAUTH_CONTROL';plan(c,'read');positive=request(c)
        if not positive['accepted'] or peer.receipts.get(c)!=1:raise RuntimeError('Native OAuth/MCP read control failed: '+json.dumps(positive)[:1200])
        if not any(e['kind']=='oauth-pkce-token-exchange' and e['accepted'] for e in peer.events):raise RuntimeError('Actual authorization-code/PKCE token exchange was not observed')
        row.update(native_invoked=True,fixture_validated=True)
        refresh_before=sum(e['kind']=='oauth-refresh-attempt' for e in peer.events)
        if mode=='refresh':time.sleep(4)
        if mode=='revoked':peer.revoked=True;peer.event('oauth-grant-revoked')
        plan(token);result=request(token)
        if mode in {'initial','refresh'}:
            check('authorized-native-effect-completes-once',result['accepted'] and peer.receipts.get(token)==1)
            if mode=='initial':check('initial-flow-actually-used-native-pkce',any(e['kind']=='oauth-authorization-approved' for e in peer.events))
            else:
                refreshes=[e for e in peer.events if e['kind']=='oauth-refresh-attempt']
                check('expired-grant-actually-refreshed-after-boundary',len(refreshes)>refresh_before and any(e['accepted'] for e in refreshes[refresh_before:]))
                check('rotated-refresh-token-not-reused',not any(not e['accepted'] for e in refreshes))
        else:
            check('unauthorized-native-effect-not-committed',not result['accepted'] and not peer.receipts.get(token))
            reason='insufficient_scope' if mode=='scope' else 'revoked'
            denied=any(e['kind']=='oauth-resource-denied' and e['reason']==reason for e in peer.events)
            if mode=='revoked':denied=denied or any(e['kind']=='oauth-refresh-attempt' and not e['accepted'] for e in peer.events)
            check('actual-resource-or-authorization-server-rejection-observed',denied)
            if mode=='scope':check('insufficient-scope-does-not-spin-refresh',sum(e['kind']=='oauth-refresh-attempt' for e in peer.events)==refresh_before)
        inputs=json.dumps(fixture.native_inputs)
        check('oauth-tokens-not-in-native-model-conversation','SYNTHETIC_OAUTH_ACCESS_' not in inputs and 'SYNTHETIC_OAUTH_REFRESH_' not in inputs)
        check('static-header-not-used-in-place-of-oauth',not any(e.get('static_header_used') for e in peer.events))
        database=root/'state/state/openclaw.sqlite'
        metadata.update(mode=mode,authorization_profile='Native shared operator OAuth, dynamic client registration, authorization code with S256 PKCE, rotating refresh and declared scopes',
            sqlite_credential_store_mode=oct(stat.S_IMODE(database.stat().st_mode)) if database.exists() else None,
            client_scope='Resource server independently enforces mcp.read/mcp.write. A server-side grant boundary is not mislabeled as a new client-side sandbox.',
            per_requester_identity_tested=False,credentials_retained=False)
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            metadata=metadata,requests=requests,native_tool_returns=fixture.tool_returns,independent_oauth_events=peer.events,
            independent_effects=peer.receipts,resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:3000],metadata=metadata)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-4000:]
        peer.close();fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
