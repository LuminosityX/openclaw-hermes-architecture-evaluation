"""Owned child enters its cgroup, requests parent tracing, then execs native CLI."""
import ctypes
import os
from pathlib import Path
import signal
import sys
(Path('/native-control')/'procs').write_text(str(os.getpid()))
libc=ctypes.CDLL(None,use_errno=True)
if libc.ptrace(0,0,None,None)!=0:raise OSError(ctypes.get_errno(),'Owned TRACEME failed')
os.kill(os.getpid(),signal.SIGSTOP)
os.execvpe(sys.argv[1],sys.argv[1:],os.environ)
