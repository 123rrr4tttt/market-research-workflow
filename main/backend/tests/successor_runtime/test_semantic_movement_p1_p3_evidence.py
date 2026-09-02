"""P1-P3 evidence binding, C7 exact binding and projection tests."""

from __future__ import annotations

import hashlib
import json
import os
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
PLAN = (
    REPO
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration"
)

SPEC_SHA256 = "2a96bb63d0e3b548173558959da9fc4421024f300d9c39daf6dda5f7b79e53d2"
C7_DESIGN_SHA256 = hashlib.sha256(
    (PLAN / "evidence/semantic-movements/C7SemanticMovementDesign.v3.md").read_bytes()
).hexdigest()
C7_INVENTORY_DIGEST = "4c92fef4f38ebe6b8d5ddf95771bc6b4b4da3ca132ac177cbeddea706ebe4bf8"
C7_MATRIX_DIGEST = "b4d15c086a2d9699061f934fc57880741f6959c939a7a493b0420fafc7fd05fd"
C7_TRACE_DIGEST = "2f1c0f179449b26ad1403cf6dda0034890b9020ccde4900ce4487e8ec485f92d"


def _load(name: str) -> dict:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_spec_and_c7_external_bindings_are_exact() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    spec_binding = matrix["spec_binding"]
    assert spec_binding["bytes_sha256"] == SPEC_SHA256
    c7 = matrix["c7_external_binding"]
    assert c7["status"] == "EXACT_BOUND"
    assert c7["design_sha256"] == C7_DESIGN_SHA256
    design_binding = next(
        binding
        for binding in matrix["source_bindings"]
        if binding["role"] == "c7_external_semantic_design"
    )
    assert design_binding["sha256"] == C7_DESIGN_SHA256
    assert c7["design_sha256"] == design_binding["sha256"]
    assert c7["inventory_content_digest"] == C7_INVENTORY_DIGEST
    assert c7["matrix_content_digest"] == C7_MATRIX_DIGEST
    assert c7["trace_content_digest"] == C7_TRACE_DIGEST
    assert c7["row_count"] == 20
    assert c7["unassigned_blocker_count"] == 0
    assert c7["design_unassigned_blocker_count"] == 0
    assert (
        c7["movement_ids_exact"]
        and c7["blocker_ids_exact"]
        and c7["row_contents_exact"]
    )


def test_p2v5_and_p3_aggregate_refs_are_bound_exactly() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    roles = {binding["role"]: binding for binding in matrix["source_bindings"]}
    for role in (
        "p2_c21_capability_packet_v5",
        "p3_capability_migration_aggregate",
        "p1_eligibility",
        "p1_semantic_owner_inventory",
    ):
        binding = roles[role]
        assert len(binding["sha256"]) == 64
        assert binding["bytes"] > 0
    for family in ("C1", "C2", "C3", "C4", "C5", "C6", "C8", "C9"):
        assert roles[f"p1_fragment_{family}"]["bytes"] > 0
    for family in ("C2", "C3", "C4", "C5", "C6"):
        assert roles[f"p3_fragment_{family}"]["bytes"] > 0
    assert (
        "P2C21CapabilityPacket.v5.json" in roles["p2_c21_capability_packet_v5"]["path"]
    )
    assert (
        "P3CapabilityMigration.v1.json"
        in roles["p3_capability_migration_aggregate"]["path"]
    )


def test_evidence_refs_classification_has_no_unresolved_refs() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    gate = _load("P1P3SemanticMovementGate.v1.json")
    refs = gate["evidence_refs"]
    assert (
        refs["resolved"] + refs["typed_absence"] + refs["absence_evidence"]
        == (refs["total_refs"])
    )
    assert refs["absence_evidence"] == 0
    assert refs["typed_absence"] == 0
    unresolved = [
        {
            "movement_id": row["movement_id"],
            "field": field,
            "binding": binding,
        }
        for row in matrix["movements"]
        for field in ("source_evidence", "target_realization", "acceptance_trace")
        for binding in row["evidence_bindings"].get(field, [])
        if binding.get("kind") == "unresolved"
    ]
    assert unresolved == []
    c5_targets = {
        row["movement_id"]: row["target_realization"]
        for row in matrix["movements"]
        if row["movement_id"] in ("C5-M002", "C5-M005")
    }
    assert c5_targets == {
        "C5-M002": [
            "main/backend/app/successor_runtime/substrate/projections/agent_session.py"
        ],
        "C5-M005": [
            "main/backend/app/successor_runtime/substrate/projections/agent_session.py"
        ],
    }


def test_fragments_and_inventory_are_bijective_projections() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    inventory = _load("P1P3LegacyDonorSemanticMovementInventory.v1.json")
    matrix_ids = [row["movement_id"] for row in matrix["movements"]]
    families = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9")
    fragment_ids: list[str] = []
    for family in families:
        fragment = _load(f"fragments/{family}.v1.json")
        fragment_ids.extend(fragment["movement_ids"])
        assert fragment["is_projection_of_matrix"] is True
        assert fragment["matrix_content_digest"] == matrix["content_digest"]
        assert fragment["movement_count"] == len(fragment["movement_ids"])
    assert sorted(fragment_ids) == sorted(matrix_ids)
    assert len(set(fragment_ids)) == 60
    assert inventory["movement_ids"] == matrix_ids
    assert inventory["matrix_content_digest"] == matrix["content_digest"]


def test_trace_and_loss_account_is_exact_bound() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    gate = _load("P1P3SemanticMovementGate.v1.json")
    c2_m008 = next(
        row for row in matrix["movements"] if row["movement_id"] == "C2-M008"
    )
    assert c2_m008["disposition"] == "DECLARED_LOSS"
    assert "source_library.c2_4.compat.loss.v1" in str(c2_m008["projection_loss"])
    account = gate["trace_and_loss_account"]
    assert account["zero_loss_declared"] is False
    assert account["declared_loss_movements"] == [
        "C2-M008",
        "C7-MOV-002",
        "C7-MOV-011",
        "C7-MOV-021",
        "C7-MOV-031",
        "C7-MOV-041",
        "C7-MOV-070",
        "C7-MOV-060",
        "C7-MOV-061",
    ]
    assert (
        sum(
            movement.startswith("C7-MOV-")
            for movement in account["declared_loss_movements"]
        )
        == 8
    )
    c7_trace = json.loads(
        (PLAN / "evidence/semantic-movements/C7.TraceAndLossBundle.v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert c7_trace["content_digest"] == C7_TRACE_DIGEST
    assert c7_trace["zero_loss_declared"] is False
    assert len(c7_trace["declared_losses"]) == 8


def test_p1_cell_coverage_is_complete_cross_check() -> None:
    matrix = _load("P1P3SuccessorMovementMatrix.v1.json")
    eligibility = json.loads(
        (PLAN / "evidence/P1FunctorizationEligibility.v1.json").read_text(
            encoding="utf-8"
        )
    )
    eligible_cells = {str(cell["cell"]) for cell in eligibility["cells"]}
    non_c7_eligible = {cell for cell in eligible_cells if not cell.startswith("C7.")}
    movement_cells = {
        cell
        for row in matrix["movements"]
        if row["family"] != "C7"
        for cell in (row.get("p1_cells") or [])
    }
    assert movement_cells == non_c7_eligible
    assert len(non_c7_eligible) == 26
