"""Only derived native transport authority enters this unprivileged namespace."""
import json
import os
from pathlib import Path
import subprocess
import time

spec=json.loads(Path('/input/spec.json').read_text())
for name in ['state','workspace','tmp','home','cache','run']:(Path('/scratch')/name).mkdir()
config=dict(gateway=dict(mode='remote',remote=dict(url='wss://'+spec['host'],token=spec['native_token'])),nodeHost=dict(workerRuns=dict(enabled=True,capacity=1,isolation='none')),logging=dict(level='debug',consoleLevel='info',file='/scratch/node-native.log'))
Path('/scratch/config.json').write_text(json.dumps(config))
env=dict(os.environ,OPENCLAW_STATE_DIR='/scratch/state',OPENCLAW_CONFIG_PATH='/scratch/config.json',OPENCLAW_GATEWAY_TOKEN=spec['native_token'])
process=subprocess.Popen(['/toolchain/node','/runtime/node_modules/openclaw/openclaw.mjs','node','run','--host',spec['host'],'--port','443','--tls','--display-name','owned-multihost-worker','--session-host'],env=env,stdout=Path('/evidence/native-node.log').open('w'),stderr=subprocess.STDOUT)
try:
    until=time.monotonic()+100
    identity=Path('/scratch/state/identity/device.json')
    while not identity.is_file() and time.monotonic()<until:
        if process.poll() is not None:raise RuntimeError('Actual native node exited before publishing its own device identity')
        time.sleep(.2)
    if not identity.is_file():raise RuntimeError('Actual native node identity did not appear')
    data=json.loads(identity.read_text());public={k:data[k] for k in ['deviceId','publicKeyPem'] if k in data}
    if not public.get('deviceId') or not public.get('publicKeyPem'):raise RuntimeError('Actual native node public identity fields are unavailable')
    Path('/evidence/node-public.json').write_text(json.dumps(public)+'\n')
    process.wait(timeout=1100)
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
