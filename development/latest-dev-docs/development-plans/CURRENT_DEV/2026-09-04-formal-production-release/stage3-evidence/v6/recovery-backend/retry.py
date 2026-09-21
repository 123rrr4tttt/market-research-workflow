import os,subprocess,pathlib,json,datetime
out=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-backend')
base=json.loads((out/'index.v1.json').read_text()); env=base['env']; env['PYTHONPATH']+=':/private/tmp/mrw-stage3-v6-backend-recovery-20260907/src'
records=[]
for r in base['records']:
 if r['id'] in ('root','identity'):continue
 name=r['id']+'-src-path'; cmd=[v.replace(r['id']+'.xml',name+'.xml') for v in r['command']]
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (out/(name+'.log')).open('x') as f:
  try: code=subprocess.run(cmd,cwd=r['cwd'],env=env,stdout=f,stderr=subprocess.STDOUT,timeout=900).returncode
  except subprocess.TimeoutExpired:code=124
 record={'id':name,'command':cmd,'cwd':r['cwd'],'started_at':start,'exit_code':code,'environment':env,'reason':'Initial backend pytest config did not inherit root pyproject pythonpath=src; add candidate-local src'}
 with (out/(name+'.record.json')).open('x') as f:json.dump(record,f,indent=2)
 records.append(record);print(json.dumps(record),flush=True)
with (out/'retry-index.v1.json').open('x') as f:json.dump(records,f,indent=2)
