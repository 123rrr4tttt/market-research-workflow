"""P1-P3 semantic movement matrix/inventory contract tests."""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_DEFAULT_REPO = _BACKEND.parents[1]
REPO = Path(
    os.environ.get("P1P3_SEMANTIC_MOVEMENT_REPO_ROOT", str(_DEFAULT_REPO))
).resolve()
OUTPUT = Path(os.environ.get("P1P3_SEMANTIC_MOVEMENT_OUTPUT_ROOT", str(REPO))).resolve()

EVIDENCE = (
    OUTPUT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/semantic-movement"
)

REQUIRED_FIELDS = {
    "source_object",
    "target_object",
    "named_transform",
    "owner",
    "effect",
    "failure",
    "resource",
    "authority",
    "recovery",
    "projection_loss",
    "source_evidence",
    "target_realization",
    "acceptance_trace",
}
ALLOWED_DISPOSITIONS = {
    "PRESERVED_AS",
    "MOVED_TO",
    "REIMPLEMENTED_AS",
    "DECLARED_LOSS",
    "EXPLICITLY_REJECTED",
    "UNASSIGNED_BLOCKER",
}
EXPECTED_FAMILY_COUNTS = {
    "C1": 4,
    "C2": 8,
    "C3": 3,
    "C4": 5,
    "C5": 6,
    "C6": 4,
    "C7": 20,
    "C8": 5,
    "C9": 5,
}


def _load(relative: str) -> dict:
    return json.loads((EVIDENCE / relative).read_text(encoding="utf-8"))


def test_matrix_has_sixty_unique_movements_and_exact_blockers() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    rows = matrix["movements"]
    assert len(rows) == 60
    assert len({row["movement_id"] for row in rows}) == 60
    assert matrix["inline_movement_count"] == 40
    assert matrix["external_c7_movement_count"] == 20
    assert matrix["total_movement_count"] == 60
    assert matrix["unique_movement_ids"] == 60
    blocker_ids = [
        row["movement_id"] for row in rows if row["disposition"] == "UNASSIGNED_BLOCKER"
    ]
    assert matrix["unassigned_blocker_ids"] == blocker_ids
    assert matrix["unassigned_blocker_count"] == len(blocker_ids)
    assert len(blocker_ids) == len(set(blocker_ids))


def test_every_row_has_thirteen_fields_and_one_allowed_disposition() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    for row in matrix["movements"]:
        missing = REQUIRED_FIELDS - set(row)
        assert not missing, (row["movement_id"], sorted(missing))
        assert row["disposition"] in ALLOWED_DISPOSITIONS, row["movement_id"]
        assert row.get("locator_role") == "evidence_ref_only", row["movement_id"]
        assert set(row["evidence_bindings"]) == {
            "source_evidence",
            "target_realization",
            "acceptance_trace",
        }, row["movement_id"]


def test_disposition_counts_and_family_partitions() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    rows = matrix["movements"]
    row_dispositions = Counter(row["disposition"] for row in rows)
    assert matrix["disposition_counts"] == {
        disposition: row_dispositions.get(disposition, 0)
        for disposition in ALLOWED_DISPOSITIONS
    }
    for family, expected in EXPECTED_FAMILY_COUNTS.items():
        partition = matrix["family_partitions"][family]
        assert partition["movement_count"] == expected, family
        assert len(partition["movement_ids"]) == expected, family
        family_blockers = [
            row["movement_id"]
            for row in rows
            if row["family"] == family and row["disposition"] == "UNASSIGNED_BLOCKER"
        ]
        assert partition["unassigned_blocker_count"] == len(family_blockers), family


def test_locator_authority_separation_and_promotion_are_frozen() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    inventory = _load("P1P3LegacyDonorSemanticMovementInventory.v1.json")
    assert matrix["locator_counts_are_completeness"] is False
    assert inventory["locator_counts_are_completeness"] is False
    assert "runtime_authority_inventory_refs" in matrix
    assert matrix["promotion_decision"] is None
    assert matrix["promotion_allowed"] is False
    assert not any(matrix["authority_ceiling"].values())
    assert matrix["scope"]["does_not_revoke_or_reprove_p0_p3_local_only_state"] is True
    assert "does_not_authorize" in matrix["scope"]
    blocker_ids = [
        row["movement_id"]
        for row in matrix["movements"]
        if row["disposition"] == "UNASSIGNED_BLOCKER"
    ]
    account = matrix["unassigned_blocker_account"]
    assert account["exact_count_for_this_spec"] == len(blocker_ids)
    assert account["exact_count_for_this_spec"] == matrix["unassigned_blocker_count"]
    assert account["inline_count"] == len(blocker_ids) - account["external_C7_count"]
    assert account["external_C7_count"] == 0
    assert matrix["unassigned_blocker_account"]["promotion_allowed"] is False


def test_inventory_is_projection_of_matrix() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    inventory = _load("P1P3LegacyDonorSemanticMovementInventory.v1.json")
    matrix_ids = [row["movement_id"] for row in matrix["movements"]]
    assert inventory["movement_ids"] == matrix_ids
    assert inventory["matrix_content_digest"] == matrix["content_digest"]
    assert inventory["is_projection_of_matrix"] is True
    assert len(inventory["source_capabilities"]) == 60
    for capability in inventory["source_capabilities"]:
        assert capability["movement_id"] in matrix_ids
        assert capability["disposition"] in ALLOWED_DISPOSITIONS


def test_c7_fragment_preserves_external_c7_matrix_rows_exactly() -> None:
    fragment = _load("fragments/C7.v1.json")
    c7_matrix = json.loads(
        (
            REPO / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/semantic-movements/"
            "C7.SuccessorMovementMatrix.v1.json"
        ).read_text(encoding="utf-8")
    )
    wrapper_keys = {
        "family",
        "phase_partition",
        "p1_cell_scope",
        "locator_role",
        "evidence_bindings",
    }
    projected = [
        {key: value for key, value in row.items() if key not in wrapper_keys}
        for row in fragment["movements"]
    ]
    assert projected == c7_matrix["movements"]
