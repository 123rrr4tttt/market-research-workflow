"""Deterministic route-decision and generated/handwritten ownership evidence."""

from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
GENERATOR = BACKEND_ROOT / "scripts/generate_capability_spec_route_decision.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_capability_spec_route_decision", GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_decision_records_exact_route_and_p3_prerequisite() -> None:
    module = _load_generator()
    decision, _ownership = module.build_documents(REPOSITORY_ROOT)

    assert decision["schema"] == module.DECISION_SCHEMA
    assert decision["goal_id"] == "01a0504c-47ef-77e1-9783-454dbcbe3697"
    assert decision["route"]["name"] == (
        "CAPABILITY_SPEC_COMPILATION_AND_VERTICAL_PRODUCT_SLICES"
    )
    assert decision["route"]["normative_class"] == "NOT_A_FROZEN_AMENDMENT"
    authorization = decision["user_authorization_record"]
    assert authorization["payload"] == module.USER_AUTHORIZATION_SEMANTICS
    assert authorization["semantic_digest"] == module._sha256(
        module._canonical_json_bytes(module.USER_AUTHORIZATION_SEMANTICS)
    )
    assert decision["p3_prerequisite"]["passed"] is True
    assert decision["p3_prerequisite"]["aggregate"]["file_sha256"] == (
        module.P3_FILE_SHA256
    )
    assert decision["p3_prerequisite"]["aggregate"]["content_digest"] == (
        module.P3_CONTENT_DIGEST
    )
    review = decision["p3_prerequisite"]["independent_review"]
    assert review["binding_kind"] == "unique_record_slice_not_whole_file"
    assert review["review_task_identity"] == module.P3_REVIEW_TASK
    assert review["disposition"] == "ALLOW_P3_AGGREGATE_LOCAL_ONLY_PROMOTION"
    assert "file_sha256" not in review
    assert all(
        binding["path"]
        not in {
            str(module.PROGRESS_REL),
            str(module.TOPIC_REL / "04_functorial-successor-capability-ledger.json"),
        }
        for binding in decision["normative_inputs"]
    )


def test_route_shape_pilots_slices_c1_and_dual_identity_are_exact() -> None:
    module = _load_generator()
    decision, _ownership = module.build_documents(REPOSITORY_ROOT)

    assert decision["pilot"]["representative_cells"] == ["C7.1", "C8.2", "C9.1"]
    assert [item["slice"] for item in decision["vertical_slices"]] == ["A", "B", "C"]
    assert decision["c1_cross_cutting_surface"]["cells"] == ["C1.1", "C1.2", "C1.3"]
    assert decision["identity_model"]["semantic_identity"][
        "semantic_change_requires_review"
    ]
    assert decision["identity_model"]["artifact_identity"][
        "required_in_addition_to_semantic_identity"
    ]
    assert decision["identity_model"]["freeze_or_packet_binding_bypass"] is False
    assert decision["normative_conflict_policy"]["mode"] == "FAIL_CLOSED"
    assert decision["candidate_state"] == "NO_CANDIDATE"


def test_ownership_map_keeps_mechanics_generated_and_semantics_handwritten() -> None:
    module = _load_generator()
    decision, ownership = module.build_documents(REPOSITORY_ROOT)

    assert ownership["schema"] == module.OWNERSHIP_SCHEMA
    assert ownership["decision_binding"]["content_digest"] == decision["content_digest"]
    generated = ownership["generated_ownership"]
    assert generated["manual_edit"] == "PROHIBITED"
    assert generated["read_only_check"] == "REQUIRED"
    assert generated["truth_source_exclusions"] == ["runtime", "semantics", "authority"]
    handwritten = ownership["handwritten_ownership"]
    assert handwritten["exact_binding"] == "REQUIRED"
    assert set(handwritten["responsibilities"]) == {
        "domain_transformation_semantics",
        "failure_ownership",
        "effect_execution_and_ordering",
        "resource_behavior",
        "cancellation_behavior",
        "retry_behavior",
        "verification_and_admission",
        "recovery_and_readback",
        "projection_information_loss",
        "authority_adoption",
    }


def test_authority_is_all_false_and_no_pilot_or_candidate_is_claimed() -> None:
    module = _load_generator()
    decision, ownership = module.build_documents(REPOSITORY_ROOT)

    for artifact in (decision, ownership):
        assert artifact["authority_ceiling"] == {
            "live_provider": False,
            "external_delivery": False,
            "cutover": False,
            "authority_transfer": False,
        }
        assert not any(artifact["authority_ceiling"].values())
        assert artifact["candidate_state"] == "NO_CANDIDATE"
    assert decision["pilot"]["status"] == "AUTHORIZED_PENDING_EXECUTION"
    assert decision["route"]["p4_adoption"] == "NOT_STARTED_BY_THIS_DECISION"


def test_build_is_deterministic_digest_valid_and_sensitive_to_readiness_binding() -> (
    None
):
    module = _load_generator()
    first = module.build_documents(REPOSITORY_ROOT)
    second = module.build_documents(REPOSITORY_ROOT)
    assert first == second
    for artifact in first:
        assert artifact["content_digest"] == module.content_digest(artifact)

    changed = copy.deepcopy(first[0])
    changed["current_readiness_inputs"][0]["file_sha256"] = "0" * 64
    changed = module._finalize(changed)
    assert changed["content_digest"] != first[0]["content_digest"]


def test_persisted_outputs_match_generated_exact_bytes() -> None:
    module = _load_generator()
    decision, ownership = module.build_documents(REPOSITORY_ROOT)
    assert (REPOSITORY_ROOT / module.DECISION_REL).read_bytes() == module._serialized(
        decision
    )
    assert (REPOSITORY_ROOT / module.OWNERSHIP_REL).read_bytes() == module._serialized(
        ownership
    )


def test_check_match_preserves_bytes_and_mtime() -> None:
    module = _load_generator()
    paths = [
        REPOSITORY_ROOT / module.DECISION_REL,
        REPOSITORY_ROOT / module.OWNERSHIP_REL,
    ]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--check"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CHECK_OK" in result.stdout
    assert [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths] == before


def test_check_drift_exits_one_and_does_not_write(tmp_path: Path) -> None:
    module = _load_generator()
    decision, ownership = module.build_documents(REPOSITORY_ROOT)
    decision_path = tmp_path / "decision.json"
    ownership_path = tmp_path / "ownership.json"
    decision_path.write_bytes(module._serialized(decision) + b"drift")
    ownership_path.write_bytes(module._serialized(ownership))
    before = [
        (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (decision_path, ownership_path)
    ]
    result = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--check",
            "--decision-output",
            str(decision_path),
            "--ownership-output",
            str(ownership_path),
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "DRIFT" in result.stdout
    assert [
        (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (decision_path, ownership_path)
    ] == before


def test_unknown_argument_exits_two_without_writing() -> None:
    module = _load_generator()
    paths = [
        REPOSITORY_ROOT / module.DECISION_REL,
        REPOSITORY_ROOT / module.OWNERSHIP_REL,
    ]
    before = [path.read_bytes() for path in paths]
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--unknown-route-option"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert [path.read_bytes() for path in paths] == before
