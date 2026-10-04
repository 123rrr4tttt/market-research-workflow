from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from app.successor_runtime.specification.runtime_kernel_abi import RuntimeKernelABI
from scripts.generate_runtime_kernel_abi_pilot import build_bytes

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parents[1]
ARTIFACT = (
    REPO
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/capability-specs"
    / "RuntimeKernelABI.v1.json"
)

EXACT_PROTOCOL_FILES = {
    "app/successor_runtime/language/program.py": "eba5147e44ada7ee264606cb64347132b902d86beebba14b9b9a1c3bb6f01e02",
    "app/successor_runtime/language/plan.py": "a8f5ab8ccc38c56ebfb67b6b7a1b36132bf45e132014f6d2a2ed0ee3ba7cfb82",
    "app/successor_runtime/runtime/assignments.py": "5cf914fbb3c49bc00f929ab184c5c5014f8013a6526af57e3283a12a8b8ca0b0",
    "app/successor_runtime/runtime/reducer.py": "0462576d08ec7748aaf96fabf739707ca44b3b6a4a9c1f85f52574122af31856",
    "app/successor_runtime/runtime/work_items.py": "5acf8ecdfc4c85aec16af6798f7ea24053b7b77a3ab49187a6a3387a4c5d75f2",
    "app/successor_runtime/substrate/postgres/work_items.py": "03252d2a746459a827b95bd3c3f6966172a0503f4763729e9c39eed23a641f24",
}


def test_runtime_kernel_abi_artifact_is_canonical_and_semantic() -> None:
    assert ARTIFACT.read_bytes() == build_bytes()
    abi = RuntimeKernelABI.from_dict(json.loads(ARTIFACT.read_text()))
    assert (
        abi.semantic_digest
        == "870aa856d153119093242b949be709586db0eb08779809feee0ad1b466e1baaa"
    )
    changed = replace(
        abi, program_protocol_version="mrw.successor.program.v2", semantic_digest=""
    )
    assert changed.compute_semantic_digest() != abi.semantic_digest


def test_exact_protocol_bytes_are_artifact_evidence_not_semantic_payload() -> None:
    abi = RuntimeKernelABI.from_dict(json.loads(ARTIFACT.read_text()))
    for relative, expected in EXACT_PROTOCOL_FILES.items():
        actual = hashlib.sha256((BACKEND / relative).read_bytes()).hexdigest()
        assert actual == expected
    artifact_evidence = dict(EXACT_PROTOCOL_FILES)
    artifact_evidence[next(iter(artifact_evidence))] = "0" * 64
    assert abi.compute_semantic_digest() == abi.semantic_digest
    assert artifact_evidence != EXACT_PROTOCOL_FILES


def test_direct_check_is_read_only() -> None:
    before = (ARTIFACT.read_bytes(), ARTIFACT.stat().st_mtime_ns)
    result = subprocess.run(
        [
            sys.executable,
            str(BACKEND / "scripts/generate_runtime_kernel_abi_pilot.py"),
            "--output",
            str(ARTIFACT),
            "--check",
        ],
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert (ARTIFACT.read_bytes(), ARTIFACT.stat().st_mtime_ns) == before
