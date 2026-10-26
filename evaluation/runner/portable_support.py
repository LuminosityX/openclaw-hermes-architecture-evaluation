"""Bounded native Linux/Windows test support; no platform simulation."""
import ctypes
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import platform
import signal
import sqlite3
import subprocess
import time
import uuid

_WINDOWS_JOB=None


def owned_child_environment(root):
    allowed={'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','PROGRAMFILES','PROGRAMW6432','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE',
        'HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','NODE_EXTRA_CA_CERTS'}
    result={key:value for key,value in os.environ.items() if key.upper() in {v.upper() for v in allowed}}
    home=root/'owned-home';home.mkdir(parents=True,exist_ok=True);temporary=root/'tmp';temporary.mkdir(exist_ok=True)
    result.update(HOME=str(home),USERPROFILE=str(home),LOCALAPPDATA=str(home/'local'),APPDATA=str(home/'roaming'),TEMP=str(temporary),TMP=str(temporary),TMPDIR=str(temporary),
        OPENCLAW_STATE_DIR=str(root/'state'),OPENCLAW_CONFIG_PATH=str(root/'config.json'),OPENCLAW_SKIP_CHANNELS='1',OPENCLAW_DISABLE_BUNDLED_PLUGINS='1',
        OPENCLAW_EXEC_SHELL_SNAPSHOT='0',NODE_DISABLE_COMPILE_CACHE='1',JITI_CACHE_DIR=str(root/'jiti-cache'))
    return result


def process_identity(pid):
    if os.name!='nt':
        try:
            fields=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
            return None if fields[0]=='Z' else dict(pid=pid,start_ticks=fields[19])
        except (OSError,IndexError):return None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    kernel.GetProcessTimes.argtypes=[ctypes.c_void_p,*([ctypes.c_void_p]*4)]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        error=ctypes.get_last_error()
        if error in {87,1168}:return None
        raise OSError(error,'Owned Windows process identity cannot be queried')
    try:
        exit_code=ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle),ctypes.byref(exit_code)) or exit_code.value!=259:return None
        values=[ctypes.c_ulonglong() for _ in range(4)]
        if not kernel.GetProcessTimes(ctypes.c_void_p(handle),*[ctypes.byref(v) for v in values]):raise OSError(ctypes.get_last_error(),'Owned process time query failed')
        return dict(pid=pid,created_filetime=values[0].value)
    finally:kernel.CloseHandle(ctypes.c_void_p(handle))


def stop_owned_process(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,timeout=15,check=False)
    else:
        os.killpg(process.pid,signal.SIGTERM)
        try:process.wait(timeout=8)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL)
    process.wait(timeout=12)


def transcript_inventory(root):
    result=[]
    for path in sorted(root.rglob('*.sqlite')):
        if path.stat().st_size>8*1024**2:raise RuntimeError('Portable owned SQLite file exceeds 8 MiB inspection bound')
        connection=sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True,timeout=3)
        try:
            if not connection.execute("select 1 from sqlite_master where type='table' and name='transcript_events'").fetchone():continue
            columns=[r[1] for r in connection.execute('pragma table_info(transcript_events)')]
            order=','.join('"'+name.replace('"','""')+'"' for name in columns)
            rows=connection.execute('select * from transcript_events order by '+order+' limit 1001').fetchall()
            if len(rows)>1000:raise RuntimeError('Portable transcript inventory exceeds 1000 native rows')
            digest=hashlib.sha256()
            for row in rows:
                encoded=json.dumps([{'binary':v.hex()} if isinstance(v,bytes) else v for v in row],ensure_ascii=False,separators=(',',':')).encode()
                digest.update(len(encoded).to_bytes(8,'big'));digest.update(encoded)
            result.append(dict(database=path.name,columns=columns,row_count=len(rows),record_sha256=digest.hexdigest(),quick_check=[list(v) for v in connection.execute('pragma quick_check').fetchall()]))
        finally:connection.close()
    return sorted(result,key=lambda row:(row['database'],row['record_sha256']))


def staged_asset(staging,manifest,kind):
    assets=[a for a in manifest['assets'] if a['kind']==kind]
    if len(assets)!=1:raise RuntimeError('Portable corpus requires exactly one native '+kind+' asset')
    relative=PurePosixPath(assets[0]['archivePath'])
    if relative.is_absolute() or '..' in relative.parts or any(':' in p or '\\' in p for p in relative.parts):raise RuntimeError('Native restored asset escaped its staging layout')
    path=staging.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(staging.resolve()):raise RuntimeError('Native restored asset resolved outside staging')
    return path


