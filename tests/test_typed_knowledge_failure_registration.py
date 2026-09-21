from __future__ import annotations

import ast
import json
from pathlib import Path

from mrw_functorial_kit.core.typed_knowledge_semantics import (
    typed_knowledge_persistence_boundary_failures,
)


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = ROOT / "main/backend/app/services/typed_knowledge/persistence_boundary.py"


def _runtime_failure_code() -> str:
    module = ast.parse(RUNTIME_SOURCE.read_text(encoding="utf-8"))
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name)
            and target.id == "TYPED_KNOWLEDGE_PERSISTENCE_BOUNDARY_FAILURE"
            for target in statement.targets
        ):
            continue
        value = ast.literal_eval(statement.value)
        assert isinstance(value, str)
        return value
    raise AssertionError("typed-knowledge runtime failure code constant is missing")


def test_INVARIANT__typed_knowledge_boundary_failure_matches_runtime() -> None:
    assert typed_knowledge_persistence_boundary_failures.codes == (
        _runtime_failure_code(),
    )


def test_INVARIANT__typed_knowledge_boundary_failure_matches_registry() -> None:
    entries = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}
    assert registered["typed_knowledge.persistence_boundary_failure"] == (
        typed_knowledge_persistence_boundary_failures.codes
    )


def test_FAILURE_PRESERVED__typed_exception_keeps_family_member() -> None:
    failure = typed_knowledge_persistence_boundary_failures.fail(
        _runtime_failure_code(),
        "specific diagnostic",
    )
    assert typed_knowledge_persistence_boundary_failures.matches(failure)
