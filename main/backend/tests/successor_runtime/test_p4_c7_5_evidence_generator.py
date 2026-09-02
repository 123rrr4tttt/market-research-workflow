"""P4 C7 evidence generator determinism and normalized-root schema tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c7_fragment.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c7_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fragment_root_schema_cells_and_status_are_normalized() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["phase"] == "P4"
    assert fragment["family"] == "C7"
    assert fragment["status"] == "AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED"
    assert fragment["lifecycle_state"] == "P4_NOT_STARTED"
    assert fragment["fragment_id"]
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C7.1",
        "C7.2",
        "C7.3",
        "C7.4",
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


def test_cells_have_required_fields_and_zero_provider_calls() -> None:
    module = _load_generator()
    fragment = module.build_fragment()
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
    assert fragment["cells"][0]["successor_observation"]["admission_implied"] is False
    assert fragment["cells"][0]["successor_observation"]["step_kinds"] == [
        "EFFECT",
        "ADMISSION",
    ]
    assert fragment["cells"][0]["successor_observation"]["execution_class"] == (
        "EFFECTFUL"
    )
    assert (
        fragment["cells"][0]["successor_observation"]["document_write_boundary"]
        is False
    )
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
    assert closure["step_role"] == "EFFECT"
    assert fragment["cells"][1]["successor_observation"]["document_write"] is False
    assert fragment["cells"][2]["successor_observation"]["declared_loss"]
    assert fragment["cells"][3]["successor_observation"]["new_attempt_allowed"] is False


def test_bindings_are_exact_authority_false_and_shared_identities_bound() -> None:
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
    assert fragment["open_findings"]
    finding_ids = {entry["id"] for entry in fragment["open_findings"]}
    assert "C7_AHEAD_OF_TIME_SCAFFOLDING_UNADOPTED" in finding_ids
    assert "C7_P4_NOT_STARTED" in finding_ids
    assert "C7_SHARED_RUNTIME_MODULES_ABSENT_IN_WORKTREE" not in finding_ids
    source_roles = {entry["role"] for entry in fragment["source_bindings"]}
    assert "shared_program_spec" in source_roles
    assert "shared_compiler" in source_roles
    assert "shared_commit_intent_verification_binding" in source_roles
    assert "shared_effect_reconciler" in source_roles
    assert "shared_runtime_assignment" in source_roles
    assert "shared_document_admission_return_contract_registry" in source_roles
    assert "shared_projection_offset_repository" in source_roles
    assert "p1_fragment_locators" in source_roles
    for frozen_role in (
        "frozen_locator_frontdoor_orchestrator",
        "frozen_locator_entities",
        "frozen_locator_graph_persistence",
        "frozen_locator_dry_run",
        "frozen_locator_cleanup",
        "frozen_locator_db_retry",
        "frozen_locator_rollout",
    ):
        assert frozen_role in source_roles
    roles = {entry["role"] for entry in fragment["implementation_bindings"]}
    assert "c7_common_contracts" in roles
    assert "c7_contracts" in roles
    assert "c7_program" in roles
    assert "c7_recovery" in roles
    assert "c7_document_repository" in roles
    assert "c7_projection_common" in roles
    test_roles = {entry["role"] for entry in fragment["test_bindings"]}
    assert "c7_0_return_registry_invariants" in test_roles
    assert "c7_6_disposable_postgres" in test_roles


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
    persisted = json.loads(module.FRAGMENT_PATH.read_text())
    assert persisted["schema"] == module.FRAGMENT_SCHEMA
    persisted_digest = module.content_digest(
        {key: value for key, value in persisted.items() if key != "content_digest"}
    )
    assert persisted["content_digest"] == persisted_digest
    assert module.build_fragment()["content_digest"] == persisted["content_digest"]


def test_persisted_fragment_matches_generated_bytes() -> None:
    module = _load_generator()
    persisted = json.loads(module.FRAGMENT_PATH.read_text())
    rebuilt = module.build_fragment()
    rebuilt["content_digest"] = module.content_digest(
        {key: value for key, value in rebuilt.items() if key != "content_digest"}
    )
    assert module._canonical_json(rebuilt) == module._canonical_json(persisted)
