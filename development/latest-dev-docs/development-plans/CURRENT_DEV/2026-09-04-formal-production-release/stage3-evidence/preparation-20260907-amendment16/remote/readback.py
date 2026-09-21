"""Anonymous read-only preparation snapshot; not candidate acceptance."""
import datetime, hashlib, json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent / sys.argv[1]
ROOT.mkdir(parents=True,exist_ok=True)
base='https://api.github.com/repos/123rrr4tttt/market-research-workflow'
sha='909eb608e538b6427bcbacca974f1efb05fef611'
rows=[]
for name,endpoint in [('old-v6-commit','/commits/'+sha),('old-v6-runs','/actions/runs?head_sha='+sha),('main','/branches/main'),('rulesets','/rulesets?includes_parents=true'),('effective-rules','/rules/branches/main')]:
    cmd=['curl','-sS','--max-time','20','-i',base+endpoint]
    r=subprocess.run(cmd,capture_output=True)
    refs=[]
    for ext,data in [('response',r.stdout),('stderr',r.stderr)]:
        p=ROOT/(name+'.'+ext)
        with p.open('xb') as f:f.write(data)
        refs.append({'path':str(p),'sha256':hashlib.sha256(data).hexdigest()})
    rows.append({'id':name,'command':cmd,'cwd':str(Path.cwd()),'exit_code':r.returncode,'refs':refs})
payload={'schema_version':'mrw.stage3.preparation.remote.v1','authoritative':False,'qualification':'PREPARATION_ONLY_NO_NEW_CANDIDATE_SUPPLIED','observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attempts':rows,'external_mutations':[]}
with (ROOT/'observations.json').open('x') as f:json.dump(payload,f,indent=2)
