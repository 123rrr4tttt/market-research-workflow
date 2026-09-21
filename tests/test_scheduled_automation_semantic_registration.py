from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from functorial_kit import is_failure

from mrw_functorial_kit.core.scheduled_automation_semantics import (
    identity_warning_severities,
    matrix_valid_statuses,
    schedule_source_keys,
    schedule_source_values,
    scheduled_automation_blocker_classifications,
    scheduled_automation_classifications,
    scheduled_automation_failures,
    scheduled_automation_report_codec,
    scheduled_automation_statuses,
)


ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = ROOT / "scripts/check_scheduled_automation_artifacts.py"


def _checker_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "s8_scheduled_automation_checker", CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _checker_ast() -> ast.Module:
    return ast.parse(CHECKER_PATH.read_text(encoding="utf-8"))


def _constant(name: str, tree: ast.Module) -> Any:
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise AssertionError(name)


def _build_report_return_keys(tree: ast.Module) -> tuple[str, ...]:
    function = next(
        statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef) and statement.name == "build_report"
    )
    returns = [
        statement.value
        for statement in ast.walk(function)
        if isinstance(statement, ast.Return)
        and isinstance(statement.value, ast.Dict)
        and all(isinstance(key, ast.Constant) for key in statement.value.keys)
    ]
    assert len(returns) == 1
    return tuple(str(key.value) for key in returns[0].keys)


def test_INVARIANT__scheduled_automation_checker_registration_matches_ast() -> None:
    checker = _checker_module()
    tree = _checker_ast()
    expected_vocabularies = {
        scheduled_automation_statuses: (
            _constant("STATUS_PASSED", tree),
            _constant("STATUS_BLOCKED", tree),
        ),
        scheduled_automation_classifications: (
            _constant("CLASS_SCHEDULED", tree),
            _constant("CLASS_SCHEDULED_BLOCKED", tree),
            _constant("CLASS_MANUAL", tree),
            _constant("CLASS_MISSING", tree),
        ),
        scheduled_automation_blocker_classifications: tuple(
            _constant(name, tree)
            for name in (
                "TRIAGE_SCHEDULER_NOT_OBSERVED",
                "TRIAGE_SCHEDULER_CONFIGURED_PENDING_RUN",
                "TRIAGE_SCHEDULER_RAN_NO_ARTIFACT",
                "TRIAGE_ARTIFACT_WRONG_PATH",
                "TRIAGE_ARTIFACT_PRESENT_CHECKER_MISMATCH",
                "TRIAGE_SCHEDULED_RUN_BLOCKED",
            )
        ),
        matrix_valid_statuses: tuple(_constant("MATRIX_VALID_STATUSES", tree)),
        identity_warning_severities: tuple(
            _constant("IDENTITY_WARNING_SEVERITY_RANKS", tree)
        ),
        schedule_source_keys: tuple(_constant("SCHEDULE_SOURCE_KEYS", tree)),
        schedule_source_values: tuple(_constant("SCHEDULE_SOURCE_VALUES", tree)),
    }
    for vocabulary, expected in expected_vocabularies.items():
        assert vocabulary.members == expected or sorted(vocabulary.members) == sorted(expected)

    assert scheduled_automation_report_codec.discriminant == checker.SCHEMA_VERSION
    assert scheduled_automation_report_codec.keys == _build_report_return_keys(tree)

    vocabularies = json.loads(
        (ROOT / "registries/vocabularies.json").read_text(encoding="utf-8")
    )["entries"]
    registered_members = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    for vocabulary in expected_vocabularies:
        assert registered_members[vocabulary.name] == vocabulary.members


def test_INVARIANT__scheduled_automation_registry_and_failure_consistency() -> None:
    codecs = json.loads((ROOT / "registries/codecs.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    codec_discriminants = {entry["name"]: entry["discriminant"] for entry in codecs}
    assert (
        codec_discriminants["scheduled.automation.evidence.report"]
        == scheduled_automation_report_codec.discriminant
    )
    failures = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_codes["scheduled.automation.evidence.failure"] == (
        scheduled_automation_failures.codes
    )
    sketches = json.loads((ROOT / "sketches.json").read_text(encoding="utf-8"))["entries"]
    sketch = next(
        entry
        for entry in sketches
        if any(
            obj["name"] == "ScheduledAutomationArtifactEvidence"
            for obj in entry["objects"]
        )
    )
    assert sketch["derived"] == {
        "authoritative": False,
        "derived_as": "external_claim",
    }


def test_INVARIANT__scheduled_automation_identity_wire_projection_is_lossless() -> None:
    checker = _checker_module()
    report = checker.build_report(ROOT)
    wire = scheduled_automation_report_codec.to_wire(report)
    parsed = scheduled_automation_report_codec.parse(wire)
    assert not is_failure(parsed)
    assert parsed is report
    assert json.loads(json.dumps(report)) == report


def test_FAILURE_PRESERVED__scheduled_automation_foreign_discriminant_fails_closed() -> None:
    checker = _checker_module()
    report = checker.build_report(ROOT)
    drifted = dict(report)
    drifted["schema_version"] = "scheduled_automation_artifact_evidence.v0"
    result = scheduled_automation_report_codec.parse(drifted)
    assert is_failure(result)
    assert result.code == "CODEC_UNKNOWN_DISCRIMINANT"


def test_FAILURE_PRESERVED__scheduled_automation_invalid_status_fails_closed() -> None:
    checker = _checker_module()
    report = checker.build_report(ROOT)
    drifted = dict(report)
    drifted["status"] = "passed_without_scheduler"
    result = scheduled_automation_report_codec.parse(drifted)
    assert is_failure(result)
    assert scheduled_automation_failures.matches(result)
    assert result.code == "report_status_invalid"
