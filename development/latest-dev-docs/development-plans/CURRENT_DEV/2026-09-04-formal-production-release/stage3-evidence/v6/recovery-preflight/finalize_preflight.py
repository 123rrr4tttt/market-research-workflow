"""Remove only the two recorded toolchain symlinks, then verify clean exact R1."""
from pathlib import Path
exec(compile(Path(__file__).with_name('run_preflight.py').read_text().split("initial = identity(")[0], 'run_preflight_helpers', 'exec'))
prior=json.loads((OUT/'result.json').read_text())
clone=Path(prior['retained_resources']['path'])/'candidate'
removed=[]
for alias in json.loads((OUT/'retry-environment.json').read_text())['aliases']:
    path=Path(alias['path'])
    assert path.is_symlink() and str(path.readlink())==alias['target'] and path.is_relative_to(clone)
    path.unlink()
    removed.append(alias)
run('r1-final-clean',[PYTHON,'scripts/formal_release/check_candidate_identity.py','--repo-root',str(clone),'--expected-commit',COMMIT,'--expected-tree',TREE,'--candidate-strategy','REMEDIATION_INCLUSIVE_RELEASE'],clone)
canonical=identity('canonical-completed',CANDIDATE)
clone_final=identity('clone-completed',clone)
r3=json.loads((OUT/'r3.log').read_text())
assert r3['status']=='PASS'
assert json.loads((OUT/'focused-toolchain-corrected.command.json').read_text())['exit_code']==0
assert all(r['exit_code']==0 for r in records) and canonical['valid'] and clone_final['valid']
save('completion.json',dict(schema_version='mrw.stage3.v6.recovery-preflight-completion.v1',authoritative=False,status='PASS_PREFLIGHT_ONLY',candidate_commit=COMMIT,candidate_tree=TREE,records=records,canonical=canonical,clone=clone_final,removed_toolchain_aliases=removed,validation='Fresh R1 PASS after removing temporary interpreter aliases; R3 PASS; 58 focused R1 R2 R3 workflow tests PASS with declared interpreter aliases',limitations=['R2 is synthetic conformance only','Workflow checks are static local contract tests','Initial failed CLI and toolchain attempts preserved','No remote workflow or full Stage3 acceptance established'],external_effects=[]))
refs=[]
for path in sorted(OUT.iterdir()):
    if path.is_file():
        if path.suffix=='.json': assert isinstance(json.loads(path.read_text()),dict)
        refs.append(dict(path=str(path),sha256=sha(path)))
save('completion-index.json',dict(schema_version='mrw.stage3.v6.recovery-index.v1',files=refs,authoritative=False))
print(json.dumps(dict(completion_sha256=sha(OUT/'completion.json'),index_sha256=sha(OUT/'completion-index.json'))))
