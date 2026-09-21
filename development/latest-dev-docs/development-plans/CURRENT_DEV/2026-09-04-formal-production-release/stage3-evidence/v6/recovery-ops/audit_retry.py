import pathlib,subprocess,json,hashlib,os
b=pathlib.Path(__file__).parent;r=b/'candidate';o=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-ops')
env=dict(os.environ,UV_CACHE_DIR=str(b/'uv-cache'),PIP_CACHE_DIR=str(b/'pip-cache'),PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(b))
records=[]
for name,cmd in [('scanner-venv',['uv','venv','--python','/opt/homebrew/bin/python3.11',str(b/'audit-venv')]),('scanner-install',['uv','pip','install','--python',str(b/'audit-venv/bin/python'),'pip-audit==2.9.0']),('pip-audit-py311',[str(b/'audit-venv/bin/pip-audit'),'-r','main/backend/requirements.txt','--strict','--progress-spinner','off'])]:
 try:
  p=subprocess.run(cmd,cwd=r,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150);data=p.stdout;code=p.returncode
 except subprocess.TimeoutExpired as e:data=(e.stdout or b'')+b'\nTIMEOUT\n';code=124
 except FileNotFoundError as e:data=str(e).encode();code=127
 path=o/(name+'.raw.log');path.open('xb').write(data)
 records.append(dict(id=name,command=cmd,cwd=str(r),exit_code=code,log=str(path),sha256=hashlib.sha256(data).hexdigest()))
 print(name,code,flush=True)
 if code:break
(o/'audit_retry.py').open('xb').write(pathlib.Path(__file__).read_bytes())
with (o/'audit-retry.v1.json').open('x') as f:json.dump(dict(authoritative=False,candidate_commit='909eb608e538b6427bcbacca974f1efb05fef611',candidate_tree='a60b795e509aa5dc479904a321fba32ed0ab9ab2',records=records,environment_differences=['Temporary Python3.11 scanner venv; caches and TMPDIR isolated','Network dependency retrieval enabled; no socket guard']),f,indent=2)
