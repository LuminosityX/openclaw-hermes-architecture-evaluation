#!/usr/bin/env python3
"""One disposable independent GitHub host; secrets stay outside native namespaces."""
import argparse
from collections import deque
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile

from suite import ROOT,require
sys.path.insert(0,str(ROOT/'evaluation/runner'))
from portable_support import HostBounds

REPO='zyw02/agent-arch'
UID=65534


def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False)+'\n')

def clean(value,secrets=()):
    if isinstance(value,dict):
        return {key:('[redacted]' if key.lower() in {'devicetoken','privatekey','privatekeypem','apikey','native_token','shared_token','authorization','password'} or key.lower()=='token' and not (isinstance(item,str) and item.startswith('PILOT_MULTI_')) else clean(item,secrets)) for key,item in value.items()}
    if isinstance(value,list):return [clean(v,secrets) for v in value]
    if isinstance(value,str):
        for secret in secrets:
            if secret:value=value.replace(secret,'[redacted]')
        value=re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._-]+',r'\1[redacted]',value)
        value=re.sub(r'(?i)(["\']?(?:deviceToken|privateKeyPem|apiKey)["\']?\s*[:=]\s*["\']?)[^\s,"\'}]+',r'\1[redacted]',value)
    return value


def peer_artifact(unit,role,timeout=240):
    until=time.monotonic()+timeout;name='multihost-rendezvous-'+role+'-'+str(unit)
    base='repos/'+REPO+'/actions/'
    while time.monotonic()<until:
        artifacts=json.loads(subprocess.check_output(['gh','api',base+'runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts?per_page=100']))['artifacts']
        matched=[a for a in artifacts if a['name']==name and not a['expired']]
        if matched:
            require(len(matched)==1 and matched[0]['size_in_bytes']<=16384,'Invalid public peer descriptor artifact')
            raw=subprocess.check_output(['gh','api',base+'artifacts/'+str(matched[0]['id'])+'/zip'])
            require(len(raw)<=16384,'Peer descriptor ZIP exceeded bound')
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                require(z.namelist()==['rendezvous.json'] and z.getinfo('rendezvous.json').file_size<=8192,'Unsafe public peer descriptor layout')
                descriptor=json.loads(z.read('rendezvous.json'))
            require(descriptor['controller_commit']==os.environ['GITHUB_SHA'] and str(descriptor['run_id'])==os.environ['GITHUB_RUN_ID'] and descriptor['unit']==unit and descriptor['role']==role,'Actual peer identity disagrees with this workflow')
            return descriptor
        time.sleep(3)
    raise RuntimeError('Independent GitHub peer rendezvous unavailable before timeout')


