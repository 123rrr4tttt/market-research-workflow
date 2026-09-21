import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parent
files=[]
for p in sorted(root.rglob('*')):
    if p.is_file():
        assert not p.is_symlink()
        if p.suffix=='.json':json.loads(p.read_text())
        files.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
assert len({x['path'] for x in files})==len(files)
payload={'schema_version':'mrw.stage3.preparation.index.v1','authoritative':False,'status':'PREPARATION_COMPLETE_WITH_BLOCKERS','candidate_acceptance':False,'contract16_sha256':'316339cdfa538f66272802e31dd236c0838f1fcd093169d79408b81e816ded6f','evidence':files,'external_mutations':[],'services_started':[]}
with (root/'index.v1.json').open('x') as f:json.dump(payload,f,indent=2)
print(len(files),hashlib.sha256((root/'index.v1.json').read_bytes()).hexdigest())
