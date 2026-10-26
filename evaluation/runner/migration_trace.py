"""Linux x86-64: stop only at an actual owned SQLite WAL schema-page write."""
import ctypes
import errno
import hashlib
import os
from pathlib import Path
import signal
import struct
import subprocess
import time

import native_freeze

LIBC=ctypes.CDLL(None,use_errno=True)
LIBC.ptrace.restype=ctypes.c_long
class Registers(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in 'r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()]

def trace(request,pid,address=0,data=0):
    result=LIBC.ptrace(ctypes.c_uint(request),ctypes.c_uint(pid),ctypes.c_void_p(address),ctypes.c_void_p(data))
    if result==-1 and ctypes.get_errno():raise OSError(ctypes.get_errno(),'Owned migration ptrace operation failed')
    return result

def read_memory(pid,address,size):
    if not 0<size<=131072:raise RuntimeError('Migration syscall buffer exceeds bound')
    # /proc/PID/mem reads only the traced owned child's write buffer.
    fd=os.open('/proc/'+str(pid)+'/mem',os.O_RDONLY)
    try:return os.pread(fd,size,address)
    finally:os.close(fd)

def schema_payload(data,version,cookie):
    for start in (0,24):
        if data[start:start+16]==b'SQLite format 3\0' and len(data)>=start+100:
            observed_cookie=int.from_bytes(data[start+40:start+44],'big')
            observed_version=int.from_bytes(data[start+60:start+64],'big')
            if observed_cookie>cookie and observed_version==version:
                return dict(schema_cookie=observed_cookie,user_version=observed_version,payload_offset=start)
    return None

def interrupt(command,env,database,old_cookie,new_version,boundary,log_path,timeout=150):
    if os.uname().machine!='x86_64':raise RuntimeError('Native migration syscall decoder requires actual Linux x86-64')
    database=database.resolve();wal=str(database)+'-wal'
    # A stopped preexec cannot be used with Popen's exec-error pipe: use a tiny
    # exec wrapper which requests tracing after Popen has completed its exec.
    wrapper=Path('/driver/migration_trace_child.py')
    with log_path.open('w') as output:
        process=subprocess.Popen(['/usr/bin/python3',str(wrapper),*command],env=env,stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        initial,status=os.waitpid(process.pid,os.WUNTRACED)
        if initial!=process.pid or not os.WIFSTOPPED(status):raise RuntimeError('Owned trace child did not reach native tracing boundary')
        options=1|2|4|8|0x40|0x100000 # syscall, fork/vfork/clone/exec, exit-kill
        trace(0x4200,process.pid,0,options)
        active={process.pid};headers={};pending={};observation=None;deadline=time.monotonic()+timeout
        trace(24,process.pid)
        try:
            while active and time.monotonic()<deadline and observation is None:
                pid,status=os.waitpid(-1,os.WNOHANG|0x40000000)
                if not pid:time.sleep(.0005);continue
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    active.discard(pid)
                    if pid==process.pid:process.returncode=os.waitstatus_to_exitcode(status)
                    continue
                if not os.WIFSTOPPED(status):continue
                sig=os.WSTOPSIG(status);event=status>>16
                if event in (1,2,3):
                    new=ctypes.c_ulonglong();trace(0x4201,pid,0,ctypes.addressof(new));active.add(new.value)
                if sig==(signal.SIGTRAP|0x80):
                    regs=Registers();trace(12,pid,0,ctypes.addressof(regs))
                    info=ctypes.create_string_buffer(128)
                    trace(0x420e,pid,128,ctypes.addressof(info))
                    operation=info.raw[0]
                    if operation not in {1,2}:raise RuntimeError('Kernel did not identify syscall entry/exit for owned migration tracing')
                    is_entry=operation==1
                    if is_entry and regs.orig_rax==18:
                        try:destination=os.readlink('/proc/'+str(pid)+'/fd/'+str(regs.rdi))
                        except OSError:destination=None
                        if destination==wal and 0<regs.rdx<=131072:
                            data=read_memory(pid,regs.rsi,regs.rdx);offset=regs.r10
                            # SQLite's separate 24-byte WAL frame header is the
                            # authoritative page/commit marker for its payload.
                            if len(data)>=24 and offset>=32 and len(data)==24:
                                headers[offset+24]=dict(page=int.from_bytes(data[:4],'big'),commit_pages=int.from_bytes(data[4:8],'big'))
                            header=headers.get(offset)
                            if len(data)>24 and offset>=32 and data[24:40]==b'SQLite format 3\0':
                                header=dict(page=int.from_bytes(data[:4],'big'),commit_pages=int.from_bytes(data[4:8],'big'))
                            payload=schema_payload(data,new_version,old_cookie)
                            if payload and header and header['page']==1 and header['commit_pages']==0:
                                match=dict(actual_syscall='pwrite64',pid=pid,wal_path=wal,offset=offset,bytes=regs.rdx,buffer_sha256=hashlib.sha256(data).hexdigest(),frame=header,**payload)
                                if boundary=='before':observation=dict(boundary='before-uncommitted-schema-page-write',**match)
                                else:pending[pid]=match
                    elif not is_entry and pid in pending:
                        match=pending.pop(pid)
                        if regs.rax!=match['bytes']:raise RuntimeError('Actual schema-page write failed before fault injection')
                        observation=dict(boundary='after-uncommitted-schema-page-write-before-commit',write_return_bytes=regs.rax,**match)
                if observation is None:
                    delivery=0 if sig in {signal.SIGTRAP,signal.SIGTRAP|0x80,signal.SIGSTOP} else sig
                    try:trace(24,pid,0,delivery)
                    except OSError as error:
                        if error.errno!=errno.ESRCH:raise
            if observation is None:raise RuntimeError('No proven uncommitted schema-page migration write was reached before native exit/timeout')
        finally:
            (native_freeze.ROOT/'kill').write_text('1')
            for pid in active:
                try:trace(7,pid,0,signal.SIGKILL)
                except OSError:pass
            until=time.monotonic()+5
            while active and time.monotonic()<until:
                try:pid,status=os.waitpid(-1,os.WNOHANG|0x40000000)
                except ChildProcessError:break
                if not pid:time.sleep(.01);continue
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    active.discard(pid)
                    if pid==process.pid:process.returncode=os.waitstatus_to_exitcode(status)
                else:
                    try:trace(7,pid,0,signal.SIGKILL)
                    except OSError:pass
            process.returncode=-9 if process.returncode is None else process.returncode
    observation['native_trace_output']=log_path.read_text()[-6000:]
    return observation
