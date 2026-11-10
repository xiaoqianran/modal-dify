"""Build a Dify 1.19.0 VM snapshot caching only active Docker images.

Usage: python scripts/build_cache.py --plan
       python scripts/build_cache.py --build

--build creates a billable Modal VM and pulls full Dify image set.
No production Dify services are started.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = ROOT / "vendor" / "dify-1.19.0"
VERSION = "1.19.0"
APP_NAME = "modal-dify-cache-builder"
IMAGE_NAME = "modal-dify-docker-cache-1-19-0"
PARALLEL = 4
MAX_VM_SECONDS = 7200

BASE = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("docker.io", "iptables", "procps", "ca-certificates")
    .add_local_dir(DOCKER_DIR, remote_path="/opt/dify/docker", copy=True)
)

# Keep this small and independent of runtime environment variables.
VM_SCRIPT = r"""
set -euo pipefail
mkdir -p /etc/docker
printf '{"max-concurrent-downloads": 6}\n' >/etc/docker/daemon.json
dockerd -H unix:///var/run/docker.sock >/tmp/modal-dify-dockerd.log 2>&1 &
for i in $(seq 1 90); do
    if docker info >/dev/null 2>&1; then echo DOCKER_READY; exit 0; fi
    sleep 2
done
tail -n 100 /tmp/modal-dify-dockerd.log
exit 1
"""

# Remote script performs controlled concurrent pulls and fails the stage if any fails.
PULL_SCRIPT = r"""
import concurrent.futures,json,subprocess,time,os
refs=json.loads(os.environ["DIFY_IMAGE_REFS"])
workers=int(os.environ["DIFY_PARALLEL"])
def pull(ref):
    start=time.monotonic()
    p=subprocess.run(["docker","pull",ref],capture_output=True,text=True,timeout=3600)
    print(json.dumps({"ref":ref,"rc":p.returncode,"seconds":round(time.monotonic()-start,2),
                      "stdout_tail":p.stdout[-350:],"stderr_tail":p.stderr[-800:]}),flush=True)
    if p.returncode:
        raise RuntimeError("Pull failed: "+ref)
    p=subprocess.run(["docker","image","inspect","--format","{{.Id}}",ref],capture_output=True,text=True,check=True)
    return ref,p.stdout.strip()
with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
    results=dict(pool.map(pull,refs))
print("CACHE_MANIFEST="+json.dumps(results,sort_keys=True),flush=True)
"""


def manifest() -> list[str]:
    # Run Compose using official complete environment. No tokens are committed.
    tmp_env = DOCKER_DIR / ".env"
    if tmp_env.exists():
        raise RuntimeError("Unexpected runtime .env inside pinned vendor directory")
    try:
        tmp_env.write_bytes((DOCKER_DIR / ".env.example").read_bytes())
        p = subprocess.run(
            ["docker", "compose", "--project-directory", str(DOCKER_DIR),
             "-f", str(DOCKER_DIR / "docker-compose.yaml"), "config", "--images"],
            capture_output=True, text=True, check=True,
        )
        refs = sorted(set(x.strip() for x in p.stdout.splitlines() if x.strip()))
    finally:
        tmp_env.unlink(missing_ok=True)
    if len(refs) != 12:
        raise RuntimeError(f"Expected 12 active image references, got {len(refs)}: {refs}")
    if any("$" in r for r in refs):
        raise RuntimeError("Unresolved image variable in Compose config")
    return refs


def run(sb, *args, timeout=300, env=None):
    p = sb.exec(*args, timeout=timeout, env=env)
    stdout=p.stdout.read()
    stderr=p.stderr.read()
    p.wait()
    if p.returncode:
        raise RuntimeError(f"failed {args}: {stdout[-1500:]} {stderr[-1500:]}")
    return stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--plan", action="store_true")
    group.add_argument("--build", action="store_true")
    args = parser.parse_args()
    refs = manifest()
    print(json.dumps({"version":VERSION,"compose_images":refs,
                      "parallel":PARALLEL,"named_image":IMAGE_NAME},indent=2),flush=True)
    if args.plan:
        return

    sb = None
    t0=time.monotonic()
    app=modal.App.lookup(APP_NAME,create_if_missing=True)
    try:
        sb=modal.Sandbox.create("sleep",str(MAX_VM_SECONDS-30),
                app=app, image=BASE, runtime="vm", cpu=4, memory=16384,
                timeout=MAX_VM_SECONDS)
        print("BUILDER_VM",sb.object_id,flush=True)
        print(run(sb,"bash","-lc",VM_SCRIPT,timeout=240),flush=True)
        # Do not put secrets in image/snapshot.
        result=run(sb,"python3","-c",PULL_SCRIPT,timeout=5000,
                   env={"DIFY_IMAGE_REFS":json.dumps(refs),"DIFY_PARALLEL":str(PARALLEL)})
        print(result,flush=True)
        if "CACHE_MANIFEST=" not in result:
            raise RuntimeError("Docker manifest missing; refusing snapshot")
        print("STOP_DOCKER",run(sb,"bash","-lc",
            "kill -TERM $(pidof dockerd); for i in $(seq 1 60); do "
            "if ! pidof dockerd >/dev/null; then exit 0; fi; sleep 1; done; exit 1",timeout=75),flush=True)
        snapshot=sb.snapshot_filesystem(timeout=900,ttl=None)
        print("SNAPSHOT_ID",snapshot.object_id,flush=True)
        snapshot.publish(IMAGE_NAME)
        print("PUBLISHED",IMAGE_NAME,"elapsed_seconds",round(time.monotonic()-t0,2),flush=True)
    finally:
        if sb is not None:
            try:
                sb.terminate()
                print("TERMINATED",sb.object_id,flush=True)
            except Exception as e:
                print("WARNING_TERMINATE_FAILED",repr(e),flush=True)


if __name__ == "__main__":
    main()
