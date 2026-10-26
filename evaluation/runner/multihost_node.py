"""Only derived native transport authority enters this unprivileged namespace."""
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import base64
import hashlib
import time

spec=json.loads(Path('/input/spec.json').read_text())
for name in ['state','workspace','tmp','home','cache','run']:(Path('/scratch')/name).mkdir()
config=dict(gateway=dict(mode='remote',remote=dict(url='wss://'+spec['host'],token=spec['native_token'])),nodeHost=dict(workerRuns=dict(enabled=True,capacity=1,isolation='none')),logging=dict(level='debug',consoleLevel='info',file='/scratch/node-native.log'))
Path('/scratch/config.json').write_text(json.dumps(config))
env=dict(os.environ,OPENCLAW_STATE_DIR='/scratch/state',OPENCLAW_CONFIG_PATH='/scratch/config.json',OPENCLAW_GATEWAY_TOKEN=spec['native_token'])
process=subprocess.Popen(['/toolchain/node','/runtime/node_modules/openclaw/openclaw.mjs','node','run','--host',spec['host'],'--port','443','--tls','--display-name','owned-multihost-worker','--session-host'],env=env,stdout=Path('/evidence/native-node.log').open('w'),stderr=subprocess.STDOUT)
try:
    until=time.monotonic()+100
    public=None
    while public is None and time.monotonic()<until:
        if process.poll() is not None:raise RuntimeError('Actual native node exited before publishing its own device identity')
        found=[]
        for database in Path('/scratch/state').rglob('*.sqlite'):
            connection=sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True,timeout=2)
            try:
                if connection.execute("select 1 from sqlite_master where type='table' and name='device_identities'").fetchone():
                    found.extend(connection.execute('select device_id,public_key_pem from device_identities limit 2').fetchall())
            finally:connection.close()
        if len(found)>1:raise RuntimeError('Fresh native node public identity is ambiguous')
        if found:
            device,pem=found[0];der=base64.b64decode(''.join(line for line in pem.splitlines() if not line.startswith('---')))
            if hashlib.sha256(der[-32:]).hexdigest()!=device:raise RuntimeError('Native public key does not bind its actual device ID')
            public=dict(deviceId=device,publicKeyPem=pem,source='read-only canonical SQLite public columns; private-key column never queried')
        else:time.sleep(.2)
    if public is None:raise RuntimeError('Actual canonical native node public identity did not appear')
    Path('/evidence/node-public.json').write_text(json.dumps(public)+'\n')
    process.wait(timeout=1100)
finally:
    if process.poll() is None:process.terminate();process.wait(timeout=10)
