"""Assemble create-only Stage 3 negative evidence after all workers finish."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
CANDIDATE = Path('/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6')
COMMIT = '909eb608e538b6427bcbacca974f1efb05fef611'
TREE = 'a60b795e509aa5dc479904a321fba32ed0ab9ab2'
CEILING = ['NO_DEPLOY', 'NO_LIVE', 'NO_PRODUCTION_WRITE', 'NO_EXTERNAL_DELIVERY', 'NO_CANARY', 'NO_CUTOVER', 'NO_AUTHORITY_TRANSFER', 'NO_LEGACY_RETIREMENT', 'NO_PUSH', 'NO_REMOTE_MUTATION', 'NO_REGISTRY_WRITE', 'NO_SIGNING_WRITE']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ref(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Invalid evidence path: {path}')
    return {'path': str(path), 'sha256': digest(path)}

def write(name, payload):
    with (ROOT / name).open('x') as out:
        json.dump(payload, out, indent=2, ensure_ascii=False)
        out.write('\n')
    return ref(ROOT / name)

def envelope(record_id, status):
    return {'schema_version': 'mrw.formal_release.stage3.recovery.v1', 'record_id': record_id,
            'stage_id': 'STAGE_3', 'candidate_generation': 'V6_ADDITIVE_SUCCESSOR',
            'candidate_commit': COMMIT, 'candidate_tree': TREE, 'status': status,
            'authoritative': False, 'derived_as': 'preflight', 'authority_ceiling': CEILING,
            'external_effects': [], 'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}

def main():
    decisions = json.loads((ROOT / 'integration-input.json').read_text())
    # The input is a retained preparation draft. Completion receipts supersede it.
    for completion in ['recovery-backend/completion.v1.json', 'recovery-frontend/summary-01.json', 'recovery-frontend/audit-summary-01.json', 'recovery-ops/audit-retry.v1.json', 'recovery-preflight/completion.json']:
        assert (ROOT / completion).is_file(), completion
    decisions['workers_finished'] = True
    decisions['completion_qualification'] = 'All recovery workers reported finished; backend process-termination receipt retained.'
    for p in sorted(Path('/private/tmp').glob('mrw-stage3-v6-*')):
        if str(p) not in {r['path'] for r in decisions['retained_resources']}:
            decisions['retained_resources'].append({'path': str(p), 'owner': 'Stage3 recovery workers', 'reason': 'Task-owned replay runner or diagnostic output', 'recovery': 'Retain for review; remove exact path after review'})
    write('integration-decisions.final.v1.json', decisions)
    leaves = [ref(p) for p in sorted(ROOT.glob('recovery-*/**/*')) if p.is_file() and not p.is_symlink()]
    for row in leaves:
        p = Path(row['path'])
        if p.suffix == '.json':
            data = json.loads(p.read_text())
            # Raw tool payloads may be lists. Candidate-bound receipts must match.
            if isinstance(data, dict):
                for key, value in [('candidate_commit', COMMIT), ('candidate_tree', TREE)]:
                    if key in data:
                        assert data[key] == value, (p, key)
    command = ['git', '-C', str(CANDIDATE), 'status', '--porcelain=v1', '--untracked-files=all']
    status = subprocess.run(command, capture_output=True, text=True)
    assert status.returncode == 0 and status.stdout == '', status.stdout
    assert subprocess.check_output(['git', '-C', str(CANDIDATE), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    assert subprocess.check_output(['git', '-C', str(CANDIDATE), 'rev-parse', 'HEAD^{tree}'], text=True).strip() == TREE
    inputs = [ref(ROOT.parent.parent / name) for name in ['15_production-deployment-stage3-v6-contract.v1.md', '09_production-deployment-stage3-successor-contract.v1.md', '04_production-deployment-stage-plan.v1.md']]
    eroot = Path('/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6')
    inputs += [ref(eroot / name) for name in ['candidate-manifest.v6.json', 'closure.final.v6.json', 'stage2-record.final.v6.json', 'r1.final.v6.json', 'r2.pass.v6.json', 'r3.pass.v6.json']]
    gate_record = envelope('v6-test-gates-final', 'FAIL')
    gate_record.update({'gates': decisions['gates'], 'attribution': decisions['attribution'], 'source_receipts': leaves,
                        'qualification': 'LOCAL_ENVIRONMENTS_WITH_DECLARED_DIFFERENCES; NOT_REMOTE_WORKFLOW'})
    gates_ref = write('test-gates.final.v1.json', gate_record)
    cleanup = envelope('v6-cleanup-retention', 'PASS')
    cleanup.update({'canonical_clean_check': {'command': command, 'exit_code': status.returncode, 'stdout': status.stdout},
                    'retained_resources': decisions['retained_resources'],
                    'qualification': 'OWNED_REPLAY_RESOURCES_RETAINED_WITH_PATH_OWNER_REASON; NOT_DELETION_CLAIM',
                    'missing_previous_attempt_resources': 'Pre-interruption /private/tmp evidence absent on resume; excluded from active PASS evidence.'})
    cleanup_ref = write('cleanup-and-retention.v1.json', cleanup)
    manifest = {'schema_version': 'mrw.formal-production-release-evidence.v1', 'authoritative': False,
                'derived_as': 'preflight', 'candidate_commit': COMMIT, 'candidate_tree': TREE, 'records': []}
    families = ['semantic_closure', 'candidate_identity', 'artifact_build', 'business_validation', 'security_supply_chain', 'runtime_staging', 'observability_canary', 'backup_recovery', 'independent_review', 'promotion_authority']
    for family in families:
        state = 'UNEXECUTED'
        evidence = gates_ref
        if family == 'candidate_identity':
            state, evidence = 'PASS', ref(ROOT / 'recovery-preflight/completion.json')
        elif family in ['artifact_build', 'business_validation', 'security_supply_chain']:
            state = 'FAIL'
        elif family == 'promotion_authority':
            state = 'BLOCKED'
        manifest['records'].append({'gate_id': f'v6-{family}', 'family': family, 'status': state, 'required': True,
                                    'evidence_refs': [evidence['path']], 'evidence_sha256': [evidence['sha256']],
                                    'observed_at': gate_record['observed_at'], 'owner': 'Stage3 executor',
                                    'notes': ['Negative Stage3 manifest; future-stage evidence is not asserted.']})
    manifest_ref = write('release-evidence-manifest.actual.v1.json', manifest)
    clone = Path(decisions['validator_clone'])
    checker = clone / 'scripts/formal_release/check_release_evidence.py'
    assert digest(checker) == digest(CANDIDATE / 'scripts/formal_release/check_release_evidence.py')
    cmd = [decisions['python'], str(checker), '--manifest', manifest_ref['path']]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONPATH=str(clone / 'src'))
    run = subprocess.run(cmd, cwd=clone, env=env, capture_output=True, text=True)
    result = json.loads(run.stdout)
    r2_ref = write('release-evidence-validation.actual.v1.json', result)
    expected = [(r['family'] + '.gate', r['status']) for r in manifest['records']]
    observed = [(r['check_id'], r['status']) for r in result['report']['findings']]
    assert expected == observed, (expected, observed)
    for r in manifest['records']:
        for path, sha in zip(r['evidence_refs'], r['evidence_sha256']):
            assert digest(Path(path)) == sha
    binding = envelope('v6-actual-manifest-binding', 'PASS')
    binding.update({'command': cmd, 'cwd': str(clone), 'exit_code': run.returncode, 'stderr': run.stderr,
                    'checker': ref(checker), 'manifest': manifest_ref, 'result': r2_ref,
                    'scope': 'Actual reference bytes and exact candidate identity verified; R2 ten gate findings structurally match. Readiness remains false.'})
    binding_ref = write('candidate-bound-evidence-validation.v1.json', binding)
    record = envelope('v6-stage3-rebuild-required', 'REBUILD_REQUIRED')
    record['schema_version'] = 'mrw.formal_release.stage3.candidate_artifact.v2'
    record.update(decisions['main_fields'])
    record.update({'input_refs_and_sha256': inputs, 'test_families_and_exact_results': decisions['gates'],
                   'warning_skip_deselect_inventory': gates_ref, 'cleanup_and_retained_resources': cleanup_ref,
                   'release_evidence_manifest_and_r2_result': {'manifest': manifest_ref, 'result': r2_ref, 'binding': binding_ref, 'exit_code': run.returncode, 'readiness': result['readiness']},
                   'open_failures': decisions['blockers'], 'source_receipts': leaves})
    main_ref = write('stage3-candidate-artifact.rebuild-required.v1.json', record)
    index = envelope('v6-final-index', 'REBUILD_REQUIRED')
    index.update({'main_record': main_ref, 'evidence': [ref(p) for p in sorted(ROOT.rglob('*')) if p.is_file() and not p.is_symlink()],
                  'identity_rule': 'Evidence path is the unique identity; raw receipt record_ids are namespaced by path.',
                  'superseded_attempts_policy': 'All failed attempts and integration-input preparation draft retained; active gate conclusions use integration-decisions.final.v1.json.'})
    index_ref = write('evidence-index.rebuild-required.v1.json', index)
    print(json.dumps({'main': main_ref, 'index': index_ref, 'r2_exit': run.returncode, 'r2_report_status': result['report']['status']}))

if __name__ == '__main__':
    main()
