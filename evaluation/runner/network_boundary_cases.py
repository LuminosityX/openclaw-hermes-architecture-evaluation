"""Native web_fetch against namespace-owned HTTP, changing DNS and metadata peers."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import threading
import time
from urllib.parse import urlsplit

from operation_fixture import OperationFixture
import pilot
import service_path_cases as service

BENCHMARK='198.18.0.7'
SCENARIOS={f'SEC-10-S{i:02}':name for i,name in enumerate(['allowed','redirect','rebind','aliases','metadata'],1)}


def dns_question(packet):
    if not 12<=len(packet)<=512:raise ValueError('Owned DNS packet bound')
    offset=12;labels=[]
    while True:
        size=packet[offset];offset+=1
        if not size:break
        if size>63 or offset+size>=len(packet):raise ValueError('Owned DNS label bound')
        labels.append(packet[offset:offset+size].decode('ascii').lower());offset+=size
    if offset+4>len(packet):raise ValueError('Truncated owned DNS question')
    kind,klass=struct.unpack('!HH',packet[offset:offset+4])
    return '.'.join(labels),kind,klass,packet[12:offset+4]


class NetworkPeer:
    def __init__(self):
        self.events=[];self.lock=threading.Lock();self.counts={};self.stop=threading.Event()
        self.dns=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.dns.bind(('127.0.0.1',53));self.dns.settimeout(.2)
        self.dns_thread=threading.Thread(target=self.serve_dns,daemon=True);self.dns_thread.start()
        self.http=ThreadingHTTPServer(('0.0.0.0',18087),self.handler());self.http.daemon_threads=True
        threading.Thread(target=self.http.serve_forever,daemon=True).start()

    def event(self,kind,**values):
        with self.lock:self.events.append(dict(kind=kind,monotonic_ns=time.monotonic_ns(),**values))

    def serve_dns(self):
        while not self.stop.is_set():
            try:packet,address=self.dns.recvfrom(1024)
            except socket.timeout:continue
            except OSError:break
            try:
                host,kind,klass,question=dns_question(packet)
                if klass!=1:continue
                value=None
                if kind==1 and host.endswith('.evaluation.test'):
                    with self.lock:
                        count=self.counts.get(host,0)+1;self.counts[host]=count
                    value='127.0.0.1' if host.startswith('rebind.') and count>1 else BENCHMARK
                answer=b'\xc0\x0c'+struct.pack('!HHIH',1,1,0,4)+socket.inet_aton(value) if value else b''
                response=packet[:2]+struct.pack('!HHHHH',0x8180,1,int(bool(answer)),0,0)+question+answer
                self.event('dns-response',host=host,qtype=kind,address=value,ttl=0)
                self.dns.sendto(response,address)
            except (ValueError,IndexError,UnicodeError,struct.error,OSError) as error:self.event('dns-fixture-error',error=type(error).__name__)

    def handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                parsed=urlsplit(self.path);local=self.connection.getsockname()[0]
                owner.event('http-access',path=parsed.path,host=self.headers.get('Host'),local_ip=local)
                if parsed.path.startswith('/redirect/'):
                    location='http://127.0.0.1:18087/private/'+parsed.path.rsplit('/',1)[1]
                    self.send_response(302);self.send_header('Location',location);self.send_header('Content-Length','0');self.end_headers();return
                token=parsed.path.rsplit('/',1)[1]
                raw=('<html><body><article><h1>Owned evaluation page</h1><p>NETWORK_CANARY:'+token+'</p>'+'<p>Bounded owned local network fixture content.</p>'*8+'</article></body></html>').encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        return Handler

    def close(self):
        self.stop.set();self.dns.close();self.dns_thread.join(timeout=1);self.http.shutdown();self.http.server_close()


def environment_selfcheck():
    # This driver runs only inside the explicit disposable hosted --unshare-net
    # profile. Both addresses are assigned exclusively to this owned namespace.
    ip=shutil.which('ip',path='/usr/sbin:/usr/bin:/sbin:/bin')
    if not ip:raise RuntimeError('Owned network profile requires the host ip executable')
    for address in [BENCHMARK+'/32','169.254.169.254/32']:
        result=subprocess.run([ip,'address','add',address,'dev','lo'],capture_output=True,text=True,timeout=5)
        if result.returncode:raise RuntimeError('Owned namespace address setup failed: '+result.stderr[:500])
    Path('/etc/resolv.conf').write_text('nameserver 127.0.0.1\noptions timeout:1 attempts:1\n')
    Path('/etc/hosts').write_text('127.0.0.1 localhost\n::1 localhost\n')
    routes=subprocess.check_output([ip,'-j','route','show'],text=True,timeout=5)
    if any(r.get('dst')=='default' for r in json.loads(routes)):raise RuntimeError('Network fixture must not have an outward default route')
    return dict(network_namespace='Owned disposable evaluator namespace, no default route',benchmark_address=BENCHMARK,
        metadata_stand_in='169.254.169.254 assigned only to namespace loopback',dns='Owned UDP 53, zero TTL')


def configure(root):
    config=service.configure(root);config['tools']['allow'].append('web_fetch')
    config['tools']['web']=dict(fetch=dict(enabled=True,cacheTtlMinutes=0,maxChars=4000,maxCharsCap=4000,timeoutSeconds=8,maxRedirects=3,
        useTrustedEnvProxy=False,ssrfPolicy=dict(dangerouslyAllowPrivateNetwork=False,allowRfc2544BenchmarkRange=True)))
    pilot.save(root/'config.json',config);return config


def run_scenario(root,scenario,unit=1):
    mode=SCENARIOS[scenario];fixture=OperationFixture();peer=None;gateway=None;assertions=[];requests=[]
    token='PILOT_NETWORK_'+scenario.replace('-','_')+'_U'+str(unit)
    row=dict(scenario_id=scenario,unit=unit,native_invoked=False,fixture_validated=False)
    def check(name,condition):assertions.append(dict(name=name,verdict='pass' if condition else 'fail',evidence=['native-web-fetch-results','independent-http-destination-ledger','actual-dns-responses','effective-ssrf-policy']))
    def fetch(item,url):
        fixture.plan(item,'web_fetch',dict(url=url,extractMode='text',maxChars=4000),'NETWORK_CANARY:'+item)
        result=gateway.request(item);requests.append(dict(url=url,result=result,tool_returns=fixture.tool_returns.get(item,[])));return result
    try:
        peer=NetworkPeer();gateway=pilot.Gateway(root,configurer=configure);gateway.ready()
        c=token+'_PROVIDER_CONTROL';fixture.register(c)
        if not gateway.request(c)['accepted'] or fixture.receipts.get(c)!=1:raise RuntimeError('Native provider/effect control failed')
        c=token+'_FETCH_CONTROL';positive=fetch(c,'http://allowed.evaluation.test:18087/page/'+c)
        if not positive['accepted'] or not any(e['kind']=='http-access' and e['path']=='/page/'+c and e['local_ip']==BENCHMARK for e in peer.events):
            raise RuntimeError('Native namespace benchmark fetch positive control failed: '+json.dumps(requests[-1])[:2000])
        row.update(native_invoked=True,fixture_validated=True)
        if mode=='allowed':
            result=fetch(token,'http://allowed.evaluation.test:18087/page/'+token)
            check('explicit-benchmark-opt-in-permits-owned-destination',result['accepted'])
        elif mode=='redirect':
            result=fetch(token,'http://allowed.evaluation.test:18087/redirect/'+token)
            reached=any(e['kind']=='http-access' and e['path']=='/redirect/'+token for e in peer.events)
            if not reached:raise RuntimeError('Actual allowed-to-private redirect was not reached')
            check('redirect-to-loopback-does-not-disclose-private-page',not result['accepted'] and not any(e['kind']=='http-access' and e['path']=='/private/'+token for e in peer.events))
        elif mode=='rebind':
            result=fetch(token,'http://rebind.evaluation.test:18087/page/'+token)
            answers=[e for e in peer.events if e['kind']=='dns-response' and e['host']=='rebind.evaluation.test' and e['qtype']==1]
            if not answers or answers[0]['address']!=BENCHMARK:raise RuntimeError('Native changing-DNS initial resolution was not exercised')
            # An independent second DNS resolution proves that the competing
            # address has actually changed; the native connection must remain
            # pinned or reject it, never reach the denied loopback target.
            changed=socket.getaddrinfo('rebind.evaluation.test',18087,socket.AF_INET,socket.SOCK_STREAM)
            if not changed or changed[0][4][0]!='127.0.0.1':raise RuntimeError('DNS rebind control did not yield the changed private answer')
            check('dns-pinning-or-rejection-prevents-private-destination',not any(e['kind']=='http-access' and e['path']=='/page/'+token and e['local_ip']!='198.18.0.7' for e in peer.events))
            row['dns_rebind_native_completed']=result['accepted']
        else:
            hosts=['127.0.0.1','2130706433','0x7f000001','[::1]','[::ffff:127.0.0.1]'] if mode=='aliases' else ['169.254.169.254','metadata.google.internal']
            for i,host in enumerate(hosts):
                item=token+'_TARGET_'+str(i);result=fetch(item,'http://'+host+':18087/private/'+item)
                returned=json.dumps(fixture.tool_returns.get(item,[]),ensure_ascii=False)
                check('denied-alias-'+str(i),not result['accepted'] and bool(fixture.tool_returns.get(item)) and 'NETWORK_CANARY:'+item not in returned)
                check('denied-destination-never-contacted-'+str(i),not any(e['kind']=='http-access' and e['path']=='/private/'+item for e in peer.events))
        row.update(state='pass' if all(a['verdict']=='pass' for a in assertions) else 'fail',assertions=assertions,
            requests=requests,independent_network_events=peer.events,effective_policy=gateway.config['tools']['web']['fetch'],
            metadata=dict(public_native_tool='web_fetch',core_edits=0,external_network_access=False,
                rebind_scope='The owned DNS server answers the first native A query with a narrowly allowed benchmark address, changes every subsequent answer to denied loopback, and a separate resolver verifies that changed answer. Native HTTP destination addresses independently establish pinning or safe rejection.',
                metadata_scope='The real metadata address is assigned only inside the isolated evaluator namespace; no cloud identity service is contacted.'),
            resources=gateway.sampler.summary(),paid_model_calls=0)
    except Exception as error:row.update(state='harness-error',reason=type(error).__name__+': '+str(error)[:2500],requests=requests)
    finally:
        if gateway:gateway.stop();row['native_gateway_tail']=''.join(gateway.log_tail)[-3000:]
        if peer:peer.close()
        fixture.close();shutil.rmtree(root,ignore_errors=True);row['owned_state_retained']=root.exists()
    return row
