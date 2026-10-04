"""P4 C8 evidence generator determinism and normalized-root tests."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c8_fragment.py"
_FRAGMENT_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p4-fragments/C8.json"
)
_CANDIDATE_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b17-2026-09-05/fragments/C8.json"
)
_FROZEN_PREDECESSOR_SHA256 = (
    "206e69ad34ab60948c8310c6012f15fc66a03386eb3d2b60ae9e88328c8316a6"
)
_FROZEN_SNAPSHOT_REL = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
    "stage-b16-2026-09-05/candidates/I1/snapshots/"
    + _FROZEN_PREDECESSOR_SHA256
)

if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.specification.c8_p4 import CONFIG
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    content_digest,
    fragment_bytes,
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c8_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def module_bytes() -> bytes:
    module = _load_generator()
    return fragment_bytes(CONFIG, module.build_fragment())


def test_frozen_predecessor_is_checked_from_history_only() -> None:
    historical = (_REPOSITORY_ROOT / _FROZEN_SNAPSHOT_REL).read_bytes()
    assert hashlib.sha256(historical).hexdigest() == _FROZEN_PREDECESSOR_SHA256


def test_fragment_root_schema_and_cells_are_normalized() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["phase"] == "P4"
    assert fragment["family"] == "C8"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fragment["lifecycle_state"] == "P4_NOT_STARTED"
    assert "topic" not in fragment
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C8.1",
        "C8.2",
        "C8.3",
        "C8.4",
    ]
    required_roots = {
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
    assert set(fragment) == required_roots


def test_cells_have_required_binding_fields_and_zero_effect_counts() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    required_cell_fields = {
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
    for cell in fragment["cells"]:
        assert set(cell) == required_cell_fields
        assert isinstance(cell["p1_cell_digest"], str)
        assert len(cell["p1_cell_digest"]) == 64
        assert cell["provider_calls"] == 0
        assert cell["postgres_requirement"] == "not_required"
        assert cell["program_digest"]["value"]
        assert cell["plan_digest"]["value"]
        for binding in cell["operation_bindings"]:
            assert set(binding) == {"operation_kind", "contract_digest", "role"}
            assert len(binding["contract_digest"]) == 64


def test_c8_3_locator_is_open_finding_without_guessed_source_binding() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C8_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED" in finding_ids
    assert "P0_TARGET_RUNTIME_ARCHITECTURE_UNFROZEN" not in finding_ids
    assert "C8_P4_NOT_STARTED" in finding_ids
    assert "C8_PROGRAMS_COMPILED_NOT_EXECUTED" in finding_ids
    assert "C8_3_REPORT_ADMISSION_DELIVERY_LOCATOR_UNBOUND" in finding_ids
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert not any("c8_3" in role for role in source_roles)
    c8_3_legacy = fragment["cells"][2]["legacy_observation"]
    assert c8_3_legacy["locator"].startswith("UNBOUND_C8_3")
    assert c8_3_legacy["adoption"] is False
    assert c8_3_legacy["availability"] == "READ_ONLY_UNAVAILABLE"
    assert c8_3_legacy["reads_only"] is True
    assert any(
        item.endswith("llm_report_export_token_state.py")
        for item in c8_3_legacy["missing_paths"]
    )


def test_bindings_are_exact_and_authority_is_false() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    for binding in (
        *fragment["source_bindings"],
        *fragment["implementation_bindings"],
        *fragment["test_bindings"],
    ):
        assert set(binding) == {"path", "sha256", "bytes", "lines", "role"}
        assert len(binding["sha256"]) == 64
        assert binding["bytes"] > 0
        assert binding["lines"] > 0
    assert all(not value for value in fragment["authority"].values())
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert {"p1_eligibility", "p1_fragment"} <= source_roles
    assert {
        "development_contract_01",
        "freeze_manifest_02",
        "architecture_correction_06",
    } <= source_roles


def test_generator_is_deterministic_and_digest_self_tests() -> None:
    module = _load_generator()
    first = module.build_fragment()
    second = module.build_fragment()
    assert module._canonical_json(first) == module._canonical_json(second)
    digest = module.content_digest(
        {key: value for key, value in first.items() if key != "content_digest"}
    )
    first["content_digest"] = digest
    module._self_test(first)


def test_c8_3_interface_digest_identity_is_shared() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    bindings = {
        binding["operation_kind"]: binding["contract_digest"]
        for binding in fragment["cells"][2]["operation_bindings"]
    }
    observation = fragment["cells"][2]["successor_observation"]
    assert (
        bindings["c8.report.admission.v1"] == observation["admission_interface_digest"]
    )
    assert bindings["c8.report.delivery.v1"] == observation["delivery_interface_digest"]


def test_c8_4_graph_closure_and_projection_digest_recorded() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    observation = fragment["cells"][3]["successor_observation"]
    assert len(observation["source_closure"]) == 2
    assert set(observation["source_closure"][0]) == {
        "identity",
        "digest",
        "revision",
        "incarnation",
        "handle_id",
    }
    assert observation["projection_digest"]


def test_legacy_parity_is_execution_based() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    for cell in fragment["cells"]:
        observation = cell["successor_observation"]
        assert observation["parity"]["executions"] == observation["ordered_steps"]
        assert observation["parity"]["failures"] == []


def test_current_adapter_and_persisted_candidate_each_remain_valid() -> None:
    persisted = json.loads((_REPOSITORY_ROOT / _CANDIDATE_REL).read_text())
    rebuilt = build_fragment(CONFIG, _REPOSITORY_ROOT)
    adapter_bytes = module_bytes()
    assert fragment_bytes(CONFIG, rebuilt) == adapter_bytes
    assert persisted["family"] == rebuilt["family"]
    assert persisted["content_digest"] == content_digest(
        {key: value for key, value in persisted.items() if key != "content_digest"}
    )
