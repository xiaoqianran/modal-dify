"""Dify VM evaluation deployment; default official UI/Compose, protected HTTPS tunnel.

WARNING: state in this VM is ephemeral until an independently verified backup/
restore strategy is implemented. Do not put real production data here.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import string
import subprocess
import sys

import modal

APP = "modal-dify-vm"
NAME = "dify-119-evaluation"
IMAGE_NAME = "modal-dify-docker-cache-1-19-0"
ROOT = Path(__file__).resolve().parents[1]
SECRET_FILE = ROOT / "runtime" / "deploy-secrets.json"

def credentials():
    if SECRET_FILE.exists():
        return json.loads(SECRET_FILE.read_text())
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    chars = string.ascii_letters + string.digits
    data = {
        "edge_password": "".join(secrets.choice(chars) for _ in range(30)),
        "DB_PASSWORD": secrets.token_urlsafe(32),
        "REDIS_PASSWORD": secrets.token_urlsafe(32),
        "WEAVIATE_API_KEY": secrets.token_urlsafe(32),
        "CODE_EXECUTION_API_KEY": secrets.token_urlsafe(32),
        "PLUGIN_DAEMON_KEY": secrets.token_urlsafe(40),
        "PLUGIN_DIFY_INNER_API_KEY": secrets.token_urlsafe(40),
        "DIFY_AGENT_LOCAL_SANDBOX_AUTH_TOKEN": secrets.token_hex(32),
        "DIFY_AGENT_API_TOKEN": secrets.token_urlsafe(32),
        "SECRET_KEY": secrets.token_urlsafe(48)
    }
    fd=os.open(str(SECRET_FILE),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w") as f:json.dump(data,f)
    return data

def remote(sb,cmd,timeout=300,env=None):
    p=sb.exec("bash","-lc",cmd,timeout=timeout,env=env)
    output=p.stdout.read()
    error=p.stderr.read()
    p.wait()
    if p.returncode:
        raise RuntimeError(f"remote returned {p.returncode}: {(output+error)[-2500:]}")
    return output.strip()

def sandbox():
    return modal.Sandbox.from_name(APP,NAME)

# Operates on the VM's writable filesystem only, never modifies published cache.
SETUP = r'''
import base64,json,os,pathlib,secrets,subprocess
d=json.loads(base64.b64decode(os.environ["DIFY_SETUP"]).decode())
root=pathlib.Path("/opt/dify/docker")
env=root/".env"
if env.exists():
    raise RuntimeError("Refusing to overwrite existing Dify environment")
values={k:v for k,v in d.items() if k!="edge_password"}
values["COMPOSE_PROFILES"]="weaviate,postgresql,collaboration"
values["EXPOSE_NGINX_PORT"]="80"
values["EXPOSE_NGINX_SSL_PORT"]="443"
values["EXPOSE_PLUGIN_DEBUGGING_PORT"]="5003"
env.write_text("\n".join(f"{k}={v}" for k,v in values.items())+"\n")
env.chmod(0o600)
template=root/"nginx/conf.d/default.conf.template"
text=template.read_text()
assert "server {\n" in text
text=text.replace("server {\n", "server {\n    auth_basic \"Dify evaluation\";\n    auth_basic_user_file /etc/nginx/conf.d/.htpasswd;\n", 1)
template.write_text(text)
digest=subprocess.run(["openssl","passwd","-6","-stdin"],input=d["edge_password"],capture_output=True,text=True,check=True).stdout.strip()
(root/"nginx/conf.d/.htpasswd").write_text("dify:"+digest+"\n")
(root/"nginx/conf.d/.htpasswd").chmod(0o640)
print("CONFIG_PREPARED protected_nginx=on")
'''

# Debian 12 may not ship a sufficiently recent Compose plugin; install v2.40.3.
BOOT = r'''
set -euo pipefail
if ! docker compose version 2>/dev/null | grep -Eq 'v2\.(3[5-9]|[4-9][0-9])'; then
  mkdir -p /usr/local/lib/docker/cli-plugins
  python3 - <<'PYS'
import urllib.request
u="https://github.com/docker/compose/releases/download/v2.40.3/docker-compose-linux-x86_64"
urllib.request.urlretrieve(u,"/usr/local/lib/docker/cli-plugins/docker-compose")
PYS
  chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi
docker compose version
dockerd -H unix:///var/run/docker.sock >/tmp/dify-dockerd.log 2>&1 &
for n in $(seq 1 90); do
  if docker info >/dev/null 2>&1; then echo DOCKER_READY; exit 0; fi
  sleep 2
done
tail -60 /tmp/dify-dockerd.log
exit 1
'''

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("action",choices=["start","status","stop","credentials"])
    args=pa.parse_args()
    if args.action=="credentials":
        d=credentials()
        print("EDGE_USER=dify\nEDGE_PASSWORD="+d["edge_password"])
        return
    if args.action=="status":
        sb=sandbox()
        print("VM",sb.object_id,"poll",sb.poll())
        if sb.poll() is None:
            print("TUNNEL",sb.tunnels().get(80))
            try:print(remote(sb,"cd /opt/dify/docker && docker compose ps --all",timeout=60))
            except Exception as e:print("STATUS_ERROR",str(e))
        return
    if args.action=="stop":
        sb=sandbox()
        print("STOPPING",sb.object_id)
        sb.terminate()
        return
    app=modal.App.lookup(APP,create_if_missing=True)
    try:
        sb=sandbox()
        if sb.poll() is None:
            print("REUSE_VM",sb.object_id,flush=True)
            print("TUNNEL",sb.tunnels().get(80),flush=True)
            return
    except modal.exception.NotFoundError:
        pass
    d=credentials()
    sb=modal.Sandbox.create("sleep","86300",app=app,name=NAME,
         image=modal.Image.from_name(IMAGE_NAME),
         runtime="vm",cpu=4,memory=16384,timeout=86400,
         encrypted_ports=[80])
    print("CREATED_VM",sb.object_id,flush=True)
    try:
        print("BOOT",remote(sb,BOOT,timeout=360),flush=True)
        data=base64.b64encode(json.dumps(d).encode()).decode()
        print("SETUP",remote(sb,"python3 -c "+__import__("shlex").quote(SETUP),timeout=90,
                env={"DIFY_SETUP":data}),flush=True)
        print("CONFIG",remote(sb,
            "cd /opt/dify/docker && docker compose config --quiet && docker compose config --images | sort -u | wc -l",
            timeout=120),flush=True)
        print("COMPOSE_START",remote(sb,
            "cd /opt/dify/docker && docker compose --parallel 4 up -d --pull never --no-build",
            timeout=1200),flush=True)
        print("SERVICES",remote(sb,"cd /opt/dify/docker && docker compose ps --all",timeout=90),flush=True)
        print("WEB_HTTP",remote(sb,
            "python3 -c 'import urllib.request,urllib.error;u=\"http://127.0.0.1/install\";print(urllib.request.urlopen(u, timeout=20).status)'",
            timeout=30),flush=True)
        print("TUNNEL",sb.tunnels().get(80),flush=True)
        print("EDGE_USER=dify\nEDGE_PASSWORD="+d["edge_password"],flush=True)
        print("WARNING=EVALUATION_ONLY, DATA_NOT_PERSISTENT_ACROSS_VM_DESTRUCTION",flush=True)
    except Exception:
        print("START_FAILED_VM_RETAINS_FOR_DEBUG",sb.object_id,flush=True)
        raise

if __name__=="__main__":main()
