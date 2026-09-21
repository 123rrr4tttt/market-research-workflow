"""Additive recovery of explicit CLI spelling and missing test interpreter aliases."""
from pathlib import Path
exec(compile(Path(__file__).with_name('run_preflight.py').read_text().split("initial = identity(")[0], 'run_preflight_helpers', 'exec'))
prior=json.loads((OUT/'result.json').read_text())
clone=Path(prior['retained_resources']['path'])/'candidate'
aliases=[]
for relative in ['.venv','main/backend/.venv311']:
    destination=clone/relative
    source=ROOT/relative
    destination.symlink_to(source, target_is_directory=True)
    aliases.append(dict(path=str(destination),target=str(source)))
save('retry-environment.json',dict(reason=['Initial R1 invocation used --strategy instead of required --candidate-strategy','Four R1 CLI subtests require repo-relative existing interpreter environments'],aliases=aliases,scope='Toolchain-only aliases within disposable clone; no candidate code modifications',prior_record_sha256=sha(OUT/'result.json')))
run('r1-corrected',[PYTHON,'scripts/formal_release/check_candidate_identity.py','--repo-root',str(clone),'--expected-commit',COMMIT,'--expected-tree',TREE,'--candidate-strategy','REMEDIATION_INCLUSIVE_RELEASE'],clone)
run('focused-toolchain-corrected',[PYTHON,'-m','pytest','-o','addopts=','-p','no:cacheprovider','tests/formal_release/test_check_release_evidence.py','tests/formal_release/test_s1_workflow_contract.py','tests/formal_release/test_check_candidate_identity.py','tests/formal_release/test_check_static_production_contract.py','--junitxml='+str(OUT/'focused-corrected.junit.xml'),'-ra'],clone,dict(PYTHONPATH=str(clone)))
canonical=identity('canonical-final',CANDIDATE)
clone_final=identity('clone-final',clone)
save('retry-result.json',dict(schema_version='mrw.stage3.v6.recovery-preflight-retry.v1',authoritative=False,candidate_commit=COMMIT,candidate_tree=TREE,records=records,status='PASS_PREFLIGHT_ONLY' if all(r['exit_code']==0 for r in records) and canonical['valid'] else 'FAILED',canonical_final=canonical,clone_final=clone_final,prior_record=dict(path=str(OUT/'result.json'),sha256=sha(OUT/'result.json')),r3=dict(path=str(OUT/'r3.log'),sha256=sha(OUT/'r3.log')),junit=dict(path=str(OUT/'focused-corrected.junit.xml'),sha256=sha(OUT/'focused-corrected.junit.xml')),qualification='LOCAL_SYNTHETIC_CONFORMANCE_AND_STATIC_WORKFLOW_ONLY',external_effects=[]))
refs=[]
for path in sorted(OUT.iterdir()):
    if path.is_file():
        if path.suffix=='.json':
            assert isinstance(json.loads(path.read_text()),dict)
        refs.append(dict(path=str(path),sha256=sha(path)))
for record in prior['records']+records:
    assert sha(record['log'])==record['sha256']
save('verified-index.json',dict(schema_version='mrw.stage3.v6.recovery-index.v1',authoritative=False,files=refs,logs_rehashed=True,json_roots_valid=True))
print(json.dumps(dict(status=json.loads((OUT/'retry-result.json').read_text())['status'],index_sha256=sha(OUT/'verified-index.json'))))
