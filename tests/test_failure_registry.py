from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from functorial_kit import FailureFamily
from functorial_kit.arch.scan import SourceFile, collect_declarations

import mrw_functorial_kit.core as core

ROOT = Path(__file__).resolve().parents[1]
FAILURE_SEMANTICS_MODULES = (
    "mrw_functorial_kit.core.application_failure_semantics",
    "mrw_functorial_kit.core.agent_service_semantics",
    "mrw_functorial_kit.core.provider_port_failures",
    "mrw_functorial_kit.core.service_failure_semantics",
    "mrw_functorial_kit.core.capability_contract_failure_semantics",
    "mrw_functorial_kit.core.source_and_capability_failure_semantics",
    "mrw_functorial_kit.core.workflow_research_failure_semantics",
)


def _modules() -> tuple[ModuleType, ...]:
    return tuple(importlib.import_module(name) for name in FAILURE_SEMANTICS_MODULES)


def _declared_families() -> dict[str, tuple[str, ...]]:
    module_paths: list[str] = []
    for module in _modules():
        module_path = module.__file__
        assert module_path is not None
        module_paths.append(module_path)
    sources = tuple(
        SourceFile(module.__name__, Path(module_path).read_text(encoding="utf-8"))
        for module, module_path in zip(_modules(), module_paths, strict=True)
    )
    return dict(collect_declarations(sources).failures)


def _families() -> tuple[tuple[str, FailureFamily], ...]:
    declared = _declared_families()
    families: list[tuple[str, FailureFamily]] = []
    for module in _modules():
        for symbol in module.__all__:
            value = getattr(module, symbol)
            # Explicit historical readers expose metadata without declaring a
            # current producer. Match only the actual native declarations.
            if isinstance(value, FailureFamily) and value.name in declared:
                families.append((symbol, value))
    return tuple(families)


def test_INVARIANT__failure_families_have_one_canonical_owner() -> None:
    families = _families()
    names = [family.name for _, family in families]

    assert set(names) == set(_declared_families())
    assert len(names) == len(set(names))
    assert {family.name for _, family in families if family.name == "request_identity.failure"} == {
        "request_identity.failure"
    }


def test_INVARIANT__failure_registry_matches_declared_families() -> None:
    entries = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))["entries"]
    names = [entry["name"] for entry in entries]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}

    assert len(names) == len(set(names))
    for _, family in _families():
        assert sorted(registered[family.name]) == sorted(family.codes)


def test_INVARIANT__failure_families_are_exported_from_core() -> None:
    for symbol, family in _families():
        assert symbol in core.__all__
        assert getattr(core, symbol) is family