class HostBounds:
    def __init__(self):
        self.group=None;self.original=None;self.job=None
        if os.name=='nt':self.windows()
        else:
            if os.geteuid()!=0:raise RuntimeError('Portable Linux controller needs its explicit hosted cgroup profile')
            current=Path('/proc/self/cgroup').read_text().strip().split('::',1)[1]
            self.original=Path('/sys/fs/cgroup')/current.lstrip('/')
            self.group=Path('/sys/fs/cgroup/system.slice')/('openclaw-portable-'+uuid.uuid4().hex[:12]+'.scope');self.group.mkdir()
            for key,value in {'memory.max':str(3*1024**3),'memory.swap.max':'0','pids.max':'128','cpu.max':'200000 100000'}.items():(self.group/key).write_text(value)
            (self.group/'cgroup.procs').write_text(str(os.getpid()))

    def windows(self):
        global _WINDOWS_JOB
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active_processes',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[(name,ctypes.c_ulonglong) for name in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
        class Extended(ctypes.Structure):_fields_=[('basic',Basic),('io',IO),('process_limit',ctypes.c_size_t),('job_limit',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        class CPU(ctypes.Structure):_fields_=[('flags',wintypes.DWORD),('rate',wintypes.DWORD)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.CreateJobObjectW.restype=wintypes.HANDLE;kernel.GetCurrentProcess.restype=wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        job=kernel.CreateJobObjectW(None,None)
        if not job:raise OSError(ctypes.get_last_error(),'Owned Windows Job Object creation failed')
        limits=Extended();limits.basic.flags=0x2000|0x200|0x8;limits.basic.active_processes=128;limits.job_limit=3*1024**3
        if not kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)):raise OSError(ctypes.get_last_error(),'Owned Windows memory/process limit failed')
        cpu=CPU(1|4,min(10000,max(1,int(20000/(os.cpu_count() or 2)))))
        if not kernel.SetInformationJobObject(job,15,ctypes.byref(cpu),ctypes.sizeof(cpu)):raise OSError(ctypes.get_last_error(),'Owned Windows CPU rate limit failed')
        if not kernel.AssignProcessToJobObject(job,kernel.GetCurrentProcess()):raise OSError(ctypes.get_last_error(),'Owned Windows controller job assignment failed')
        self.job=job;_WINDOWS_JOB=job
        self.win_kernel=kernel;self.win_limits_type=Extended

    def summary(self):
        result=dict(kernel=platform.system(),release=platform.release(),machine=platform.machine(),python=platform.python_version(),logical_cpus=os.cpu_count(),memory_limit_bytes=3*1024**3,pids_limit=128,cpu_quota_cores=2)
        if self.group:result.update(memory_peak_bytes=int((self.group/'memory.peak').read_text()),memory_events=(self.group/'memory.events').read_text(),cpu_stat=(self.group/'cpu.stat').read_text())
        if self.job:
            from ctypes import wintypes
            class Accounting(ctypes.Structure):_fields_=[('user',ctypes.c_longlong),('system',ctypes.c_longlong),('period_user',ctypes.c_longlong),('period_system',ctypes.c_longlong),('faults',wintypes.DWORD),('total_processes',wintypes.DWORD),('active_processes',wintypes.DWORD),('terminated',wintypes.DWORD)]
            query=self.win_kernel.QueryInformationJobObject;query.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
            limits=self.win_limits_type();accounting=Accounting()
            if not query(self.job,9,ctypes.byref(limits),ctypes.sizeof(limits),None) or not query(self.job,1,ctypes.byref(accounting),ctypes.sizeof(accounting),None):raise OSError(ctypes.get_last_error(),'Native Windows job accounting failed')
            result.update(windows_native_job_object=True,windows_peak_job_commit_bytes=limits.peak_job,job_cpu_user_seconds=accounting.user/10**7,job_cpu_system_seconds=accounting.system/10**7,active_job_processes=accounting.active_processes)
        result['attribution_scope']='Cumulative bounded controller/native job; kernel-specific memory counters are not pooled as comparable RSS measurements.'
        return result

    def close(self):
        if self.group:
            (self.original/'cgroup.procs').write_text(str(os.getpid()))
            if (self.group/'cgroup.kill').exists():(self.group/'cgroup.kill').write_text('1')
            for _ in range(20):
                try:self.group.rmdir();break
                except OSError:time.sleep(.1)
        # Windows retains its native kill-on-close job handle until this
        # controller exits. Closing a job containing ourselves here would kill
        # the controller before it can publish its final evidence.
