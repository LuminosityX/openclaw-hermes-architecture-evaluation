"""Control only the dedicated owned native-runtime cgroup, never the evaluator."""
from pathlib import Path
import os
import subprocess
import time

ROOT=Path('/native-control')


def members():return [int(v) for v in (ROOT/'procs').read_text().split()]


def freeze(value):
    (ROOT/'freeze').write_text('1' if value else '0');deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        events=dict(line.split() for line in (ROOT/'events').read_text().splitlines())
        if events.get('frozen')==('1' if value else '0'):return events
        time.sleep(.01)
    raise RuntimeError('Owned native-runtime cgroup did not confirm its actual freeze state')


def kill():
    (ROOT/'kill').write_text('1');deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        live=[]
        for pid in members():
            try:
                if Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[0]!='Z':live.append(pid)
            except (OSError,IndexError):pass
        if not live:return
        time.sleep(.01)
    raise RuntimeError('Owned native-runtime cgroup did not actually exit')


def environment_selfcheck():
    if not all((ROOT/name).is_file() for name in ['procs','freeze','kill','events']):raise RuntimeError('Explicit hosted native-runtime control profile is missing')
    def enter():(ROOT/'procs').write_text(str(os.getpid()))
    child=subprocess.Popen(['/usr/bin/python3','-c','import time;time.sleep(20)'],preexec_fn=enter,start_new_session=True)
    try:
        if child.pid not in members() or os.getpid() in members():raise RuntimeError('Owned native freeze scope includes the evaluator or excludes its actual child')
        frozen=freeze(True)
        if child.poll() is not None:raise RuntimeError('Owned native freeze child exited before the control')
        kill();child.wait(timeout=5)
        if child.returncode!=-9:raise RuntimeError('Owned native cgroup kill did not confirm actual process death')
        return dict(actual_child_pid=child.pid,evaluator_excluded=True,kernel_freeze=frozen,actual_kill_returncode=child.returncode)
    finally:
        freeze(False)
        if child.poll() is None:child.kill();child.wait(timeout=5)
