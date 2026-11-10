"""Temporary low-cost Docker layer cache smoke test on Modal VM.

Does NOT launch Dify or expose ports. Requires Modal login.
Creates up to two short-lived 2 CPU, 4 GiB VM Sandboxes, terminated in finally.
A snapshot is retained for 1 hour; it is not published as a named image.
"""
import json
import time
import traceback

import modal

APP = "modal-dify-cache-smoke"
BASE = modal.Image.debian_slim(python_version="3.12").apt_install("docker.io", "iptables", "procps")
TEST_IMAGES = ("busybox:1.37.0", "redis:6-alpine")
START_CMD = ("bash", "-lc", "dockerd -H unix:///var/run/docker.sock > /tmp/dockerd.log 2>&1 & exec sleep 1000")


def execute(sb, *cmd, timeout=120, check=True):
    p = sb.exec(*cmd, timeout=timeout)
    out = p.stdout.read()
    err = p.stderr.read()
    p.wait()
    if check and p.returncode:
        raise RuntimeError(f"Exit {p.returncode}, command={cmd!r}, stdout={out[-600:]!r}, stderr={err[-600:]!r}")
    return out.strip()


def boot(app, image):
    sb = modal.Sandbox.create(
        *START_CMD,
        app=app,
        image=image,
        runtime="vm",
        cpu=2,
        memory=4096,
        timeout=900,
    )
    for _ in range(45):
        try:
            execute(sb, "docker", "info", "--format", "{{.ServerVersion}}", timeout=6)
            return sb
        except Exception:
            time.sleep(2)
    print("dockerd log:", execute(sb, "sh", "-lc", "tail -60 /tmp/dockerd.log", check=False), flush=True)
    raise RuntimeError("Docker daemon did not start in 90 seconds")


def main():
    sb = restored = None
    t0 = time.monotonic()
    app = modal.App.lookup(APP, create_if_missing=True)
    try:
        sb = boot(app, BASE)
        print("FIRST_VM", sb.object_id, flush=True)
        for ref in TEST_IMAGES:
            t = time.monotonic()
            print("PULL", ref, flush=True)
            execute(sb, "docker", "pull", ref, timeout=270)
            print("PULL_OK", ref, "seconds", round(time.monotonic()-t, 2), flush=True)
        before = {ref: execute(sb, "docker", "image", "inspect", "--format", "{{.Id}}", ref) for ref in TEST_IMAGES}
        print("IDS_BEFORE", json.dumps(before), flush=True)
        print("STOP_DOCKER", execute(sb, "sh", "-lc",
              "kill -TERM $(pidof dockerd); for i in $(seq 1 30); do "
              "if ! pidof dockerd >/dev/null; then exit 0; fi; sleep 1; done; exit 1", timeout=45), flush=True)
        t = time.monotonic()
        snapshot = sb.snapshot_filesystem(timeout=300, ttl=3600)
        print("SNAPSHOT", snapshot.object_id, "seconds", round(time.monotonic()-t, 2), flush=True)
        sb.terminate()
        sb = None
        restored = boot(app, snapshot)
        print("RESTORED_VM", restored.object_id, flush=True)
        after = {ref: execute(restored, "docker", "image", "inspect", "--format", "{{.Id}}", ref) for ref in TEST_IMAGES}
        print("IDS_AFTER", json.dumps(after), flush=True)
        assert before == after, f"image IDs differ: {before} != {after}"
        print("OFFLINE_RUN", execute(restored, "docker", "run", "--pull=never", "--rm", TEST_IMAGES[0], "echo", "CACHE_OK"), flush=True)
        print("RESULT=PASS", "elapsed_seconds=", round(time.monotonic()-t0,2), flush=True)
    except Exception as err:
        print("RESULT=FAIL", repr(err), flush=True)
        traceback.print_exc()
        raise
    finally:
        for sandbox in (sb, restored):
            if sandbox:
                try:
                    sandbox.terminate()
                    print("TERMINATED", sandbox.object_id, flush=True)
                except Exception as err:
                    print("CLEANUP_WARNING", repr(err), flush=True)


if __name__ == "__main__":
    main()
