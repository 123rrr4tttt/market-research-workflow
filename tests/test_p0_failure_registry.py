from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from functorial_kit import FailureFamily
from functorial_kit.arch.scan import SourceFile, collect_declarations

import mrw_functorial_kit.core as core

ROOT = Path(__file__).resolve().parents[1]
P0_MODULE_NAMES = (
    "mrw_functorial_kit.core.application_failure_semantics",
    "mrw_functorial_kit.core.agent_service_semantics",
    "mrw_functorial_kit.core.provider_port_failures",
    "mrw_functorial_kit.core.w04_service_semantics",
    "mrw_functorial_kit.core.w05_capability_semantics",
    "mrw_functorial_kit.core.w06_semantics",
    "mrw_functorial_kit.core.w07_semantics",
)


def _modules() -> tuple[ModuleType, ...]:
    return tuple(importlib.import_module(name) for name in P0_MODULE_NAMES)


def _declared_families() -> dict[str, tuple[str, ...]]:
    sources = tuple(
        SourceFile(module.__name__, Path(module.__file__).read_text(encoding="utf-8"))
        for module in _modules()
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


def test_INVARIANT__p0_failure_families_have_one_canonical_owner() -> None:
    families = _families()
    names = [family.name for _, family in families]

    assert set(names) == set(_declared_families())
    assert len(names) == len(set(names))
    assert {family.name for _, family in families if family.name == "request_identity.failure"} == {
        "request_identity.failure"
    }


def test_INVARIANT__p0_failure_registry_matches_declared_families() -> None:
    entries = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))["entries"]
    names = [entry["name"] for entry in entries]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}

    assert len(names) == len(set(names))
    for _, family in _families():
        assert sorted(registered[family.name]) == sorted(family.codes)


def test_INVARIANT__p0_failure_families_are_exported_from_core() -> None:
    for symbol, family in _families():
        assert symbol in core.__all__
        assert getattr(core, symbol) is family
