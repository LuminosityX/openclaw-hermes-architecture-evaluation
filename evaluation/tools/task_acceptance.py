"""Evaluate generated code in a separate PID/network/mount/resource boundary."""
import json
from contextlib import contextmanager
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import time
import uuid

from suite import ROOT


@contextmanager
def acceptance_group():
    group=Path('/sys/fs/cgroup/system.slice')/('openclaw-task-oracle-'+uuid.uuid4().hex[:12]+'.scope')
    if os.geteuid()!=0: raise RuntimeError('Hosted acceptance cgroup requires root')
    group.mkdir()
    try:
        for name,value in {'memory.max':256*1024**2,'memory.swap.max':0,'pids.max':32,'cpu.max':'100000 100000','memory.oom.group':1}.items():
            (group/name).write_text(str(value))
        yield group
    finally:
        if (group/'cgroup.procs').read_text().strip(): (group/'cgroup.kill').write_text('1')
        for _ in range(30):
            try:
                group.rmdir()
                break
            except OSError: time.sleep(.05)


def function_results(task,content):
    if not isinstance(content,str) or len(content.encode())>128*1024: return None
    oracle=task['oracle']
    if oracle['kind']!='python-function': raise ValueError('Expected a function task')
    with acceptance_group() as group,tempfile.TemporaryDirectory(prefix='openclaw-task-acceptance-') as directory:
        root=Path(directory)
        (root/'solution.py').write_text(content)
        command=['bwrap','--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--unshare-cgroup',
            '--die-with-parent','--new-session','--clearenv','--cap-drop','ALL',
            '--ro-bind','/usr','/usr','--symlink','usr/bin','/bin','--symlink','usr/lib','/lib',
            '--symlink','usr/lib64','/lib64','--proc','/proc','--dev','/dev',
            '--size',str(8*1024**2),'--tmpfs','/tmp','--ro-bind',str(root),'/artifact',
            '--ro-bind',str(ROOT/'evaluation/runner/function_probe.py'),'/probe.py',
            '--setenv','PATH','/usr/bin:/bin','--setenv','PYTHONDONTWRITEBYTECODE','1',
            '--chdir','/artifact','--','/usr/bin/python3','-I','/probe.py']
        def limits():
            (group/'cgroup.procs').write_text(str(os.getpid()))
            resource.setrlimit(resource.RLIMIT_CORE,(0,0))
            resource.setrlimit(resource.RLIMIT_CPU,(2,2))
            resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,256*1024**2))
            resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024,128*1024))
            resource.setrlimit(resource.RLIMIT_NPROC,(32,32))
        # Keep pipe reads bounded even if generated code floods stdout.
        with tempfile.TemporaryFile() as stdout,tempfile.TemporaryFile() as stderr:
            try:
                result=subprocess.run(command,input=json.dumps({k:oracle[k] for k in ['function','inputs']}).encode(),
                    stdout=stdout,stderr=stderr,env={},timeout=5,preexec_fn=limits,check=False)
                if result.returncode: return None
                stdout.seek(0);raw=stdout.read(128*1024+1)
                if len(raw)>128*1024: return None
                marker=b'EVAL_FUNCTION_RESULTS:'
                lines=[line[len(marker):] for line in raw.splitlines() if line.startswith(marker)]
                if len(lines)!=1:return None
                return json.loads(lines[0])
            except (OSError,ValueError,subprocess.TimeoutExpired): return None
