from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = (
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release"
    / "stage0-evidence/kit-applicability.v1.json"
)
REQUIRED_LANGUAGES = {"python", "typescript", "rust"}
VALID_RESULTS = {"PASS", "FAIL", "BLOCKED", "NOT_RUN", "OBSERVED"}


def load_evidence() -> dict[str, object]:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_INVARIANT__kit_applicability_record_has_required_binding_and_ceiling() -> None:
    payload = load_evidence()

    assert payload["schema"] == "stage0-kit-applicability.v1"
    assert payload["status"] == "CONSUMER_GATE_CLOSED_WITH_UPSTREAM_FINDINGS_RETAINED"
    assert payload["status"] != "PASS"
    assert isinstance(payload["observed_at"], str) and payload["observed_at"]
    assert "CONSUMER_GATE_CLOSED" in payload["status_vocabulary"]

    scope = payload["scope"]
    assert isinstance(scope, dict)
    assert scope["stage"] == "0B"
    assert scope["authority"] == "NOT_AUTHORITY"
    assert scope["authority_all_false"] is True
    assert scope["live_provider"] is False
    assert scope["canonical_write"] is False

    binding = payload["project_binding"]
    assert isinstance(binding, dict)
    for key in ("project_root", "config", "config_sha256", "sketches", "stage_plan"):
        assert isinstance(binding.get(key), str) and binding[key]

    kit_binding = payload["kit_binding"]
    assert isinstance(kit_binding, dict)
    assert kit_binding["binding_mode"] == "read_only_external_checkout"
    assert kit_binding["worktree"] == "DIRTY"
    assert kit_binding["commit"] == "785ff25e201c9eae84c862e68e786bc975e7a800"
    assert kit_binding["isolated_source_tree"] == "40a8019815040ff00c0ce61c0cdca30ac004ec7e"
    assert kit_binding["isolated_tracked_source_sha256"] == "8ea96363e3c600b828ed07a0adc93691e23aa7b36883196e6f826ed0e8ad4fd2"
    assert len(kit_binding["isolated_untracked_python_build_sha256"]) == 64

    source_refs = payload["source_refs"]
    assert isinstance(source_refs, list) and len(source_refs) >= 6
    for source in source_refs:
        assert isinstance(source, dict)
        assert isinstance(source.get("path"), str) and source["path"]
        assert isinstance(source.get("sha256"), str) and len(source["sha256"]) == 64

    ceiling = payload["ceiling"]
    assert isinstance(ceiling, list)
    assert "PRODUCTION_RELEASE_NOT_AUTHORIZED" in ceiling
    assert "EXTERNAL_KIT_WORKTREE_DIRTY" in ceiling
    assert "TYPESCRIPT_NOT_APPLICABLE_TO_MRW_CONSUMER_UPSTREAM_CONFORMANCE_PASS" in ceiling
    assert "RUST_NOT_APPLICABLE_TO_MRW_CONSUMER_UPSTREAM_DEFAULT_COMPILE_FAILURE" in ceiling
    assert "PYTHON_CONSUMER_GATE_CLOSED_UPSTREAM_FINDINGS_RETAINED" in ceiling
    assert "UPSTREAM_KIT_FINDINGS_RETAINED_NON_AUTHORITY" in ceiling

    applicability = payload["applicability"]
    assert isinstance(applicability, dict)
    consumer = applicability["mrw_consumer"]
    upstream = applicability["upstream_kit_conformance"]
    assert consumer["consumer_language"] == "python"
    assert consumer["typescript"] == "NOT_APPLICABLE_TO_CONSUMER"
    assert consumer["rust"] == "NOT_APPLICABLE_TO_CONSUMER"
    assert consumer["consumer_gate_status"] == "CONSUMER_GATE_CLOSED"
    assert consumer["base_source_commit"] == "785ff25e201c9eae84c862e68e786bc975e7a800"
    assert consumer["base_source_tree"] == "40a8019815040ff00c0ce61c0cdca30ac004ec7e"
    assert consumer["patch_sha256"] == "bab5ddcf18a9312d99be4972e7c2addec233dab8faf7281d27f2148546cc0098"
    assert consumer["execution"]["status"] == "PASS"
    assert [item["observed"] for item in consumer["execution"]["commands"]] == ["49 passed", "6 passed", "295 passed"]
    assert upstream["typescript"] == "PASS"
    assert upstream["rust"] == "PARTIAL_WITH_DEFAULT_FEATURE_FAILURE_AND_TOOLING_BLOCKERS"


