from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_TOPIC = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
_P1 = _TOPIC / "evidence/P1FunctorizationEligibility.v1.json"
_SELECTION = _TOPIC / "evidence/P2C21Selection.v1.json"


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_selection_binds_exact_reviewed_p1_artifact_and_c2_1_cell() -> None:
    p1_bytes = _P1.read_bytes()
    p1 = json.loads(p1_bytes)
    selection = json.loads(_SELECTION.read_bytes())

    assert selection["p1_artifact"] == {
        "path": (
            "development/latest-dev-docs/development-plans/CURRENT_DEV/"
            "2026-08-30-functorial-successor-migration/evidence/"
            "P1FunctorizationEligibility.v1.json"
        ),
        "file_sha256": hashlib.sha256(p1_bytes).hexdigest(),
        "content_digest": p1["content_digest"],
    }

    cell = next(row for row in p1["cells"] if row["cell"] == "C2.1")
    assert selection["selected_cell"]["cell_digest"] == _canonical_digest(cell)
    assert selection["selected_cell"]["disposition"] == cell["disposition"]
    assert selection["selected_cell"]["risk"] == cell["risk"]
    assert selection["selected_cell"]["p1_atom_kind"] == cell["atom_kind"]
    assert selection["selected_cell"]["operation_kind"] == (
        "source_library.resolve_execution_request.v1"
    )


def test_selection_content_digest_and_authority_ceiling_fail_closed() -> None:
    selection = json.loads(_SELECTION.read_bytes())
    claimed = selection.pop("content_digest")
    assert claimed == _canonical_digest(selection)
    assert selection["status"] == "FROZEN_SELECTION_IMPLEMENTATION_NOT_PROMOTED"
    assert selection["independent_review"] == {
        "task": "/root/p1_eligibility_review",
        "disposition": "ALLOW P1 COMPLETE AND SELECT C2.1 FOR P2",
        "open_p0": [],
        "open_p1": [],
    }

    authority = selection["authority"]
    assert authority["local_fixture_replay_shadow"] is True
    for key in (
        "business_authority_migrated",
        "successor_claim_enabled",
        "live_provider",
        "external_delivery",
        "production_canonical_write",
        "cutover",
        "authority_transfer",
    ):
        assert authority[key] is False
