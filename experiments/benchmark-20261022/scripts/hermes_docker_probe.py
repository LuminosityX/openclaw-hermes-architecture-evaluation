#!/usr/bin/env python3
"""Native DockerEnvironment create/reuse and marker-command benchmark."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=int, default=30)
    p.add_argument("--warmups", type=int, default=5)
    p.add_argument("--output", type=Path, default=ROOT / "raw/hermes-docker.json")
    args = p.parse_args()
    profile = ROOT / "runtime/hermes-docker-profile"
    profile.mkdir(parents=True, exist_ok=True)
    workspace = ROOT / "fixtures/docker-workspace"
    workspace.mkdir(exist_ok=True)
    os.environ["HERMES_HOME"] = str(profile)
    os.environ["HERMES_RUNTIME_DIR"] = str(profile / "runtime")
    os.environ["DOCKER_HOST"] = "unix://" + str(ROOT / "runtime/docker/docker.sock")
    os.environ["PATH"] = str(ROOT / "envs/docker/docker") + os.pathsep + os.environ["PATH"]
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "sources/hermes"))
    from tools.environments.docker import DockerEnvironment, _cgroup_limits_available
    docker = str(ROOT / "envs/docker/docker/docker")
    # Native feature detection once outside timed samples, like a warmed runtime.
    cgroups_available = _cgroup_limits_available(IMAGE)
    samples = []
    config = {"image": IMAGE, "cwd": "/workspace", "cpu": 1, "memory": 512,
        "persistent_filesystem": False, "network": False, "volumes": [str(workspace) + ":/workspace:rw"],
        "auto_mount_cwd": False, "persist_across_processes": True, "extra_args": ["--pids-limit", "128"],
        "shm_size": "64m", "image_pinned": True}
    inspections = []
    errors = []
    cleanup_errors = []
    commit = subprocess.check_output(["git", "-C", str(ROOT / "sources/hermes"), "rev-parse", "HEAD"], text=True).strip()
    for index in range(args.warmups + args.samples):
        task_id = f"hermes-bench-{os.getpid()}-{index}"
        env = None
        container_id = None
        try:
            start = time.perf_counter_ns()
            env = DockerEnvironment(task_id=task_id, **config)
            create_end = time.perf_counter_ns()
            result = env.execute("sh -lc 'printf BENCH_READY'")
            end = time.perf_counter_ns()
            container_id = env._container_id
            if not inspections:
                inspect = json.loads(subprocess.check_output([docker, "inspect", container_id], text=True))[0]
                inspections.append({"container_id": container_id, "HostConfig": inspect["HostConfig"], "Mounts": inspect["Mounts"]})
            # A new backend handle reattaches the same running container (not just an in-memory exec).
            reuse_start = time.perf_counter_ns()
            reused = DockerEnvironment(task_id=task_id, **config)
            reuse_init_end = time.perf_counter_ns()
            warm_result = reused.execute("sh -lc 'printf BENCH_READY'")
            reuse_end = time.perf_counter_ns()
            # Docker run returns full ID; native ps lookup returns its 12-character prefix.
            same_id = reused._container_id[:12] == container_id[:12]
            if index >= args.warmups:
                samples.extend([
                    {"framework": "hermes", "row": 6, "metric": "cold_create_and_command", "sample": index-args.warmups,
                        "duration_ms": (end-start)/1e6, "initialize_ms": (create_end-start)/1e6,
                        "correct": result.get("returncode") == 0 and "BENCH_READY" in result.get("output", ""), "result": result},
                    {"framework": "hermes", "row": 6, "metric": "warm_reattach_and_command", "sample": index-args.warmups,
                        "duration_ms": (reuse_end-reuse_start)/1e6, "initialize_ms": (reuse_init_end-reuse_start)/1e6,
                        "same_container": same_id, "cold_container_id": container_id, "warm_container_id": reused._container_id,
                        "correct": same_id and warm_result.get("returncode") == 0 and "BENCH_READY" in warm_result.get("output", ""), "result": warm_result}])
            # Both handles point at this one owned container; direct owned-ID removal avoids a 10s stop grace.
        except Exception as exc:
            errors.append({"index": index, "error": str(exc), "type": type(exc).__name__})
            break
        finally:
            if env is not None:
                container_id = container_id or env._container_id
            # The label is unique to this process/sample; it also finds a container created before __init__ raised.
            owned = subprocess.run([docker, "ps", "-aq", "--filter", "label=hermes-agent=1", "--filter", "label=hermes-task-id=" + task_id], capture_output=True, text=True)
            if owned.returncode:
                cleanup_errors.append({"index": index, "step": "list_owned", "returncode": owned.returncode, "stderr": owned.stderr})
            ids = set(owned.stdout.split())
            if container_id:
                ids.add(container_id)
            # Normalize full/prefix IDs before removing, as Docker's ps uses short IDs.
            deduped = {value[:12] for value in ids}
            for owned_id in deduped:
                removed = subprocess.run([docker, "rm", "-f", owned_id], check=False, capture_output=True, text=True)
                if removed.returncode:
                    cleanup_errors.append({"index": index, "step": "remove_owned", "container": owned_id, "returncode": removed.returncode, "stderr": removed.stderr})
    payload = {"schema_version": 1, "framework": "hermes", "commit": commit, "config": config, "cgroups_available": cgroups_available,
        "entrypoint": "tools.environments.docker.DockerEnvironment.__init__ and .execute",
        "scope": "Native backend module; imports/cgroup capability detection and image download excluded. Cold container absent, warm new backend handle reattaches running container. Native init_session shell snapshot is included. Cleanup excluded.",
        "warmups": args.warmups, "samples_per_case": args.samples, "inspections": inspections, "samples": samples, "errors": errors, "cleanup_errors": cleanup_errors}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2))
    limits_correct = all(x["HostConfig"].get("NanoCpus") == 1000000000 and x["HostConfig"].get("Memory") == 536870912 and x["HostConfig"].get("PidsLimit") == 128 and x["HostConfig"].get("NetworkMode") == "none" for x in inspections)
    ok = args.samples > 0 and len(samples) == 2 * args.samples and bool(inspections) and not errors and not cleanup_errors and limits_correct and all(x["correct"] for x in samples)
    print(json.dumps({"output": str(args.output), "samples": len(samples), "all_correct": ok, "errors": errors}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
