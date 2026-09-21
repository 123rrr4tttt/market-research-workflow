from __future__ import annotations

import ast
import json
from pathlib import Path

from mrw_functorial_kit.core.llm_provider_semantics import (
    llm_provider_names,
    llm_provider_resolution_failures,
)


ROOT = Path(__file__).resolve().parents[1]
PORTS_SOURCE = ROOT / "main/backend/app/services/llm/ports.py"
COMPOSITION_SOURCE = ROOT / "main/backend/app/composition/llm.py"


def _assigned_string(name: str) -> str:
    module = ast.parse(PORTS_SOURCE.read_text(encoding="utf-8"))
    for statement in module.body:
        if not isinstance(statement, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in statement.targets):
            value = ast.literal_eval(statement.value)
            assert isinstance(value, str)
            return value
    raise AssertionError(f"missing runtime constant: {name}")


def test_INVARIANT__llm_provider_registration_matches_runtime() -> None:
    assert llm_provider_resolution_failures.codes == (
        _assigned_string("LLM_PROVIDER_NOT_REGISTERED"),
    )
    composition = COMPOSITION_SOURCE.read_text(encoding="utf-8")
    assert all(f'"{name}"' in composition for name in llm_provider_names.members)


def test_INVARIANT__llm_provider_registration_matches_registries() -> None:
    vocab_entries = json.loads(
        (ROOT / "registries/vocabularies.json").read_text(encoding="utf-8")
    )["entries"]
    failure_entries = json.loads(
        (ROOT / "registries/failures.json").read_text(encoding="utf-8")
    )["entries"]
    registered_vocabularies = {
        entry["name"]: tuple(entry["members"]) for entry in vocab_entries
    }
    registered_failures = {
        entry["name"]: tuple(entry["codes"]) for entry in failure_entries
    }
    assert registered_vocabularies["llm.provider.name"] == llm_provider_names.members
    assert (
        registered_failures["llm.provider_resolution.failure"]
        == llm_provider_resolution_failures.codes
    )


def test_FAILURE_PRESERVED__llm_provider_resolution_keeps_family_member() -> None:
    failure = llm_provider_resolution_failures.fail(
        _assigned_string("LLM_PROVIDER_NOT_REGISTERED"),
        "provider is absent",
    )
    assert llm_provider_resolution_failures.matches(failure)