class Effects:
    def __init__(self,role,unit,group,output):
        self.role=role;self.unit=unit;self.group=group;self.output=output;self.events=[];self.destroyed=threading.Event();self.partition_done=threading.Event();self.rule=None
        self.boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip();self.lock=threading.Lock()
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.path!='/effect':return self.send_error(404)
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4096:return self.send_error(413)
                data=json.loads(self.rfile.read(size));token=data.get('token','')
                if not re.fullmatch(r'PILOT_MULTI_S[1-4]_U'+str(unit)+r'_[A-Z0-9_]+',token):return self.send_error(403)
                try:
                    identity=owner.identity(data)
                    owner.record('actual-owned-helper-entry',token=token,identity=identity)
                    if role=='worker' and token.startswith('PILOT_MULTI_S4_'):
                        owner.partition(token)
                    if role=='worker' and token.startswith('PILOT_MULTI_S3_'):
                        time.sleep(.5);before=owner.members();(group/'cgroup.kill').write_text('1');owner.record('execution-host-destroyed',token=token,before_pids=before,physical_VM_powered_off=False,complete_native_execution_group_killed=True,storage_erasure_confirmed_by_final_host_provenance=True);owner.destroyed.set();return
                    time.sleep(1)
                    result=dict(token=token,host_boot_id=owner.boot,role=role,helper_host_pid=identity['host_pid'],helper_namespace_pid=identity['namespace_pid'],receipt='RECEIPT:'+token)
                    owner.record('actual-tool-effect-committed',**result)
                    payload=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
                except Exception as error:
                    owner.record('observer-harness-error',reason=type(error).__name__+': '+str(error));self.send_error(500)
        self.server=ThreadingHTTPServer(('127.0.0.1',18086),Handler);self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def members(self):return [int(p) for p in (self.group/'cgroup.procs').read_text().split()]
    def record(self,kind,**data):
        with self.lock:
            self.events.append(dict(kind=kind,utc_ns=time.time_ns(),monotonic_ns=time.monotonic_ns(),**dict({'host_boot_id':self.boot},**data)));save(self.output/'host-events.json',self.events)
    def identity(self,data):
        matches=[]
        for pid in self.members():
            try:
                status=Path('/proc',str(pid),'status').read_text();line=next(v for v in status.splitlines() if v.startswith('NSpid:'));namespace_pid=int(line.split()[-1])
                if namespace_pid!=data.get('pid') or os.readlink('/proc/'+str(pid)+'/ns/pid')!=data.get('pid_namespace'):continue
                command=Path('/proc',str(pid),'cmdline').read_bytes()
                if b'/driver/multihost_workload.py\0' not in command or data['token'].encode()+b'\0' not in command:continue
                if Path('/proc',str(pid),'status').read_text().split('Uid:',1)[1].split()[0]!=str(UID):continue
                matches.append(dict(host_pid=pid,namespace_pid=namespace_pid,namespace=data['pid_namespace'],actual_executable=os.readlink('/proc/'+str(pid)+'/exe'),command_sha256=hashlib.sha256(command).hexdigest(),helper_source_sha256=hashlib.sha256((ROOT/'evaluation/runner/multihost_workload.py').read_bytes()).hexdigest(),parent_host_pid=int(next(v for v in status.splitlines() if v.startswith('PPid:')).split()[1]),cwd=os.readlink('/proc/'+str(pid)+'/cwd')))
            except (OSError,IndexError,StopIteration):continue
        if len(matches)!=1:raise RuntimeError('Actual owned helper kernel identity is missing or ambiguous')
        return matches[0]
    def partition(self,token):
        if self.rule:raise RuntimeError('Partition already active')
        inodes=set()
        for pid in self.members():
            try:
                for fd in Path('/proc',str(pid),'fd').iterdir():
                    try:
                        target=os.readlink(fd)
                        if target.startswith('socket:['):inodes.add(target[8:-1])
                    except OSError:pass
            except OSError:pass
        connections=[]
        for table in ['tcp','tcp6']:
            for line in Path('/proc/net',table).read_text().splitlines()[1:]:
                parts=line.split()
                if len(parts)>9 and parts[9] in inodes and parts[2].split(':')[1]=='01BB':connections.append(dict(table=table,local=parts[1],remote=parts[2],socket_inode=parts[9],state=parts[3]))
        if not connections:raise RuntimeError('No actual native worker TLS connection was established before partition')
        label='openclaw-eval-'+os.environ['GITHUB_RUN_ID']+'-'+str(self.unit)
        arguments=['-p','tcp','--dport','443','-m','owner','--uid-owner',str(UID),'-m','comment','--comment',label,'-j','DROP']
        for tool in ['iptables','ip6tables']:subprocess.run([tool,'-I','OUTPUT','1',*arguments],check=True,capture_output=True)
        self.rule=arguments;self.record('real-native-TLS-partition-started',token=token,actual_connections=connections,uid=UID,duration_seconds=15,scope='Both IPv4/IPv6 native UID TLS output including reconnects on this disposable worker VM')
        def restore():
            time.sleep(15);counters=[]
            try:
                for tool in ['iptables','ip6tables']:
                    result=subprocess.run([tool,'-nvxL','OUTPUT'],capture_output=True,text=True,check=True)
                    lines=[line for line in result.stdout.splitlines() if label in line];counters.extend(dict(tool=tool,packets=int(line.split()[0]),bytes=int(line.split()[1])) for line in lines)
                self.record('real-native-TLS-partition-restored',token=token,kernel_drop_counters=counters,actual_dropped_packets=sum(v['packets'] for v in counters))
            finally:
                self.restore();self.partition_done.set()
        threading.Thread(target=restore,daemon=True).start()
    def restore(self):
        if self.rule:
            for tool in ['iptables','ip6tables']:subprocess.run([tool,'-D','OUTPUT',*self.rule],capture_output=True,check=False)
            self.rule=None
    def close(self):self.restore();self.server.shutdown();self.server.server_close()


