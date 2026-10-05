"""Read-only validation for frozen C7 semantic-movement evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[4]
ROOT = (
    REPO
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/semantic-movements"
)
INVENTORY = ROOT / "C7.LegacyDonorSemanticMovementInventory.v1.json"
MATRIX = ROOT / "C7.SuccessorMovementMatrix.v1.json"
TRACE = ROOT / "C7.TraceAndLossBundle.v1.json"

_EXPECTED_SHA256 = {
    INVENTORY: "8ca654e374b009f5ed97fec337a093a1751367f35c579f8e1afdc0e2273ac271",
    MATRIX: "b9d877f0d24b58aedc077b2ed36e2293859eec660917c1ef9ee03f18fe112515",
    TRACE: "43c72f47a239af8f3f94070259469b03dbbf18bec3a9038f9ddc49c94670d7b5",
}
_REQUIRED_MOVEMENT_FIELDS = (
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
)
_MOVEMENT_IDS = (
    "C7-MOV-001",
    "C7-MOV-002",
    "C7-MOV-003",
    "C7-MOV-010",
    "C7-MOV-011",
    "C7-MOV-020",
    "C7-MOV-021",
    "C7-MOV-030",
    "C7-MOV-031",
    "C7-MOV-040",
    "C7-MOV-041",
    "C7-MOV-050",
    "C7-MOV-051",
    "C7-MOV-060",
    "C7-MOV-061",
    "C7-MOV-070",
    "C7-MOV-071",
    "C7-MOV-072",
    "C7-MOV-073",
    "C7-MOV-074",
)
_DECLARED_LOSS_IDS = (
    "C7-MOV-002",
    "C7-MOV-011",
    "C7-MOV-021",
    "C7-MOV-031",
    "C7-MOV-041",
    "C7-MOV-060",
    "C7-MOV-061",
    "C7-MOV-070",
)
_TRACE_IDS = (
    "TRACE-C7-STRUCTURED-JSON",
    "TRACE-C7-LONG-REPORT",
    "TRACE-C7-DERIVED-REPORT",
    "TRACE-C7-PASS-THROUGH",
    "TRACE-C7-RETURN-CLEANUP",
)


def _content_digest(value: dict[str, object]) -> str:
    body = {key: item for key, item in value.items() if key != "content_digest"}
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_frozen_semantic_movement_bytes_and_digests_are_fixed() -> None:
    for path, expected in _EXPECTED_SHA256.items():
        payload = path.read_bytes()
        document = json.loads(payload)
        assert len(payload.splitlines()) == 1, path
        assert hashlib.sha256(payload).hexdigest() == expected, path
        assert document["content_digest"] == _content_digest(document), path


def test_frozen_matrix_schema_rows_topology_and_authority_ceiling() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert matrix["schema"] == (
        "mrw.functorial_successor.c7_successor_movement_matrix.v1"
    )
    assert matrix["family"] == "C7"
    assert matrix["scope"] == "C7.1-C7.4"
    assert matrix["status"] == "REDISPOSITION_CANDIDATE_DUAL_REVIEW_PENDING"
    assert matrix["promotion"] is False
    assert matrix["candidate"] is False
    assert matrix["unassigned_blockers"] == 0
    assert matrix["unassigned_blocker_ids"] == []
    assert all(value is False for value in matrix["authority_ceiling"].values())

    movements = matrix["movements"]
    assert tuple(row["movement_id"] for row in movements) == _MOVEMENT_IDS
    assert len({row["movement_id"] for row in movements}) == 20
    for row in movements:
        assert set(_REQUIRED_MOVEMENT_FIELDS) <= set(row)
        assert all(row[field] for field in _REQUIRED_MOVEMENT_FIELDS)
        assert row["disposition"] != "UNASSIGNED_BLOCKER"

    topology = matrix["decision_topology"]
    assert topology["ordered_prefix"] == [
        "RawSnapshot",
        "NormalizedIngestEnvelope",
        "DigestionDecision",
    ]
    assert topology["decision_selector"] == "DigestionDecision"
    assert topology["one_of"] is True
    assert topology["alternatives_serial"] is False
    assert topology["commutativity_claim"] == "NOT_CLAIMED"


def test_frozen_inventory_and_trace_are_consistent_matrix_projections() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    trace = json.loads(TRACE.read_text(encoding="utf-8"))

    assert inventory["schema"] == (
        "mrw.functorial_successor.c7_legacy_donor_movement_inventory.v1"
    )
    assert inventory["family"] == "C7"
    assert inventory["is_projection_of_matrix"] is True
    assert inventory["matrix_content_digest"] == matrix["content_digest"]
    assert inventory["movement_ids"] == list(_MOVEMENT_IDS)
    assert inventory["unassigned_blockers"] == 0

    assert trace["schema"] == "mrw.functorial_successor.c7_trace_and_loss_bundle.v1"
    assert trace["family"] == "C7"
    assert trace["zero_loss_declared"] is False
    assert trace["unaccepted_loss_blockers"] == []
    assert tuple(loss["movement_id"] for loss in trace["declared_losses"]) == (
        _DECLARED_LOSS_IDS
    )
    assert tuple(item["trace_id"] for item in trace["legacy_traces"]) == _TRACE_IDS
    assert matrix["trace_and_loss_digest"] == trace["content_digest"]
