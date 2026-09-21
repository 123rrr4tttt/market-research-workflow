import subprocess,pathlib,json,hashlib,os
b=pathlib.Path(__file__).parent;r=b/'candidate'
o=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-ops')
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='.',GOBIN=str(b/'bin'),GOPATH=str(b/'go'),GOCACHE=str(b/'go-cache'))
records=[]
for name,cmd,cwd in [('docker-daemon-unsandboxed',['docker','version'],r),('alembic-heads',['/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python','-m','alembic','heads'],r/'main/backend'),('gitleaks-install',['go','install','github.com/zricethezav/gitleaks/v8@v8.24.2'],b)]:
 try:
  p=subprocess.run(cmd,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150);data=p.stdout;code=p.returncode
 except subprocess.TimeoutExpired as e:data=(e.stdout or b'')+b'\nTIMEOUT\n';code=124
 path=o/(name+'.raw.log');path.open('xb').write(data)
 records.append(dict(id=name,command=cmd,cwd=str(cwd),exit_code=code,log=str(path),sha256=hashlib.sha256(data).hexdigest()))
 print(name,code,flush=True)
with (o/'followup.v1.json').open('x') as f:json.dump({'records':records,'authoritative':False},f,indent=2)
