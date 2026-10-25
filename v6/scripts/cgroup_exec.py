import os,sys
from pathlib import Path
group=Path(sys.argv[1]);(group/'cgroup.procs').write_text(str(os.getpid()))
cmd=sys.argv[2:];os.execvp(cmd[0],cmd)
