"""Create-only Stage 3 v6 recovery evidence; never mutates the canonical candidate."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

OUT = Path(__file__).resolve().parent
ROOT = Path('/Users/wangyiliang/market-research-workflow')
CANDIDATE = Path('/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6')
EVIDENCE = Path('/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6')
DOC = OUT.parents[2]
COMMIT = '909eb608e538b6427bcbacca974f1efb05fef611'
TREE = 'a60b795e509aa5dc479904a321fba32ed0ab9ab2'
PYTHON = str(ROOT / '.venv/bin/python')
records = []
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')

def run(name, argv, cwd, extra=None):
    started = datetime.now(timezone.utc).isoformat()
    effective = dict(env, **(extra or {}))
    with (OUT / (name + '.log')).open('xb') as stream:
        result = subprocess.run(argv, cwd=cwd, env=effective, stdout=stream, stderr=subprocess.STDOUT)
    record = dict(id=name, command=argv, cwd=str(cwd), exit_code=result.returncode,
                  started_at=started, ended_at=datetime.now(timezone.utc).isoformat(),
                  log=str(OUT / (name + '.log')), sha256=sha(OUT / (name + '.log')),
                  environment_overrides=dict(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', **(extra or {})))
    records.append(record)
    save(name + '.command.json', record)
    return (OUT / (name + '.log')).read_text()

def identity(prefix, root):
    values = {}
    for label, args in [('commit',['rev-parse','HEAD']),('tree',['rev-parse','HEAD^{tree}']),('parent',['rev-parse','HEAD^']),('status',['status','--porcelain=v1','--untracked-files=all']),('shallow',['rev-parse','--is-shallow-repository']),('fsck',['fsck','--full'])]:
        values[label] = run(prefix+'-'+label, ['git', *args], root).strip()
    values['alternates_present'] = (root/'.git/objects/info/alternates').exists()
    values['valid'] = values['commit']==COMMIT and values['tree']==TREE and values['parent']=='88ffcc3dab2e6cbdc1f389e16c4226df5a2e51c6' and not values['status'] and values['shallow']=='false' and not values['alternates_present'] and records[-1]['exit_code']==0
    return values

initial = identity('canonical-before', CANDIDATE)
contracts = [DOC/'15_production-deployment-stage3-v6-contract.v1.md', DOC/'09_production-deployment-stage3-successor-contract.v1.md', DOC/'04_production-deployment-stage-plan.v1.md']
inputs = [dict(path=str(p), sha256=sha(p)) for p in contracts]
contract = contracts[0].read_text()
checks = []
for name, digest in re.findall(r'^([\w.-]+\.json)=([a-f0-9]{64})$', contract, re.M):
    path=EVIDENCE/name
    checks.append(dict(path=str(path), expected=digest, observed=sha(path), matches=sha(path)==digest))
for name, digest in [('09_production-deployment-stage3-successor-contract.v1.md','61d5b99ce8966b1bdb4eadf754ae03b7651026098b38da09dd46a69e773237be'),('04_production-deployment-stage-plan.v1.md','d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa')]:
    checks.append(dict(path=str(DOC/name), expected=digest, observed=sha(DOC/name), matches=sha(DOC/name)==digest))
def refs(value):
    if isinstance(value, dict):
        for key, val in value.items():
            digest_key = 'sha256' if key=='path' else key.removesuffix('_path')+'_sha256'
            if (key=='path' or key.endswith('_path')) and isinstance(val,str) and digest_key in value:
                p=Path(val); observed=sha(p) if p.is_file() else None
                checks.append(dict(path=val, expected=value[digest_key], observed=observed, matches=observed==value[digest_key]))
            refs(val)
    elif isinstance(value,list):
        for item in value: refs(item)
refs(json.loads((EVIDENCE/'closure.final.v6.json').read_text()))
save('preconditions.json', dict(candidate=initial, inputs=inputs, hash_checks=checks, authoritative=False))
if not initial['valid'] or not all(c['matches'] for c in checks):
    raise SystemExit('INPUT_DRIFT: see preconditions.json')
tmp=Path(tempfile.mkdtemp(prefix='mrw-stage3-v6-preflight-',dir='/private/tmp'))
clone=tmp/'candidate'
run('clone', ['git','clone','--no-hardlinks','--no-local',str(CANDIDATE),str(clone)], tmp)
clone_identity=identity('clone-before', clone)
if not clone_identity['valid']: raise SystemExit('CLONE_IDENTITY_FAILURE')
run('tool-python', [PYTHON,'--version'],clone)
run('tool-pytest', [PYTHON,'-m','pytest','--version'],clone)
run('tool-git', ['git','--version'],clone)
run('dependency-versions', [PYTHON,'-m','pip','list','--format=json','--disable-pip-version-check'],clone)
run('r1', [PYTHON,'scripts/formal_release/check_candidate_identity.py','--repo-root',str(clone),'--expected-commit',COMMIT,'--expected-tree',TREE,'--strategy','REMEDIATION_INCLUSIVE_RELEASE'],clone)
run('r3', [PYTHON,'scripts/formal_release/check_static_production_contract.py','--repo-root',str(clone)],clone)
run('r2-conformance-and-workflow', [PYTHON,'-m','pytest','-o','addopts=','-p','no:cacheprovider','tests/formal_release/test_check_release_evidence.py','tests/formal_release/test_s1_workflow_contract.py','tests/formal_release/test_check_candidate_identity.py','tests/formal_release/test_check_static_production_contract.py','--junitxml='+str(OUT/'focused.junit.xml'),'-ra'],clone,dict(PYTHONPATH=str(clone)))
final=identity('canonical-after', CANDIDATE)
clone_final=identity('clone-after',clone)
save('result.json',dict(schema_version='mrw.stage3.v6.recovery-preflight.v1',authoritative=False,candidate_commit=COMMIT,candidate_tree=TREE,records=records,input_refs_and_sha256=inputs,hash_checks=checks,canonical_before=initial,canonical_after=final,clone_before=clone_identity,clone_after=clone_final,platform=platform.platform(),python_executable=PYTHON,status='PASS_PREFLIGHT_ONLY' if all(r['exit_code']==0 for r in records) and final['valid'] else 'FAILED',qualification='R2_SYNTHETIC_CONFORMANCE_ONLY_NO_REMOTE_WORKFLOW_EXECUTION',environment_differences=['Existing project venv reused as dependency toolchain','Local macOS execution','PYTHONPATH exact clone','No DNS or socket guard injected'],external_effects=[],retained_resources=dict(path=str(tmp),owner='recover_preflight',reason='Independent clone retained for evidence replay'),junit=dict(path=str(OUT/'focused.junit.xml'),sha256=sha(OUT/'focused.junit.xml'))))
print(str(OUT/'result.json'))
