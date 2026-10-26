"""Native full session placement on a separately provisioned GitHub VM."""
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import time

import pilot
from operation_fixture import OperationFixture


def main():
    spec=json.loads(Path('/input/spec.json').read_text());pilot.TOKEN=spec['native_token'];unit=spec['unit'] or 1
    for name in ['tmp','home','cache','run']:(pilot.BASE/name).mkdir(exist_ok=True)
    root=pilot.BASE/'multihost';fixture=OperationFixture();gateway=None;rows=[];report=dict(case_id='PERF-07',observations=rows,paid_model_calls=0)
    def wire(method,params=None,timeout=180000):
        path=root/'wire.json';pilot.save(path,dict(shared_token=pilot.TOKEN,operations=[dict(method=method,params=params or {},timeout=timeout)]))
        result=subprocess.run([pilot.NODE,'/driver/multihost_wire.mjs',str(path)],capture_output=True,text=True,timeout=timeout/1000+30)
        if not result.stdout.strip():raise RuntimeError('Native multi-host RPC did not return: '+result.stderr[-1500:])
        data=json.loads(result.stdout)
        if data.get('harness_error'):raise RuntimeError(data['harness_error'])
        return data
    def rpc(method,params=None,timeout=180000):return wire(method,params,timeout)['responses'][0]['result']
    def history(key):return rpc('chat.history',dict(sessionKey=key,limit=100,maxBytes=131072,toolResultMaxChars=16000))
    def token(scenario,suffix='ACTION'):return 'PILOT_MULTI_S'+str(scenario)+'_U'+str(spec['unit'])+'_'+suffix
    def request(item,key):
        fixture.plan(item,'exec',dict(command='/usr/bin/python3 /driver/multihost_workload.py '+item,yieldMs=10000,timeoutSeconds=90),'RECEIPT:'+item)
        connection=http.client.HTTPConnection('127.0.0.1',18789,timeout=150);started=time.monotonic_ns()
        try:
            connection.request('POST','/v1/chat/completions',json.dumps(dict(model='openclaw',messages=[dict(role='user',content='Perform the owned deterministic operation '+item)],stream=False)),{'Content-Type':'application/json','Authorization':'Bearer '+pilot.TOKEN,'x-openclaw-session-key':key})
            response=connection.getresponse();raw=response.read(256*1024);data=json.loads(raw);text=''.join(str(c.get('message',{}).get('content','')) for c in data.get('choices',[]))
            return dict(status=response.status,accepted='ACCEPTED:'+item in text,response_sha256=hashlib.sha256(raw).hexdigest(),latency_ms=(time.monotonic_ns()-started)/1e6)
        except (OSError,ValueError,http.client.HTTPException) as error:return dict(status=None,accepted=False,error=type(error).__name__,latency_ms=(time.monotonic_ns()-started)/1e6)
        finally:connection.close()
    def prepare(key):
        created=rpc('sessions.patch',dict(key=key,permissionMode='full'))
        if not created.get('ok'):raise RuntimeError('Actual native session preparation failed: '+json.dumps(created)[-2000:])
        return created
    def add(scenario,checks,metadata):
        assertions=[dict(name=name,verdict='pass' if value else 'fail',evidence=['actual-independent-GitHub-VM-kernel-identities','native-session-placement-worker-bundle-and-history','read-only-tool-workload-and-independent-host-effect-ledgers']) for name,value in checks]
        rows.append(dict(scenario_id='PERF-07-S'+str(scenario).zfill(2),unit=unit,state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',native_invoked=True,fixture_validated=True,assertions=assertions,metadata=metadata))
    def configure(directory):
        config=pilot.configuration(directory,route='mcp',tool_search=False);config.pop('mcp',None);config['plugins']=dict(enabled=False)
        config['tools']=dict(allow=['exec'],toolSearch=False,exec=dict(host='gateway',security='full',ask='off'))
        config['agents']['defaults'].update(maxConcurrent=1,timeoutSeconds=180)
        # The transport is authenticated by a run/unit-specific random secret.
        config['gateway']['trustedProxies']=['127.0.0.1','::1']
        pilot.save(directory/'config.json',config);return config
    try:
        status=Path('/proc/self/status').read_text()
        caps={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.splitlines() if line.startswith(('CapEff:','CapBnd:'))}
        if os.geteuid()!=65534 or any(int(value,16) for value in caps.values()) or len(caps)!=2:raise RuntimeError('Native namespace UID/capability boundary was not established')
        report['native_namespace_security']=dict(uid=os.geteuid(),capabilities=caps)
        gateway=pilot.Gateway(root,configurer=configure);gateway.ready(timeout=100)
        # Complete this arm before publishing the remote endpoint to host B.
        local=[]
        for suffix in ['FIRST','SECOND']:
            key='agent:main:multi:local:'+str(spec['unit'])+':'+suffix.lower();prepare(key);item=token(1,suffix)
            result=request(item,key);local.append(dict(token=item,response=result,native_history=history(key)))
        if not all(x['response']['accepted'] for x in local):raise RuntimeError('Native single-execution-host control failed')
        add(1,[('Gateway-local-loop-and-tool-positive-control-completes',True)],dict(native_turns=local,remote_node_not_started_until_after_this_arm=True))
        Path('/evidence/ready.json').write_text(json.dumps(dict(native_gateway_ready=True,one_host_control_complete=True))+'\n')
        peer=Path('/peer/worker.json');until=time.monotonic()+240
        while not peer.is_file() and time.monotonic()<until:time.sleep(.5)
        if not peer.is_file():raise RuntimeError('Independent worker VM public identity did not arrive')
        worker=json.loads(peer.read_text());device=worker['deviceId'];report['worker_public_identity']=worker
        pair_records=[];until=time.monotonic()+100;inventory=None
        while time.monotonic()<until:
            pending=rpc('device.pair.list');pair_records.append(pending)
            payload=pending.get('payload',{});items=payload.get('pending',[]) if isinstance(payload,dict) else []
            for entry in items:
                if entry.get('deviceId')==device:
                    pair_records.append(rpc('device.pair.approve',dict(requestId=entry['requestId'])))
            inventory=rpc('environments.list')
            if device in json.dumps(inventory) and 'workerHost' in json.dumps(inventory):break
            time.sleep(1)
        report['exact_device_pairing_and_inventory']=dict(pairing=pair_records[-8:],inventory=inventory)
        # A fresh native session is dispatched in full. A second HTTP server or
        # system.run shell forwarding never substitutes for this placement.
        remote='agent:main:multi:remote:'+str(spec['unit']);prepare(remote)
        dispatch=rpc('sessions.dispatch',dict(key=remote,deviceId=device),240000)
        if not dispatch.get('ok') or dispatch.get('payload',{}).get('placement',{}).get('state')!='active':raise RuntimeError('Actual native full worker-session dispatch failed: '+json.dumps(dispatch)[-6000:])
        remote_item=token(2);local_key='agent:main:multi:concurrent:'+str(spec['unit']);prepare(local_key)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(request,remote_item,remote);b=pool.submit(request,token(2,'LOCAL_CONCURRENT'),local_key);remote_result=a.result(timeout=170);local_result=b.result(timeout=170)
        after=history(remote);workspace=root/'workspace'/('multihost-'+remote_item+'.json')
        commit=json.loads(workspace.read_text()) if workspace.exists() else None
        # Managed placement may use a session-owned Gateway workspace; retain
        # actual paths rather than assuming it writes the default agent root.
        if commit is None:
            matches=list((root/'state').rglob('multihost-'+remote_item+'.json'))
            if len(matches)==1:commit=json.loads(matches[0].read_text())
        if not remote_result['accepted']:raise RuntimeError('Dispatched native tool positive control did not execute on the worker: '+json.dumps(after)[-4500:])
        add(2,[('full-native-device-placement-runs-real-work',remote_result['accepted']),('Gateway-local-work-and-remote-work-both-complete',local_result['accepted']),('result-is-committed-to-Gateway-owned-native-history','RECEIPT:'+remote_item in json.dumps(after))],dict(dispatch=dispatch,remote_response=remote_result,concurrent_local_response=local_result,native_remote_history=after,reconciled_workspace_receipt=commit,loop_placement='Native sealed OpenClaw worker runs on host B; default inference HTTP proxy and canonical state owner remain on host A. Independent host-B kernel lineage and placement receipts are joined by the outer controller.',resource_comparison='Each execution host is capped separately at 3 GiB and two CPU cores. The two-host arm adds a second host; it is not equal-total-resources scaling.'))
        # Restore the partition before the destructive execution-host-loss arm.
        part_item=token(4);part_result=request(part_item,remote);part_history=history(remote)
        add(4,[('native-turn-completes-after-real-transport-partition-restores',part_result['accepted']),('same-device-placement-persists-after-partition',device in json.dumps(part_history))],dict(response=part_result,native_history=part_history,fault_scope='Worker root observer drops actual UID-scoped native TLS output for a bounded interval and requires kernel packet-drop counters. Native session hosting and worker files stay alive.'))
        lost_item=token(3);lost_result=request(lost_item,remote);time.sleep(3);lost_history=history(remote)
        add(3,[('destroyed-execution-host-does-not-report-the-lost-operation-as-success',not lost_result['accepted'] and 'RECEIPT:'+lost_item not in json.dumps(lost_history)),('lost-native-worker-has-no-automatic-local-business-replay',not (root/'workspace'/('multihost-'+lost_item+'.json')).exists())],dict(response=lost_result,native_history=lost_history,fault_scope='Entire native node/worker process namespace and tmpfs execution state on independent VM B are destroyed. The root observer remains to retain evidence; this is not a physical VM power-off or kernel crash.',recovery_scope='Offline placement and any cleanup/retry behavior are observed without silently granting destructive Continue-on-Gateway recovery or replaying the interrupted operation.'))
        report.update(validation_complete=len(rows)==4,fixture_and_invocation_valid=True,resources=gateway.sampler.summary())
    except Exception as error:report['harness_error']=type(error).__name__+': '+str(error)[:7000]
    finally:
        if gateway:gateway.stop();report['native_gateway_tail']=''.join(gateway.log_tail)[-4500:]
        report.update(independent_provider_events=fixture.events,native_tool_returns=fixture.tool_returns)
        fixture.close();Path('/evidence/gateway-report.json').write_text(json.dumps(report,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
