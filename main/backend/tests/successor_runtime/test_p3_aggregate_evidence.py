from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.generate_successor_p3_aggregate import (
    CELL_ORDER,
    FAMILY_ORDER,
    AggregateBuildError,
    FileSnapshot,
    _assert_authority_and_effect_ceiling,
    _assert_inputs_unchanged,
    _canonical_slice_digest,
    _external_family_review,
    _filter_git_status,
    _finding_scopes,
    _operation_identities,
    _path_manifest,
    _promotion_anchor,
    _resolve_cli_output,
    _write_json_atomic,
)
from scripts.validate_successor_migration_batch import (
    P3_AGGREGATE_SCHEMA,
    canonical_content_digest,
    validate_p3_aggregate_document,
)

pytestmark = pytest.mark.unit


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot(path: str, data: bytes) -> FileSnapshot:
    return FileSnapshot(
        path=path,
        data=data,
        sha256=_sha256(data),
        bytes=len(data),
        lines=data.count(b"\n"),
    )


def _operation(kind: str, digest: str | None, role: str = "atom") -> dict[str, object]:
    return {"operation_kind": kind, "contract_digest": digest, "role": role}


def _cell(
    cell_id: str, *, operation: dict[str, object] | None = None
) -> dict[str, object]:
    return {
        "cell_id": cell_id,
        "owner_capability_id": f"owner.{cell_id}",
        "p1_cell_digest": "1" * 64,
        "program_digest": {"value": "2" * 64, "reason": "fixture"},
        "plan_digest": {"value": "3" * 64, "reason": "fixture"},
        "operation_bindings": [
            operation or _operation(f"operation.{cell_id}", "4" * 64)
        ],
        "provider_calls": 0,
        "successor_observation": {"provider_calls": 0},
        "rollback_observation": {"claim_owner": "legacy"},
    }


def _aggregate() -> dict[str, object]:
    aggregate: dict[str, object] = {
        "schema": P3_AGGREGATE_SCHEMA,
        "status": "PREREQUISITES_UNSATISFIED_NOT_PROMOTED",
        "phase": "P3",
        "aggregate_id": "p3:sha256:" + "a" * 64,
        "families": list(FAMILY_ORDER),
        "cell_ids": list(CELL_ORDER),
        "ordered_composition": {
            "family_order": list(FAMILY_ORDER),
            "cell_order": list(CELL_ORDER),
            "commutativity_claim": False,
        },
        "fragment_bindings": [{"family": family} for family in FAMILY_ORDER],
        "cell_bindings": [_cell(cell_id) for cell_id in CELL_ORDER],
        "external_family_reviews": [],
        "canonical_ownership": {
            "live_claim_owner": "legacy",
            "business_authority_migrated": False,
            "conflicting_contract_identities": [],
        },
        "worktree_identity": {
            "candidate_commit": None,
            "candidate_tree": None,
        },
        "authority_ceiling": {
            "provider_calls": 0,
            "network": False,
            "production_canonical_write": False,
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
            "legacy_retired": False,
            "candidate_created": False,
        },
        "promotion_prerequisites": {
            "promotion_claim": False,
            "satisfied": [],
            "unsatisfied": ["MISSING_EXACT_FAMILY_REVIEW:C2"],
        },
    }
    aggregate["content_digest"] = canonical_content_digest(aggregate)
    return aggregate


def test_p3_aggregate_validation_is_deterministic_and_accepts_review_missing() -> None:
    aggregate = _aggregate()
    first = json.dumps(aggregate, sort_keys=True, separators=(",", ":"))
    second = json.dumps(aggregate, sort_keys=True, separators=(",", ":"))
    assert first == second
    assert canonical_content_digest(aggregate) == aggregate["content_digest"]
    assert validate_p3_aggregate_document(aggregate) == ()
    assert aggregate["promotion_prerequisites"]["unsatisfied"]


def test_operation_order_is_preserved_and_shared_identity_is_derived() -> None:
    operations = [_operation("shared.v1", "a" * 64), _operation("second.v1", "b" * 64)]
    first = _cell("C2.2")
    first["operation_bindings"] = operations
    second = _cell("C2.3", operation=_operation("shared.v1", "a" * 64))
    shared, conflicts = _operation_identities([first, second])
    assert conflicts == []
    assert [item["operation_kind"] for item in first["operation_bindings"]] == [
        "shared.v1",
        "second.v1",
    ]
    assert shared == [
        {
            "operation_kind": "shared.v1",
            "contract_digest": "a" * 64,
            "references": [
                {
                    "cell_id": "C2.2",
                    "position": 0,
                    "role": "atom",
                    "contract_digest": "a" * 64,
                },
                {
                    "cell_id": "C2.3",
                    "position": 0,
                    "role": "atom",
                    "contract_digest": "a" * 64,
                },
            ],
        }
    ]


