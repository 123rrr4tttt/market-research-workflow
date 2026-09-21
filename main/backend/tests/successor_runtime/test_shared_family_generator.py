"""Shared family generator C7 parity, check gate and fail-closed tests."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.specification.c7_p4 import CONFIG
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    build_fragment_bytes,
    confine,
    content_digest,
    run_generate,
    validate_config,
)

FRAGMENT_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p4-fragments/C7.json"
)
CANDIDATE_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b12-2026-09-05/fragments/C7.json"
)
_FROZEN_CANONICAL_SHA256 = (
    "d3a7aaf1916d2a01c1ed6e7004a06d6cd6ed24840a7403fd10e2ffdc53559a83"
)
_FROZEN_SNAPSHOT_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b12-2026-09-05/candidates/C7/snapshots/"
    + _FROZEN_CANONICAL_SHA256
)
_LEGACY_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c7_fragment.py"


def _load_legacy_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c7_fragment", _LEGACY_GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _subprocess_env() -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    paths = [str(_BACKEND_ROOT), str(_REPOSITORY_ROOT / "src")]
    if existing:
        paths.append(existing)
    return {**os.environ, "PYTHONPATH": os.pathsep.join(paths)}


def test_shared_and_legacy_generators_keep_family_identity() -> None:
    legacy = _load_legacy_generator()
    oracle = legacy.build_fragment()
    shared = build_fragment(CONFIG, _REPOSITORY_ROOT)
    assert shared["family"] == oracle["family"] == "C7"
    assert shared["schema"] == oracle["schema"]
    assert all(not value for value in shared["authority"].values())
    assert all(not value for value in oracle["authority"].values())


def test_frozen_canonical_and_b12_candidate_are_distinct_evidence() -> None:
    canonical_path = _REPOSITORY_ROOT / FRAGMENT_REL
    canonical = (_REPOSITORY_ROOT / _FROZEN_SNAPSHOT_REL).read_bytes()
    assert hashlib.sha256(canonical).hexdigest() == _FROZEN_CANONICAL_SHA256
    canonical_payload = json.loads(canonical)
    assert canonical_payload["family"] == "C7"

    disk = canonical_path.read_bytes()
    assert build_fragment_bytes(build_fragment(CONFIG, _REPOSITORY_ROOT)) != disk
    candidate = json.loads(
        (_REPOSITORY_ROOT / CANDIDATE_REL).read_text(encoding="utf-8")
    )
    assert candidate["family"] == "C7"
    assert candidate["content_digest"] == content_digest(
        {key: value for key, value in candidate.items() if key != "content_digest"}
    )
    assert all(value is False for value in candidate["authority"].values())


def test_check_accepts_expected_frozen_canonical_drift_without_write() -> None:
    path = _REPOSITORY_ROOT / FRAGMENT_REL
    before = path.stat().st_mtime_ns
    before_bytes = path.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_ROOT / "scripts/generate_family_fragment_shared.py"),
            "--check",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=_subprocess_env(),
    )
    assert result.returncode == 1
    assert "DRIFT" in result.stderr
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before


def test_b12_candidate_checker_accepts_history_only_without_write() -> None:
    candidate_path = (
        _REPOSITORY_ROOT
        / CANDIDATE_REL
    ).parents[1] / "candidates/C7/candidate.v2.json"
    candidate_root = candidate_path.parent
    before = {
        path.relative_to(candidate_root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(candidate_root.rglob("*"))
        if path.is_file()
    }
    result = subprocess.run(
        [
            sys.executable,
            str(_REPOSITORY_ROOT / "scripts/stage_family_fragment_rebind.py"),
            "check-candidate",
            "--repo-root",
            str(_REPOSITORY_ROOT),
            "--candidate",
            candidate_path.relative_to(_REPOSITORY_ROOT).as_posix(),
            "--history-only",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == (
        "HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY"
    )
    after = {
        path.relative_to(candidate_root).as_posix(): (
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in sorted(candidate_root.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_check_drift_exits_one_without_write(tmp_path: Path) -> None:
    output = tmp_path / "C7.json"
    drifted = b'{"drift": true}\n'
    output.write_bytes(drifted)
    assert run_generate(CONFIG, _REPOSITORY_ROOT, check=True, output_path=output) == 1
    assert output.read_bytes() == drifted


def test_check_missing_output_exits_one(tmp_path: Path) -> None:
    output = tmp_path / "missing.json"
    assert run_generate(CONFIG, _REPOSITORY_ROOT, check=True, output_path=output) == 1
    assert not output.exists()


def test_authority_ceiling_all_false() -> None:
    fragment = build_fragment(CONFIG, _REPOSITORY_ROOT)
    authority = fragment["authority"]
    assert set(authority) == {
        "canonical_write",
        "credential",
        "graph",
        "index",
        "provider",
    }
    assert all(not value for value in authority.values())
    bad = replace(CONFIG, authority={**authority, "provider": True})
    with pytest.raises(ValueError):
        validate_config(bad)
    with pytest.raises(ValueError):
        build_fragment(bad, _REPOSITORY_ROOT)


def test_path_escape_rejected() -> None:
    with pytest.raises(ValueError):
        confine(_REPOSITORY_ROOT, "../outside")
    with pytest.raises(ValueError):
        confine(_REPOSITORY_ROOT, "/etc/passwd")
    escaped = replace(CONFIG, fragment_output_rel="../escaped/C7.json")
    assert run_generate(escaped, _REPOSITORY_ROOT, check=True) == 2


def test_required_field_validation() -> None:
    with pytest.raises(ValueError):
        validate_config(replace(CONFIG, family_id=""))
    with pytest.raises(ValueError):
        validate_config(replace(CONFIG, source_bindings=()))
    with pytest.raises(ValueError):
        validate_config(replace(CONFIG, authority={}))
    with pytest.raises(ValueError):
        validate_config(replace(CONFIG, cells=()))


def test_missing_cell_spec_fails_closed(tmp_path: Path) -> None:
    bad = replace(CONFIG, cell_spec_path="does/not/exist.json")
    assert (
        run_generate(
            bad,
            _REPOSITORY_ROOT,
            check=True,
            output_path=tmp_path / "out.json",
        )
        == 2
    )


def test_fragment_shape_and_shared_identities() -> None:
    fragment = build_fragment(CONFIG, _REPOSITORY_ROOT)
    assert set(fragment) == {
        "schema",
        "phase",
        "family",
        "fragment_id",
        "status",
        "lifecycle_state",
        "cells",
        "source_bindings",
        "implementation_bindings",
        "test_bindings",
        "authority",
        "open_findings",
        "content_digest",
    }
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["phase"] == "P4"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fragment["lifecycle_state"] == "P4_NOT_STARTED"
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
    ]
    required_cell_fields = {
        "cell_id",
        "p1_locators",
        "contract_ids",
        "legacy_observation",
        "successor_observation",
        "rollback_observation",
        "provider_calls",
        "postgres_requirement",
    }
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert cell["provider_calls"] == 0
        assert cell["p1_locators"]["locator_paths"]
        assert cell["rollback_observation"]["rollback_digest"]
        for observation in ("successor_observation", "legacy_observation"):
            assert cell[observation]["provider_calls"] == 0
            assert cell[observation]["authority"] is False
    closure = fragment["cells"][0]["successor_observation"][
        "runtime_assignment_closure"
    ]
    assert set(closure) == {
        "program_digest",
        "plan_digest",
        "step_id",
        "step_role",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    }
    for digest_key in (
        "program_digest",
        "plan_digest",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    ):
        assert len(closure[digest_key]) == 64
    for binding in (
        *fragment["source_bindings"],
        *fragment["implementation_bindings"],
        *fragment["test_bindings"],
    ):
        assert set(binding) == {"path", "sha256", "bytes", "lines", "role"}
        assert len(binding["sha256"]) == 64
        assert binding["bytes"] > 0
        assert binding["lines"] > 0
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert "shared_program_spec" in source_roles
    assert "shared_compiler" in source_roles
    assert "shared_commit_intent_verification_binding" in source_roles
    assert "p1_fragment_locators" in source_roles
    implementation_roles = {
        entry["role"] for entry in fragment["implementation_bindings"]
    }
    assert "c7_common_contracts" in implementation_roles
    assert "evidence_generator" in implementation_roles
    test_roles = {entry["role"] for entry in fragment["test_bindings"]}
    assert "c7_0_return_registry_invariants" in test_roles
    assert "c7_6_disposable_postgres" in test_roles
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C7_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED" in finding_ids
    assert "C7_P4_NOT_STARTED" in finding_ids


def test_shared_generator_is_deterministic() -> None:
    first = build_fragment(CONFIG, _REPOSITORY_ROOT)
    second = build_fragment(CONFIG, _REPOSITORY_ROOT)
    assert build_fragment_bytes(first) == build_fragment_bytes(second)
    assert first["content_digest"] == second["content_digest"]
