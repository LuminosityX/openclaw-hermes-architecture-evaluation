#!/usr/bin/env python3
"""Create one native Hermes Docker sandbox for external kernel-quota tests.

The caller owns cleanup: docker rm -f the exact container ID emitted in the result.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", default=f"hermes-quota-{os.getpid()}")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    profile = ROOT / "runtime/hermes-quota-profile"
    profile.mkdir(parents=True, exist_ok=True)
    workspace = ROOT / "fixtures/docker-workspace"
    workspace.mkdir(exist_ok=True)
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.environ["DOCKER_HOST"] = "unix://" + str(ROOT / "runtime/docker/docker.sock")
    os.environ["PATH"] = str(ROOT / "envs/docker/docker") + os.pathsep + os.environ["PATH"]
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    from tools.environments.docker import DockerEnvironment
    env = DockerEnvironment(image=IMAGE, cwd="/workspace", cpu=1, memory=512, network=False,
        volumes=[str(workspace) + ":/workspace:rw"], auto_mount_cwd=False,
        persistent_filesystem=False, persist_across_processes=True,
        extra_args=["--pids-limit", "128", "--memory-swap", "512m"], shm_size="64m", image_pinned=True, task_id=args.run_id)
    result = env.execute("sh -lc 'printf BENCH_READY'")
    docker = str(ROOT / "envs/docker/docker/docker")
    inspection = json.loads(subprocess.check_output([docker, "inspect", env._container_id], text=True))[0]
    limits = inspection["HostConfig"]
    payload = {"framework": "hermes", "row": 26,
        "commit": subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip(),
        "entrypoint": "tools.environments.docker.DockerEnvironment", "run_id": args.run_id,
        "container_id": inspection["Id"], "HostConfig": limits, "Mounts": inspection["Mounts"],
        "ready_result": result, "limits_match": limits.get("NanoCpus") == 1000000000 and limits.get("Memory") == 536870912 and limits.get("MemorySwap") == 536870912 and limits.get("PidsLimit") == 128 and limits.get("NetworkMode") == "none",
        "cleanup_required": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    print(json.dumps({"output": str(args.output), "container_id": payload["container_id"], "limits_match": payload["limits_match"]}))


if __name__ == "__main__":
    main()
