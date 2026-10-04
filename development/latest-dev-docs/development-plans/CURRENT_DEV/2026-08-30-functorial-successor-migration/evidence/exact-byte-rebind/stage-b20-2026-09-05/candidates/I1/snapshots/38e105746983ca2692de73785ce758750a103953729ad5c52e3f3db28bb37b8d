"""P3 C3 evidence fragment determinism and schema contracts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parents[1]
_GENERATOR = _BACKEND / "scripts/generate_successor_p3_c3_fragment.py"
_TOPIC_FRAGMENT = (
    _ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C3.json"
)
_ROOT_FRAGMENT = _ROOT / "evidence/p3-fragments/C3.json"

_EXPECTED_ROOT_KEYS = {
    "schema",
    "phase",
    "family",
    "fragment_id",
    "status",
    "cells",
    "source_bindings",
    "implementation_bindings",
    "test_bindings",
    "authority",
    "open_findings",
    "content_digest",
}

_EXPECTED_CELL_KEYS = {
    "cell_id",
    "p1_cell_digest",
    "operation_bindings",
    "owner_capability_id",
    "program_digest",
    "plan_digest",
    "legacy_observation",
    "successor_observation",
    "rollback_observation",
    "provider_calls",
    "postgres_requirement",
}


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c3_fragment",
        _GENERATOR,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_fragment_build_is_deterministic_across_two_runs() -> None:
    generator = _load_generator()
    first = generator.build_fragment()
    second = generator.build_fragment()
    assert generator.fragment_bytes(first) == generator.fragment_bytes(second)
    assert first["content_digest"] == second["content_digest"]
    assert first["content_digest"] == _canonical_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )


def test_fragment_root_schema_and_status_are_exact() -> None:
    generator = _load_generator()
    fragment = generator.build_fragment()
    assert set(fragment) == _EXPECTED_ROOT_KEYS
    assert fragment["schema"] == "mrw.functorial_successor.p3_fragment.v1"
    assert fragment["phase"] == "P3"
    assert fragment["family"] == "C3"
    assert fragment["fragment_id"] == "p3-c3-family-local-implementation"
    assert fragment["status"] == "IMPLEMENTED_CANDIDATE_NOT_PROMOTED"
    assert [cell["cell_id"] for cell in fragment["cells"]] == ["C3.1", "C3.2"]


def test_fragment_cells_carry_required_validation_design_fields() -> None:
    generator = _load_generator()
    fragment = generator.build_fragment()
    for cell in fragment["cells"]:
        assert set(cell) == _EXPECTED_CELL_KEYS
        assert cell["provider_calls"] == 0
        assert cell["postgres_requirement"] == (
            "required_and_verified_mrw_p3_c3_worker_test"
        )
        assert len(cell["p1_cell_digest"]) == 64
        assert cell["legacy_observation"]["provider_calls"] == 0
        assert cell["successor_observation"]["provider_calls"] == 0
        assert cell["rollback_observation"]["claim_owner"] == "legacy"
        assert cell["rollback_observation"]["dual_claim"] is False
        assert cell["rollback_observation"]["journal_readable"] is True
        for digest_field in ("program_digest", "plan_digest"):
            binding = cell[digest_field]
            assert set(binding) == {"value", "reason"}
            if binding["value"] is not None:
                assert len(binding["value"]) == 64


def test_shared_traversal_dependency_is_bound_read_only() -> None:
    generator = _load_generator()
    fragment = generator.build_fragment()
    shared = [
        binding
        for binding in fragment["source_bindings"]
        if binding["role"] == "shared_dependency_traverse_ordered"
    ]
    assert len(shared) >= 5
    assert all(binding["read_only"] is True for binding in shared)
    paths = {binding["path"] for binding in shared}
    assert "main/backend/app/successor_runtime/language/compile.py" in paths
    assert "main/backend/app/successor_runtime/language/program.py" in paths
    assert "main/backend/app/successor_runtime/language/plan.py" in paths

    review = [
        binding
        for binding in fragment["source_bindings"]
        if binding["role"] == "shared_traversal_review_evidence"
    ]
    assert len(review) == 1
    assert review[0]["read_only"] is True
    assert review[0]["path"].endswith("P2C21CapabilityPacket.v4.json")
    assert len(review[0]["sha256"]) == 64
    superseded = [
        binding
        for binding in fragment["source_bindings"]
        if binding["role"] == "shared_traversal_review_superseded"
    ]
    assert {binding["path"].split("/")[-1] for binding in superseded} == {
        "P2C21CapabilityPacket.v2.json",
        "P2C21CapabilityPacket.v3.json",
    }
    assert all(binding["read_only"] is True for binding in superseded)
    assert all(
        finding["id"] != "C3_TRAVERSAL_SHARED_BINDING_UNREVIEWED"
        for finding in fragment["open_findings"]
    )


def test_topic_fragment_write_is_stable_and_matches_build() -> None:
    generator = _load_generator()
    first_bytes = generator.fragment_bytes(generator.build_fragment())
    generator.write_fragment()
    second_bytes = generator.fragment_bytes(generator.build_fragment())
    assert second_bytes == first_bytes
    assert _TOPIC_FRAGMENT.read_bytes() == first_bytes
    written = json.loads(_TOPIC_FRAGMENT.read_bytes())
    assert written["content_digest"] == _canonical_digest(
        {key: value for key, value in written.items() if key != "content_digest"}
    )


def test_wrong_root_copy_is_not_authoritative() -> None:
    assert not _ROOT_FRAGMENT.exists()
    assert _TOPIC_FRAGMENT.exists()
