from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "functorial-kit.json"
REGISTRY = ROOT / "registries/failures.json"
SKETCHES = ROOT / "sketches.json"
POLICY_TYPES = ROOT / "main/backend/app/production_contract/types.py"
FAMILY = "mrw.production-policy.failure.v1"


def _constant_from_assignment(tree: ast.AST, name: str) -> object:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"assignment not found: {name}")  # noqa: TRY003


def test_INVARIANT__s1_production_contract_paths_are_scanned_by_kit() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    core_paths = set(config["core_paths"])
    shell_paths = set(config["shell_paths"])

    assert {
        "main/backend/app/production_observability",
        "main/ops/production_contract",
        "main/backend/app/composition/production.py",
    } <= shell_paths
    assert "main/backend/app/production_contract" in shell_paths
    assert POLICY_TYPES.is_file()
    assert (ROOT / "main/backend/app/production_observability").is_dir()
    assert (ROOT / "main/ops/production_contract").is_dir()


def test_INVARIANT__s1_production_contract_is_inbound_shell_boundary() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert "main/backend/app/production_contract" not in config["core_paths"]
    assert "main/backend/app/production_contract" in config["shell_paths"]


def test_INVARIANT__s1_production_policy_failure_registry_matches_source() -> None:
    source_tree = ast.parse(POLICY_TYPES.read_text(encoding="utf-8"))
    expected_family = _constant_from_assignment(
        source_tree, "PRODUCTION_POLICY_FAILURE_FAMILY"
    )
    source_codes: tuple[str, ...] | None = None
    direct_family_literal: str | None = None
    for node in ast.walk(source_tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "production_policy_failures"
            for target in node.targets
        ):
            continue
        call = node.value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == "define_failure_family"
        assert isinstance(call.args[0], ast.Constant)
        assert isinstance(call.args[0].value, str)
        direct_family_literal = call.args[0].value
        source_codes = tuple(
            ast.literal_eval(element) for element in call.args[1].elts
        )
        break

    assert expected_family == FAMILY
    assert direct_family_literal == FAMILY
    assert source_codes is not None
    entries = json.loads(REGISTRY.read_text(encoding="utf-8"))["entries"]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}
    assert registered[FAMILY] == source_codes


def test_INVARIANT__s1_recovery_planners_are_explicitly_non_authoritative() -> None:
    source_tree = ast.parse(
        (ROOT / "main/ops/production_contract/fixture_recovery_tools.py").read_text(
            encoding="utf-8"
        )
    )
    annotations: dict[str, str] = {}
    for node in ast.walk(source_tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name in {"plan_recovery", "build_cli"}:
            assert isinstance(node.returns, ast.Subscript)
            annotation = ast.unparse(node.returns.slice)
            annotations[node.name] = annotation
            assert "kit:non-authoritative" in annotation
            assert "derived_as=" in annotation
            assert "fact_source=" in annotation
            assert "witness=test:" in annotation

    assert set(annotations) == {"plan_recovery", "build_cli"}


def test_INVARIANT__s1_production_sketch_binds_existing_witnesses() -> None:
    sketches = json.loads(SKETCHES.read_text(encoding="utf-8"))["entries"]
    sketch = next(
        entry
        for entry in sketches
        if FAMILY in entry.get("failures", [])
    )

    witnesses = {
        equation["witness"].removeprefix("test:")
        for equation in sketch["equations"]
        if equation["class"] == "testable"
    }
    assert witnesses == {
        "test_valid_fixture_passes_but_does_not_grant_authority",
        "test_failure_family_is_closed_and_decisions_are_immutable",
    }
    for witness in witnesses:
        assert witness in (
            ROOT / "main/backend/tests/production_contract/test_s1_production_policy.py"
        ).read_text(encoding="utf-8")
