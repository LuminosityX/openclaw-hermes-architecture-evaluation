"""Public runtime plumbing only: loopback HTTP to a single mounted Unix socket."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time

active_forwards = 0
forward_lock = threading.Lock()

class Forward(socketserver.BaseRequestHandler):
    def handle(self):
        global active_forwards
        with forward_lock:
            active_forwards += 1
        try:
            self.forward()
        finally:
            with forward_lock:
                active_forwards -= 1

    def forward(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect('/relay/api.sock')
            channels = [self.request, upstream]
            while channels:
                readable, _, _ = select.select(channels, [], [], 1)
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

class Reverse(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.create_connection(('127.0.0.1', int(os.environ['EVAL_CONTROL_PORT']))) as upstream:
            while True:
                ready, _, _ = select.select([self.request, upstream], [], [], 1)
                for source in ready:
                    chunk = source.recv(65536)
                    if not chunk:
                        return
                    (upstream if source is self.request else self.request).sendall(chunk)

class ReverseServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

server = Server(('127.0.0.1', 18080), Forward)
threading.Thread(target=server.serve_forever, daemon=True).start()
reverse_server = None
if os.environ.get('EVAL_CONTROL_PORT'):
    Path('/state/control.sock').unlink(missing_ok=True)
    reverse_server = ReverseServer('/state/control.sock', Reverse)
    threading.Thread(target=reverse_server.serve_forever, daemon=True).start()
with socket.socket() as network_probe:
    network_probe.settimeout(0.5)
    external_connect_status = network_probe.connect_ex(('1.1.1.1', 443))
probe = {
    'workspace_readable': Path('/workspace/PROMPT.md').is_file(),
    'coordinator_package_absent': not Path('/root/Downloads/1023magnitude/agent_eval_handoff').exists(),
    'coordinator_workspace_absent': not Path('/root/Documents/Codex').exists(),
    'private_directory_absent': not Path('/evaluator_private').exists(),
    'host_root_via_proc_absent': not Path('/proc/1/root/root/Downloads/1023magnitude/agent_eval_handoff').exists(),
    'direct_network_blocked': external_connect_status != 0,
    'default_user_history_absent': not Path('/root/.codex/config.toml').exists(),
    'network_interfaces': sorted(Path('/sys/class/net').glob('*')) if Path('/sys/class/net').exists() else 'sysfs_not_mounted',
    'pid_namespace_verified_by_parent': True,
}
probe['network_interfaces'] = str(probe['network_interfaces'])
Path('/state/isolation_check.json').write_text(json.dumps(probe, indent=2) + '\n')
if not all(value for key, value in probe.items() if key.endswith('_absent') or key in ['workspace_readable', 'direct_network_blocked']):
    raise SystemExit('Runtime isolation check failed.')
if sys.argv[1:] == ['--check']:
    print(json.dumps(probe))
    server.shutdown()
    raise SystemExit(0)
process = subprocess.Popen(sys.argv[1:], start_new_session=True)

def stop(signum, frame):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
result = process.wait()
drain_begin = time.monotonic()
quiet_since = None
while time.monotonic() - drain_begin < 20:
    with forward_lock:
        pending = active_forwards
    if pending == 0:
        quiet_since = quiet_since or time.monotonic()
        if time.monotonic() - quiet_since >= 2:
            break
    else:
        quiet_since = None
    time.sleep(.1)
Path('/state/network_drain.json').write_text(json.dumps({'duration_seconds':time.monotonic()-drain_begin,'active_connections_after_drain':pending})+'\n')
server.shutdown()
raise SystemExit(result)
