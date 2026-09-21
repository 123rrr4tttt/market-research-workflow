import os, sys, subprocess, pathlib, json, hashlib, datetime, platform, re
root=pathlib.Path('/private/tmp/mrw-stage3-v6-backend-recovery-20260907')
out=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-backend')
out.mkdir(parents=True, exist_ok=False)
python='/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python'
guard=pathlib.Path('/private/tmp/mrw-stage3-v6-backend-recovery-guard'); guard.mkdir(exist_ok=False)
# Temporary instrumentation, not product code. Python audit does not cover native extensions.
(guard/'sitecustomize.py').write_text('import sys, socket\ndef audit(event,args):\n    if event in ("socket.connect", "socket.sendto", "socket.getaddrinfo"):\n        raise OSError("STAGE3_PYTHON_SOCKET_AUDIT_DENIED:"+event)\nsys.addaudithook(audit)\n')
env={'PATH':os.environ['PATH'],'HOME':str(root),'TMPDIR':'/private/tmp','PYTHONHASHSEED':'0','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(guard)+':'+str(root)+':'+str(root/'main/backend'),'TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
records=[]
for name,cwd,args in [('identity',root,['-c','import subprocess,sys,platform,json; print(sys.version); print(platform.platform()); print(sys.path); subprocess.run(["git","rev-parse","HEAD","HEAD^{tree}"]); subprocess.run(["git","status","--porcelain"])']),('root',root,['-m','pytest','tests','-q','-ra']),('unit',root/'main/backend',['-m','pytest','-m','unit and not external and not flaky','-q','-ra']),('integration',root/'main/backend',['-m','pytest','-m','integration and not external and not flaky','-q','-ra']),('core-business',root/'main/backend',['-m','pytest','tests/core_business','-m','(unit or integration or contract or e2e) and not external','-q','-ra']),('successor-runtime',root/'main/backend',['-m','pytest','tests/successor_runtime','-m','not external','-q','-ra'])]:
    if name!='identity': args+=['--junitxml='+str(out/(name+'.xml'))]
    cmd=[python]+args; start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (out/(name+'.log')).open('x') as f:
        try: code=subprocess.run(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
        except subprocess.TimeoutExpired: code=124
    rec={'id':name,'command':cmd,'cwd':str(cwd),'started_at':start,'exit_code':code,'log':name+'.log'}
    records.append(rec); print(json.dumps(rec),flush=True)
    (out/(name+'.record.json')).write_text(json.dumps(rec,indent=2)+'\n')
result={'candidate_commit':'909eb608e538b6427bcbacca974f1efb05fef611','candidate_tree':'a60b795e509aa5dc479904a321fba32ed0ab9ab2','authoritative':False,'env':env,'environment_difference':'macOS reused venv311 dependencies, no .env copy, sanitized environment, Python socket audit denial, offline transformers; not remote workflow and not comprehensive native/subprocess isolation','guard_source':(guard/'sitecustomize.py').read_text(),'records':records,'retained_clone':str(root)}
result['files']=[{'path':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file()]
(out/'index.v1.json').write_text(json.dumps(result,indent=2)+'\n')
