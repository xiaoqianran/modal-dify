"""Read-only checks for the running evaluation VM."""
import json
from pathlib import Path
import base64
import urllib.request
import urllib.error
import modal

sb=modal.Sandbox.from_name("modal-dify-vm","dify-119-evaluation")
print("VM",sb.object_id,"running",sb.poll() is None,flush=True)
if sb.poll() is not None: raise SystemExit(1)
tunnel=sb.tunnels()[80]
url=f"https://{tunnel.host}/install"
print("URL",url,flush=True)
p=json.loads((Path(__file__).resolve().parents[1]/"runtime"/"deploy-secrets.json").read_text())["edge_password"]
for use_auth in (False,True):
    headers={}
    if use_auth:
        headers["Authorization"]="Basic "+base64.b64encode(("dify:"+p).encode()).decode()
    request=urllib.request.Request(url,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=20) as resp:
            print("WEB", "with_auth" if use_auth else "anonymous",resp.status, resp.url,resp.read(300)[:100],flush=True)
    except urllib.error.HTTPError as e:
        print("WEB", "with_auth" if use_auth else "anonymous",e.code,e.read(120),flush=True)
    except Exception as e:
        print("WEB_ERROR",type(e).__name__,str(e)[:180],flush=True)
proc=sb.exec("bash","-lc",
        "docker ps --format '{{.Names}} {{.Status}}' | sort; "
        "docker stats --no-stream --format '{{.Name}} {{.MemUsage}} {{.CPUPerc}}' | head -20",
        timeout=45)
print("SERVICE_STATUS",proc.stdout.read(),flush=True)
print("ERRORS",proc.stderr.read()[-500:],flush=True)
proc.wait()