def test_INVARIANT__every_language_gate_status_is_execution_qualified() -> None:
    payload = load_evidence()
    languages = payload["languages"]
    assert isinstance(languages, dict)
    assert set(languages) == REQUIRED_LANGUAGES

    for name, language in languages.items():
        assert isinstance(language, dict), name
        gates = language["applicable_gates"]
        assert isinstance(gates, list) and gates, name
        commands = language["commands"]
        assert isinstance(commands, list) and commands, name
        for item in commands:
            assert isinstance(item, dict), name
            assert isinstance(item.get("command"), str) and item["command"], name
            assert item.get("result") in VALID_RESULTS, name
            executed = item.get("executed")
            assert isinstance(executed, bool), name
            if not executed:
                assert item["result"] in {"NOT_RUN", "BLOCKED"}, (name, item)
            if item["result"] == "PASS":
                assert executed is True, (name, item)
            if item["result"] in {"BLOCKED", "NOT_RUN"}:
                blocked_by = item.get("blocked_by")
                assert isinstance(blocked_by, list) and blocked_by and all(isinstance(v, str) and v for v in blocked_by), (
                    name,
                    item,
                )


def test_INVARIANT__python_typescript_and_rust_specific_ceilings_are_explicit() -> None:
    payload = load_evidence()
    languages = payload["languages"]
    assert isinstance(languages, dict)

    python = languages["python"]
    assert isinstance(python, dict)
    assert python["project_applicability"] == "APPLICABLE"
    assert python["runtime"]["pyright_in_project_venv"] == "1.1.411"
    assert python["runtime"]["external_kit_venv_pytest"] == "MISSING"
    assert python["consumer_gate_status"] == "CONSUMER_GATE_CLOSED"
    python_upstream = python["upstream_execution"]
    assert python_upstream["status"] == "BLOCKED"
    python_commands = python_upstream["commands"]
    assert any(item["result"] == "PASS" and "pytest" in item["command"] for item in python_commands)
    assert any(item["result"] == "FAIL" and "ruff format" in item["command"] for item in python_commands)
    assert any(item["result"] == "FAIL" and "pyright" in item["command"] for item in python_commands)

    typescript = languages["typescript"]
    assert isinstance(typescript, dict)
    assert typescript["project_applicability"] == "NOT_APPLICABLE_TO_CONSUMER"
    assert typescript["runtime"]["node_modules"] == "MISSING"
    assert any(item["result"] == "BLOCKED" for item in typescript["commands"])
    assert typescript["upstream_execution"]["status"] == "PASS"
    assert typescript["upstream_execution"]["commands"][-1]["observed"] == "40 tests passed"

    rust = languages["rust"]
    assert isinstance(rust, dict)
    assert rust["project_applicability"] == "NOT_APPLICABLE_TO_CONSUMER"
    features = rust["feature_applicability"]
    assert set(features) == {"default", "laws"}
    assert features["default"]["result"] == "NOT_RUN"
    assert features["laws"]["result"] == "NOT_RUN"
    assert rust["runtime"]["rustfmt"] == "MISSING"
    assert rust["runtime"]["clippy"] == "MISSING"
    assert rust["upstream_execution"]["status"] == "PARTIAL"
    assert any(item["result"] == "PASS" and "--features laws" in item["command"] for item in rust["upstream_execution"]["commands"])
    assert any(item["result"] == "FAIL" and item["command"].endswith("cargo test") for item in rust["upstream_execution"]["commands"])
