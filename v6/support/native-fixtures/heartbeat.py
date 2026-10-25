import json,os,subprocess,sys,time
from pathlib import Path
prefix=Path(sys.argv[1]);prefix.parent.mkdir(parents=True,exist_ok=True)
child=subprocess.Popen([sys.executable,'-u','-c','import pathlib,sys,time\np=pathlib.Path(sys.argv[1])\nwhile True:\n p.write_text(str(time.time_ns()));time.sleep(.05)',str(prefix)+'.beat'])
Path(str(prefix)+'.pids').write_text(json.dumps([os.getpid(),child.pid]))
print('HEARTBEAT_READY',flush=True)
while True:time.sleep(.1)
