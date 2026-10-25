"""Start a new task-owned Docker daemon without changing the host Docker service."""
import json
import os
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
binary = root / "envs/docker/docker"
runtime = root / "runtime/docker"
runtime.mkdir(parents=True, exist_ok=True)
sock = runtime / "docker.sock"
env = dict(os.environ)
env["PATH"] = str(binary) + os.pathsep + env.get("PATH", "")
client = [str(binary / "docker"), "--host", f"unix://{sock}"]
probe = subprocess.run(client + ["info", "--format", "{{json .ServerVersion}}"], env=env, capture_output=True, text=True)
if probe.returncode == 0:
    print(json.dumps({"status": "already_ready", "version": probe.stdout.strip(), "socket": str(sock)}))
    raise SystemExit(0)
pidfile = runtime / "docker.pid"
if pidfile.exists():
    old_pid = int(pidfile.read_text())
    try:
        os.kill(old_pid, 0)
    except ProcessLookupError:
        pass
    else:
        raise SystemExit(f"Task daemon PID {old_pid} is running but unhealthy; inspect logs before recovery")
command = [str(binary / "dockerd"), f"--host=unix://{sock}", f"--data-root={runtime / 'data'}", f"--exec-root={runtime / 'exec'}", f"--pidfile={pidfile}", "--bridge=none", "--iptables=false", "--ip6tables=false", "--ip-forward=false", "--ip-masq=false", "--storage-driver=overlay2"]
with (root / "logs/docker-daemon.log").open("ab") as log:
    process = subprocess.Popen(command, env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
for attempt in range(60):
    if process.poll() is not None:
        raise SystemExit(f"Daemon exited {process.returncode}; see logs/docker-daemon.log")
    probe = subprocess.run(client + ["info", "--format", "{{json .ServerVersion}}"], env=env, capture_output=True, text=True)
    if probe.returncode == 0:
        (root / "results/docker-runtime.json").write_text(json.dumps({"daemon_pid": process.pid, "socket": str(sock), "command": command, "version": probe.stdout.strip()}, indent=2))
        print(json.dumps({"status": "ready", "pid": process.pid, "version": probe.stdout.strip(), "socket": str(sock)}))
        break
    time.sleep(0.5)
else:
    raise SystemExit("Task Docker daemon did not become ready within 30 seconds")
