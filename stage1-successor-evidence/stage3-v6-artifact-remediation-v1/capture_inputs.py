"""Capture immutable v6 inputs and observed repair bytes without granting qualification."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CANDIDATE = Path('/Users/wangyiliang/.codex/release-candidates/mrw-stage2-20260906-v6')
EVIDENCE = Path('/Users/wangyiliang/.codex/release-evidence/mrw-stage2-20260906-v6')
CONTRACT = Path(
    'development/latest-dev-docs/development-plans/CURRENT_DEV/'
    '2026-09-04-formal-production-release/15_production-deployment-stage3-v6-contract.v1.md'
)
EXPECTED = {
    'candidate-manifest.v6.json': '020ea3fe312fe5a21f5c064455fc7e2fb1d53440ca0a2dfa9bf115777c80ece1',
    'closure.final.v6.json': 'd2f0607fbf29422f78887c5c72ac17af2d867e719044fa03a545ba19a1e30e73',
    'stage2-record.final.v6.json': '0a6555aca056084f3e7645d03b7adf04b3e4f2be49d52294e48f2b2a239f9a90',
    'r1.final.v6.json': 'c0ed90b8d1253b0d8191cef46506d5ed436b74f34c6a4f8a0758de0b76ef8f2d',
    'r2.pass.v6.json': '0edca14b4177a63cb2046fb74ab01e1099d66277d5a778df91b6c7faedef9c76',
    'r3.pass.v6.json': '9f7bc679db5e6e481090e43c1c4ee9d59cfe29b9efa3d8e9fa470689cda61e03',
}
PATHS = (
    '.github/workflows/backend-tests.yml',
    '.github/branch-protection-required-checks.json',
    'main/backend/Dockerfile',
    'main/frontend-modern/Dockerfile',
    'main/frontend-modern/pnpm-lock.yaml',
    'main/frontend-modern/package-lock.json',
    'scripts/formal_release/check_static_production_contract.py',
    'scripts/formal_release/stage2_candidate_intake.py',
    'tests/formal_release/test_stage2_candidate_intake.py',
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(
        ['git', '--no-optional-locks', '-C', str(CANDIDATE), *args], text=True
    ).strip()


def main() -> None:
    contract_sha = sha(ROOT / CONTRACT)
    if contract_sha != 'f7d3637c5cc48eaf7396331c3657cc6cff42269dbf4ffab17af4f7a7a3170d5a':
        raise ValueError('CONTRACT_INPUT_DRIFT')
    commit, tree = git('rev-parse', 'HEAD', 'HEAD^{tree}').splitlines()
    if (commit, tree) != (
        '909eb608e538b6427bcbacca974f1efb05fef611',
        'a60b795e509aa5dc479904a321fba32ed0ab9ab2',
    ):
        raise ValueError('V6_IDENTITY_DRIFT')
    refs = []
    for name, expected in EXPECTED.items():
        observed = sha(EVIDENCE / name)
        if observed != expected:
            raise ValueError(f'V6_EVIDENCE_DRIFT:{name}')
        refs.append({'path': str(EVIDENCE / name), 'sha256': observed})
    payload = {
        'schema_version': 'mrw.stage3_v6_artifact_repair.input_observation.v1',
        'authoritative': False,
        'status': 'INPUTS_VERIFIED_REPAIR_IN_PROGRESS',
        'contract': {'path': str(CONTRACT), 'sha256': contract_sha},
        'predecessor': {'root': str(CANDIDATE), 'commit': commit, 'tree': tree, 'evidence': refs},
        'paths': [
            {'path': path, 'v6_sha256': sha(CANDIDATE / path),
             'observed_source_sha256': sha(ROOT / path),
             'observation_scope': 'RESUMED_REPAIR_OBSERVATION_NOT_TASK_START'}
            for path in PATHS
        ],
        'successor_created': False,
        'production_release_authorized': False,
    }
    output = HERE / 'input-observation.v1.json'
    with output.open('x', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write('\n')
    print(json.dumps({'path': str(output), 'sha256': sha(output)}))


if __name__ == '__main__':
    main()