def guest_command(args,root,group):
    command=['bwrap','--unshare-pid','--unshare-ipc','--unshare-uts','--unshare-cgroup','--die-with-parent','--new-session','--clearenv','--cap-drop','ALL','--cap-add','CAP_SETUID','--cap-add','CAP_SETGID','--cap-add','CAP_SETPCAP',
        '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib','--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev',
        '--dir','/input','--chmod','0755','/input','--dir','/runtime','--chmod','0755','/runtime','--dir','/etc','--chmod','0755','/etc','--dir','/etc/ssl','--chmod','0755','/etc/ssl','--dir','/toolchain','--chmod','0755','/toolchain','--ro-bind',str(args.node),'/toolchain/node','--ro-bind',str(args.runtime_modules),'/runtime/node_modules',
        '--ro-bind',str(ROOT/'evaluation/runner'),'/driver','--ro-bind',str(root/'private-spec.json'),'/input/spec.json','--ro-bind',str(root/'peer'),'/peer','--bind',str(root/'evidence'),'/evidence',
        '--bind',str(root/'scratch'),'/scratch','--symlink','scratch/tmp','/tmp','--symlink','scratch/home','/root',
        '--setenv','PATH','/toolchain:/usr/bin:/bin','--setenv','HOME','/scratch/home','--setenv','TMPDIR','/scratch/tmp','--setenv','NODE_DISABLE_COMPILE_CACHE','1','--setenv','JITI_CACHE_DIR','/scratch/cache/jiti',
        '--setenv','OPENCLAW_SKIP_CHANNELS','1','--setenv','OPENCLAW_DISABLE_BUNDLED_PLUGINS','1']
    for path in ['/etc/passwd','/etc/group','/etc/ssl/certs','/etc/localtime','/etc/resolv.conf','/etc/nsswitch.conf','/etc/hosts']:
        if Path(path).exists():command+=['--ro-bind',path,path]
    command+=['/usr/bin/setpriv','--reuid=65534','--regid=65534','--clear-groups','--bounding-set=-all','--inh-caps=-all','--ambient-caps=-all','/usr/bin/python3','/driver/multihost_'+('gateway' if args.role=='gateway' else 'node')+'.py']
    return command