def test_operation_kind_digest_conflict_fails_closed() -> None:
    first = _cell("C2.2", operation=_operation("shared.v1", "a" * 64))
    second = _cell("C2.3", operation=_operation("shared.v1", "b" * 64))
    _, conflicts = _operation_identities([first, second])
    assert conflicts[0]["operation_kind"] == "shared.v1"

    aggregate = _aggregate()
    aggregate["cell_bindings"][0]["operation_bindings"] = [
        _operation("shared.v1", "a" * 64)
    ]
    aggregate["cell_bindings"][1]["operation_bindings"] = [
        _operation("shared.v1", "b" * 64)
    ]
    issues = validate_p3_aggregate_document(aggregate)
    assert any(
        issue.code == "P3_AGGREGATE_OPERATION_IDENTITY_CONFLICT" for issue in issues
    )


def test_authority_and_provider_negative_cases_fail_closed() -> None:
    fragment = {
        "family": "C2",
        "authority": {
            "live_provider": False,
            "production_canonical_write": False,
        },
        "cells": [_cell("C2.2")],
    }
    _assert_authority_and_effect_ceiling(fragment)

    fragment["authority"]["live_provider"] = True
    with pytest.raises(AggregateBuildError, match="authority ceiling violation"):
        _assert_authority_and_effect_ceiling(fragment)
    fragment["authority"]["live_provider"] = False
    fragment["cells"][0]["provider_calls"] = 1
    with pytest.raises(AggregateBuildError, match="provider_calls must be zero"):
        _assert_authority_and_effect_ceiling(fragment)
    fragment["cells"][0]["provider_calls"] = 0
    fragment["cells"][0]["rollback_observation"]["claim_owner"] = "successor"
    with pytest.raises(AggregateBuildError, match="must remain legacy"):
        _assert_authority_and_effect_ceiling(fragment)


def test_validator_rejects_authority_candidate_and_promotion_claims() -> None:
    aggregate = _aggregate()
    aggregate["authority_ceiling"]["cutover"] = True
    aggregate["worktree_identity"]["candidate_tree"] = "f" * 40
    aggregate["promotion_prerequisites"]["promotion_claim"] = True
    codes = {issue.code for issue in validate_p3_aggregate_document(aggregate)}
    assert "P3_AGGREGATE_AUTHORITY_VIOLATION" in codes
    assert "P3_AGGREGATE_CANDIDATE_IDENTITY_PRESENT" in codes
    assert "P3_AGGREGATE_PROMOTION_CLAIM_FORBIDDEN" in codes


def test_finding_scope_classification_is_local_only_aware() -> None:
    assert _finding_scopes("C2_3_LIVE_PROVIDER_AUTHORITY_NOT_FROZEN") == [
        "LIVE_PROVIDER"
    ]
    assert _finding_scopes("P3_REVIEW_SURFACE_NOT_GIT_IDENTIFIED") == [
        "P5_EXACT_CANDIDATE"
    ]
    assert _finding_scopes("C5_4_PROCESS_LOG_STATUS_NAMESPACE_COLLISION") == [
        "MAINTENANCE"
    ]


def test_external_review_requires_exact_fragment_and_progress_binding() -> None:
    fragment = {"content_digest": "a" * 64, "source_bindings": []}
    fragment_snapshot = _snapshot("fragment.json", b"fragment")
    ledger_snapshot = _snapshot("ledger.json", b"ledger")
    progress_snapshot = _snapshot(
        "progress.md", f"- P3 C2 promotion /root/reviewer {'a' * 64}".encode()
    )
    disposition = {
        "state": "PROMOTED_LOCAL_ONLY",
        "review_disposition": "ALLOW_C2_LOCAL_ONLY_PROMOTION",
        "independent_review": "/root/reviewer",
        "fragment_content_digest": "a" * 64,
        "fragment_file_sha256": fragment_snapshot.sha256,
        "open_blocking_p0": [],
        "open_blocking_p1": [],
    }
    review, missing = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        disposition,
        ledger_snapshot,
        progress_snapshot,
    )
    assert missing is None
    assert review["family"] == "C2"

    disposition["fragment_content_digest"] = "b" * 64
    review, missing = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        disposition,
        ledger_snapshot,
        progress_snapshot,
    )
    assert review is None
    assert missing == "MISSING_OR_STALE_EXACT_FAMILY_REVIEW:C2"


