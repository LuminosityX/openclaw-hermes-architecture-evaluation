import json, pathlib, subprocess, time, os
ROOT=pathlib.Path(__file__).resolve().parents[1]
R=ROOT/'runtime/extended-integration/ssh';R.mkdir(parents=True,exist_ok=True)
os.chmod(R,0o700)
for name in ['client','host1','host2']:
 p=R/name
 if not p.exists():subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(p)],check=True)
(R/'authorized_keys').write_text((R/'client.pub').read_text()); os.chmod(R/'authorized_keys',0o600)
pathlib.Path('/run/sshd').mkdir(exist_ok=True)
rows=[]
for n in [1,2]:
 d=R/f'node{n}';d.mkdir(exist_ok=True);(d/'identity.txt').write_text(f'endpoint-{n}');(d/'resource.json').write_text(json.dumps({'endpoint':n,'value':n*17}))
 port=40300+n
 conf=R/f'sshd{n}.conf';conf.write_text(f'Port {port}\nListenAddress 127.0.0.1\nHostKey {R}/host{n}\nPidFile {R}/pid{n}\nAuthorizedKeysFile {R}/authorized_keys\nStrictModes no\nPermitRootLogin prohibit-password\nPasswordAuthentication no\nKbdInteractiveAuthentication no\nUsePAM no\nPrintMotd no\nSubsystem sftp internal-sftp\n')
 with (R/f'sshd{n}.log').open('a') as log:p=subprocess.Popen(['/usr/sbin/sshd','-D','-f',str(conf)],stdout=log,stderr=log,start_new_session=True)
 rows.append({'endpoint':n,'port':port,'directory':str(d),'pid':p.pid})
(R/'endpoints.json').write_text(json.dumps(rows,indent=2))
print(json.dumps({'endpoints':rows,'scope':'Dedicated loopback SSH services on same physical host; distinct fixture directories, not physical cloud nodes or isolation benchmark.'}))
