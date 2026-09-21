import pathlib,subprocess,json,hashlib,os
b=pathlib.Path(__file__).parent;r=b/'candidate'
o=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-ops')
records=[]
for name,cmd in [('gitleaks-version',[str(b/'bin/gitleaks'),'version']),('gitleaks-scan',[str(b/'bin/gitleaks'),'git','--redact=100','--no-banner','--log-opts=HEAD',str(r)])]:
 try:
  p=subprocess.run(cmd,cwd=r,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180);data=p.stdout;code=p.returncode
 except subprocess.TimeoutExpired as e:data=(e.stdout or b'')+b'\nTIMEOUT\n';code=124
 path=o/(name+'.raw.log');path.open('xb').write(data)
 records.append(dict(id=name,command=cmd,cwd=str(r),exit_code=code,log=str(path),sha256=hashlib.sha256(data).hexdigest()))
 print(name,code,flush=True)
for f in ['run.py','followup.py','scan.py']:
 (o/f).open('xb').write((b/f).read_bytes())
with (o/'security-followup.v1.json').open('x') as f:json.dump(dict(authoritative=False,candidate_commit='909eb608e538b6427bcbacca974f1efb05fef611',candidate_tree='a60b795e509aa5dc479904a321fba32ed0ab9ab2',records=records,supersedes={'gitleaks_unavailable':'scanner acquired as pinned v8.24.2 Go source into disposable path'},pip_audit_status='BLOCKED_TOOL_BOOTSTRAP_FAILED; no dependency vulnerability verdict',cleanup={'created_containers':[],'created_databases':[],'created_images':[],'retained_path':str(b),'reason':'reviewable standalone clone and scanner cache; no running services'},external_effects=[]),f,indent=2)