def test_external_review_ignores_aggregate_current_state_but_binds_exact_slice_and_anchor() -> (
    None
):
    fragment = {"content_digest": "a" * 64, "source_bindings": []}
    fragment_snapshot = _snapshot("fragment.json", b"fragment")
    disposition = {
        "state": "PROMOTED_LOCAL_ONLY",
        "review_disposition": "ALLOW_C2_LOCAL_ONLY_PROMOTION",
        "independent_review": "/root/reviewer",
        "fragment_content_digest": "a" * 64,
        "fragment_file_sha256": fragment_snapshot.sha256,
        "open_blocking_p0": [],
        "open_blocking_p1": [],
        "observed_validation": {"focused": "1 passed"},
    }
    anchor = f"- P3 C2 family promotion: /root/reviewer {'a' * 64}"
    first, missing = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        disposition,
        _snapshot("ledger.json", b'{"aggregate":{"digest":"old"}}'),
        _snapshot("progress.md", f"{anchor}\n- P3 aggregate old\n".encode()),
    )
    second, second_missing = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        disposition,
        _snapshot("ledger.json", b'{"aggregate":{"digest":"new"}}'),
        _snapshot("progress.md", f"{anchor}\n- P3 aggregate new\n".encode()),
    )
    assert missing is None and second_missing is None
    assert first == second
    assert first["record_source"]["canonical_slice_digest"] == (
        _canonical_slice_digest(disposition)
    )

    changed_disposition = {
        **disposition,
        "observed_validation": {"focused": "2 passed"},
    }
    changed, changed_missing = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        changed_disposition,
        _snapshot("ledger.json", b"changed"),
        _snapshot("progress.md", anchor.encode()),
    )
    assert changed_missing is None
    assert (
        changed["record_source"]["canonical_slice_digest"]
        != first["record_source"]["canonical_slice_digest"]
    )

    missing_anchor, anchor_error = _external_family_review(
        "C2",
        fragment_snapshot,
        fragment,
        disposition,
        _snapshot("ledger.json", b"same"),
        _snapshot("progress.md", b"- P3 aggregate only\n"),
    )
    assert missing_anchor is None
    assert anchor_error == "MISSING_OR_STALE_EXACT_FAMILY_REVIEW:C2"


def test_mutable_current_state_is_excluded_from_bound_path_manifest() -> None:
    snapshots = {
        "03.md": _snapshot("03.md", b"mutable progress"),
        "04.json": _snapshot("04.json", b"mutable ledger"),
        "fragment.json": _snapshot("fragment.json", b"immutable fragment"),
    }
    rows, digest = _path_manifest(snapshots, excluded_paths={"03.md", "04.json"})
    assert rows == [
        {
            "path": "fragment.json",
            "sha256": _sha256(b"immutable fragment"),
            "bytes": len(b"immutable fragment"),
            "lines": 0,
        }
    ]
    snapshots["03.md"] = _snapshot("03.md", b"different aggregate paragraph")
    snapshots["04.json"] = _snapshot("04.json", b"different aggregate block")
    assert _path_manifest(snapshots, excluded_paths={"03.md", "04.json"}) == (
        rows,
        digest,
    )


def test_promotion_anchor_requires_unique_exact_tokens() -> None:
    anchor = _promotion_anchor(
        "- P3 C2 promotion /root/reviewer digest\n- aggregate update\n",
        required_tokens=("/root/reviewer", "digest"),
        label="C2",
    )
    assert anchor is not None
    assert anchor["text_sha256"] == _sha256(anchor["text"].encode())
    assert (
        _promotion_anchor(
            "- aggregate update\n",
            required_tokens=("/root/reviewer", "digest"),
            label="C2",
        )
        is None
    )


def test_double_read_detects_input_drift(tmp_path: Path) -> None:
    path = tmp_path / "bound.json"
    path.write_bytes(b"one\n")
    snapshot = _snapshot("bound.json", path.read_bytes())
    _assert_inputs_unchanged(tmp_path, {"bound.json": snapshot})
    path.write_bytes(b"two\n")
    with pytest.raises(AggregateBuildError, match="INPUT_CHANGED_DURING_GENERATION"):
        _assert_inputs_unchanged(tmp_path, {"bound.json": snapshot})


def test_atomic_writer_replaces_complete_json(tmp_path: Path) -> None:
    output = tmp_path / "aggregate.json"
    _write_json_atomic(output, {"value": 1})
    assert json.loads(output.read_text()) == {"value": 1}
    _write_json_atomic(output, {"value": 2})
    assert json.loads(output.read_text()) == {"value": 2}
    assert list(tmp_path.glob(".aggregate.json.*")) == []


def test_git_status_digest_excludes_only_self_referential_canonical_artifact() -> None:
    status = b"?? evidence/P3CapabilityMigration.v1.json\0?? source.py\0"
    filtered = _filter_git_status(status, {"evidence/P3CapabilityMigration.v1.json"})
    assert filtered == b"?? source.py\0"


def test_relative_cli_output_resolves_from_repo_root_not_process_cwd(
    tmp_path: Path,
) -> None:
    assert (
        _resolve_cli_output(tmp_path, "evidence/aggregate.json")
        == (tmp_path / "evidence/aggregate.json").resolve()
    )


@pytest.mark.parametrize(
    "command",
    [
        [sys.executable, "scripts/generate_successor_p3_aggregate.py", "--help"],
        [sys.executable, "-m", "scripts.generate_successor_p3_aggregate", "--help"],
    ],
)
def test_direct_and_module_cli_imports(command: list[str]) -> None:
    backend_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        command,
        cwd=backend_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--check-only" in result.stdout
    assert "--allow-canonical-write" in result.stdout
