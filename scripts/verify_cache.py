"""Verify all pinned Dify image references are preserved in Named Image; no pulls."""
import json
import time
import modal
from build_cache import APP_NAME, IMAGE_NAME, manifest, run

def main():
    app=modal.App.lookup(APP_NAME,create_if_missing=True)
    sb=None
    try:
        image=modal.Image.from_name(IMAGE_NAME)
        sb=modal.Sandbox.create("sleep","500",app=app,image=image,
                runtime="vm",cpu=2,memory=4096,timeout=600)
        print("VERIFY_VM",sb.object_id,flush=True)
        print("DOCKER_READY",run(sb,"bash","-lc",
              "dockerd >/tmp/dockerd.log 2>&1 & for i in $(seq 1 70); do "
              "docker info >/dev/null 2>&1 && exit 0; sleep 2; done; tail -50 /tmp/dockerd.log; exit 1",timeout=180),flush=True)
        refs=manifest()
        script="""import json,subprocess,os
refs=json.loads(os.environ['DIFY_REFS'])
for ref in refs:
 p=subprocess.run(['docker','image','inspect','--format','{{.Id}}',ref],capture_output=True,text=True)
 print(json.dumps({'ref':ref,'ok':p.returncode==0,'id':p.stdout.strip(),'err':p.stderr[-300:]}),flush=True)
 if p.returncode:raise SystemExit(1)
print('RESULT=PASS all',len(refs),'images restored without pull',flush=True)
"""
        print(run(sb,"python3","-c",script,timeout=90,env={"DIFY_REFS":json.dumps(refs)}),flush=True)
    finally:
        if sb:
            sb.terminate()
            print("TERMINATED",sb.object_id,flush=True)
if __name__=="__main__":main()