def daemon(args):
    def stop_owned(signum,frame):raise RuntimeError('Owned cloud controller stopped; close endpoints before evidence publication')
    signal.signal(signal.SIGTERM,stop_owned)
    root=args.output;output=root/'evidence';output.mkdir(exist_ok=True);os.chown(output,UID,UID);os.chmod(output,0o700)
    peer=root/'peer';peer.mkdir(exist_ok=True);os.chmod(peer,0o755)
    scratch=root/'scratch';scratch.mkdir();os.chown(scratch,UID,UID);os.chmod(scratch,0o700)
    master=os.environ.pop('OPENCLAW_EVAL_TRANSPORT_FULL_20261026','');require(bool(master),'Dedicated campaign transport secret is required')
    native_token=hmac.new(master.encode(),(os.environ['GITHUB_RUN_ID']+':'+str(args.unit)).encode(),hashlib.sha256).hexdigest()
    bounds=HostBounds();group=bounds.group/'native-execution-host';group.mkdir();effects=None;guest=None;tunnel=None;secret_values=[master,native_token]
    result=dict(role=args.role,unit=args.unit,controller_commit=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],host_boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),actual_independent_GitHub_VM=True,local_runtime_installed=False)
    try:
        target=json.loads((ROOT/'evaluation/design/evaluation-matrix.json').read_text())['target']
        # Finish package lifecycle before read-only unprivileged native use.
        lifecycle_env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS'}}
        lifecycle_env.update(OPENCLAW_STATE_DIR=str(root/'private-lifecycle-state'),OPENCLAW_CONFIG_PATH=str(root/'private-lifecycle-config.json'),OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1')
        lifecycle=subprocess.run([str(args.node),str(args.runtime_modules/'openclaw/openclaw.mjs'),'--version'],env=lifecycle_env,capture_output=True,text=True,timeout=60)
        require(lifecycle.returncode==0 and target['version'] in lifecycle.stdout,'Native package lifecycle control failed')
        spec=dict(unit=args.unit,native_token=native_token)
        if args.role=='worker':
            descriptor=peer_artifact(args.unit,'gateway');result['gateway_public_descriptor']=descriptor
            require(re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',descriptor['host']) is not None,'Unexpected ephemeral TLS peer hostname')
            require(descriptor['host_boot_id']!=result['host_boot_id'],'Two independent GitHub VMs are required')
            spec['host']=descriptor['host']
        save(root/'private-spec.json',spec);os.chmod(root/'private-spec.json',0o644)
        effects=Effects(args.role,args.unit,group,output)
        def enter():(group/'cgroup.procs').write_text(str(os.getpid()))
        clean_env={k:v for k,v in os.environ.items() if k in {'PATH','LANG','LC_ALL'}}
        guest=subprocess.Popen(guest_command(args,root,group),env=clean_env,stdout=(output/'guest-process.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=enter)
        ready=output/('ready.json' if args.role=='gateway' else 'node-public.json');until=time.monotonic()+130
        while not ready.is_file() and time.monotonic()<until:
            if guest.poll() is not None:raise RuntimeError('Native guest exited before public readiness: '+(output/'guest-process.log').read_text()[-3000:])
            time.sleep(.2)
        require(ready.is_file(),'Native guest did not publish bounded public readiness')
        descriptor=dict(role=args.role,unit=args.unit,controller_commit=os.environ['GITHUB_SHA'],run_id=os.environ['GITHUB_RUN_ID'],host_boot_id=result['host_boot_id'])
        if args.role=='gateway':
            pin=json.loads((ROOT/'evaluation/design/multihost-transport.json').read_text());binary=root/'cloudflared'
            with urllib.request.urlopen(pin['url'],timeout=60) as response:raw=response.read(pin['maximum_bytes']+1)
            require(len(raw)<=pin['maximum_bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256'],'Official transport binary digest differs')
            binary.write_bytes(raw);binary.chmod(0o700);raw=b''
            transport_log=root/'private-tunnel.log'
            tunnel=subprocess.Popen([str(binary),'tunnel','--no-autoupdate','--protocol','http2','--url','http://127.0.0.1:18789'],env=clean_env,stdout=transport_log.open('w'),stderr=subprocess.STDOUT,start_new_session=True)
            until=time.monotonic()+80;hostname=None
            while time.monotonic()<until:
                matches=re.findall(r'https://([a-z0-9-]+\.trycloudflare\.com)',transport_log.read_text())
                if matches:hostname=matches[0];break
                if tunnel.poll() is not None:raise RuntimeError('Official transport exited before publishing a TLS hostname: '+transport_log.read_text()[-1500:])
                time.sleep(.5)
            require(hostname is not None,'Ephemeral authenticated native transport hostname unavailable')
            descriptor['host']=hostname;descriptor['transport_binary_sha256']=pin['sha256']
        else:descriptor.update(json.loads(ready.read_text()))
        rendezvous=root/'rendezvous';rendezvous.mkdir(exist_ok=True);save(rendezvous/'rendezvous.json',descriptor);save(root/'launch-ready.json',dict(ready=True))
        if args.role=='gateway':save(peer/'worker.json',peer_artifact(args.unit,'worker'))
        peak_scratch=0;next_storage_check=0
        deadline=time.monotonic()+1000
        while guest.poll() is None and time.monotonic()<deadline:
            if args.role=='worker' and effects.destroyed.is_set():break
            if time.monotonic()>=next_storage_check:
                used=int(subprocess.check_output(['du','-sb',str(scratch)]).split()[0]);peak_scratch=max(peak_scratch,used);next_storage_check=time.monotonic()+2
                require(used<=1024**3,'Actual disposable native state exceeds the 1 GiB write bound')
            time.sleep(.5)
        if args.role=='gateway':
            require(guest.poll() is not None,'Native multi-host campaign exceeded its bounded execution window')
            require((output/'gateway-report.json').is_file(),'Native gateway did not retain its final report')
            native=json.loads((output/'gateway-report.json').read_text())
            require(not native.get('harness_error'),native.get('harness_error','Native multi-host fixture failed'))
        else:require(effects.destroyed.is_set(),'Native worker was not destroyed at the declared live execution boundary')
        result.update(resources=bounds.summary(),host_scratch=dict(backing='Actual disposable GitHub VM disk with native free-space reserve checks unchanged',maximum_actual_bytes=1024**3,observed_peak_bytes=peak_scratch),kernel_io_stat=(bounds.group/'io.stat').read_text(),kernel_native_execution_group=dict(effective_parent_cpu_max=(bounds.group/'cpu.max').read_text(),effective_parent_memory_limit_bytes=int((bounds.group/'memory.max').read_text()),leaf_cpu_max=(group/'cpu.max').read_text() if (group/'cpu.max').is_file() else None,leaf_memory_peak_bytes=int((group/'memory.peak').read_text()) if (group/'memory.peak').is_file() else None,scope='Native leaf has only explicitly available accounting files; enforced limits and whole-host accounting belong to its bounded parent cgroup'),execution_host_destroyed=effects.destroyed.is_set())
    except Exception as error:result['harness_error']=type(error).__name__+': '+str(error)[:7000]
    finally:
        if effects:effects.close()
        if guest and guest.poll() is None:(group/'cgroup.kill').write_text('1');guest.wait(timeout=10)
        if tunnel and tunnel.poll() is None:os.killpg(tunnel.pid,signal.SIGTERM);tunnel.wait(timeout=10)
        until=time.monotonic()+5;live=[];zombies=[]
        while effects and time.monotonic()<until:
            live=[];zombies=[]
            for pid in effects.members():
                try:
                    state=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[0]
                    (zombies if state=='Z' else live).append(pid)
                except (OSError,IndexError):pass
            if not live:break
            time.sleep(.05)
        result['native_execution_pids_after_shutdown']=live
        result['nonexecuting_zombie_records_after_shutdown']=zombies
        if not live and scratch.exists():shutil.rmtree(scratch)
        result['native_execution_state_removed_after_shutdown']=not scratch.exists()
        # Publish only after the native endpoint has been stopped. Private
        # configs/identities live in removed owned disposable storage and never enter artifacts.
        save(output/'host-provenance.json',result)
        for path in output.iterdir():
            if not path.is_file():continue
            if path.suffix=='.json':
                try:save(path,clean(json.loads(path.read_text()),secret_values))
                except ValueError:path.unlink()
            else:path.write_text(clean(path.read_text(errors='replace')[-200000:],secret_values))
        save(root/'done.json',dict(success='harness_error' not in result,error=clean(result.get('harness_error'),secret_values)))
        (root/'private-spec.json').unlink(missing_ok=True)
        try:group.rmdir()
        except OSError:pass
        bounds.close()


def main():
    parser=argparse.ArgumentParser()
    for name in ['runtime-modules','node','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--role',choices=['gateway','worker'],required=True);parser.add_argument('--unit',type=int,choices=range(7),required=True)
    parser.add_argument('--phase',choices=['start','daemon','wait','stop'],required=True);args=parser.parse_args()
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.geteuid()==0,'Actual multi-host infrastructure is GitHub-only')
    if args.phase=='daemon':return daemon(args)
    if args.phase=='stop':
        if not args.output.exists() or (args.output/'done.json').is_file():return
        pid_path=args.output/'controller-pid.json'
        if pid_path.is_file():
            pid=json.loads(pid_path.read_text())['pid']
            try:
                command=Path('/proc',str(pid),'cmdline').read_bytes()
                require(b'run_multihost_host.py' in command and b'--phase\x00daemon' in command,'Owned cleanup PID does not identify this controller')
                os.kill(pid,signal.SIGTERM)
            except FileNotFoundError:pass
        deadline=time.monotonic()+30
        while not (args.output/'done.json').is_file() and time.monotonic()<deadline:time.sleep(.2)
        require((args.output/'done.json').is_file(),'Owned controller did not close/sanitize evidence before upload')
        return
    if args.phase=='start':
        args.output.mkdir(parents=True,exist_ok=False);args.output.chmod(0o700)
        command=[sys.executable,__file__,'--runtime-modules',str(args.runtime_modules),'--node',str(args.node),'--output',str(args.output),'--role',args.role,'--unit',str(args.unit),'--phase','daemon']
        process=subprocess.Popen(command,stdout=(args.output/'private-controller.log').open('w'),stderr=subprocess.STDOUT,start_new_session=True)
        save(args.output/'controller-pid.json',dict(pid=process.pid))
        deadline=time.monotonic()+400
        while not (args.output/'launch-ready.json').is_file() and time.monotonic()<deadline:
            if (args.output/'done.json').is_file():raise SystemExit((args.output/'done.json').read_text())
            if process.poll() is not None:raise SystemExit('Owned cloud controller exited before rendezvous: '+(args.output/'private-controller.log').read_text()[-2500:])
            time.sleep(.5)
        require((args.output/'launch-ready.json').is_file(),'Cloud rendezvous exceeded its finite start deadline')
    else:
        deadline=time.monotonic()+1200
        while not (args.output/'done.json').is_file() and time.monotonic()<deadline:time.sleep(1)
        require((args.output/'done.json').is_file(),'Cloud experiment exceeded its execution deadline')
        done=json.loads((args.output/'done.json').read_text());require(done['success'],done.get('error'))

if __name__=='__main__':main()
