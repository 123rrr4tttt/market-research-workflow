import subprocess, pathlib, json, hashlib, os, time
base=pathlib.Path(__file__).parent
root=base/'candidate'
out=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-ops')
out.mkdir(parents=True,exist_ok=True)
records=[]
env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PIP_CACHE_DIR=str(base/'pip-cache'),XDG_CACHE_HOME=str(base/'cache'))
def run(name,cmd,cwd,timeout=90):
    start=time.time()
    try:
        p=subprocess.run(cmd,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
        data=p.stdout; code=p.returncode
    except subprocess.TimeoutExpired as e: data=(e.stdout or b'')+b'\nTIMEOUT\n';code=124
    except FileNotFoundError as e: data=str(e).encode();code=127
    path=out/(name+'.raw.log')
    with path.open('xb') as f:f.write(data)
    records.append(dict(id=name,command=cmd,cwd=str(cwd),exit_code=code,seconds=time.time()-start,log=str(path),sha256=hashlib.sha256(data).hexdigest()))
    print(name,code,flush=True)
run('clone',['git','clone','--no-hardlinks','--no-local','/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6',str(root)],base)
run('identity',['git','show','-s','--format=%H %T %P','HEAD'],root)
run('tool-python',['python3','--version'],root)
run('tool-docker',['docker','version'],root)
run('tool-compose',['docker','compose','version'],root)
run('tool-bandit',['bandit','--version'],root)
run('tool-pip-audit',['pip-audit','--version'],root)
run('tool-gitleaks',['gitleaks','version'],root)
run('migration-graph',['python3','scripts/check_backend_migration_graph.py','--expect-single-head','--json'],root)
run('production-compose',['/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python','scripts/formal_release/check_production_compose_config.py'],root)
run('bandit',['bandit','-q','-r','main/backend/app','-x','main/backend/tests','--severity-level','high','--confidence-level','high'],root)
run('pip-audit',['pip-audit','-r','main/backend/requirements.txt','--strict','--progress-spinner','off'],root,180)
run('clean-final',['git','status','--porcelain'],root)
report=dict(schema_version='mrw.stage3.recovery_ops.v1',authoritative=False,candidate_commit='909eb608e538b6427bcbacca974f1efb05fef611',candidate_tree='a60b795e509aa5dc479904a321fba32ed0ab9ab2',records=records,environment_differences=['Local macOS arm64 toolchain; not remote workflow','Shared existing Python interpreter used read-only; cache writes isolated in disposable directory','No DNS/socket guard injected'],unexecuted={'postgres_opt_in':'Docker daemon unavailable; no existing user DB used','docker_smoke':'Docker daemon unavailable; floating product FROM requires successor','image_scan':'No qualified candidate artifact','gitleaks':'binary unavailable'},external_effects=[],cleanup={'containers':[],'databases':[],'images':[],'retained':[str(base)],'owner':'recovery_ops','reason':'isolated clone and dependency cache retained for review; no service started'})
with (out/'report.v1.json').open('x') as f:json.dump(report,f,indent=2)
