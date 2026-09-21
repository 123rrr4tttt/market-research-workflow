from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

from functorial_kit import FailureFamily

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


def _families() -> tuple[tuple[str, FailureFamily], ...]:
    families: list[tuple[str, FailureFamily]] = []
    for module in _modules():
        for symbol in module.__all__:
            value = getattr(module, symbol)
            if isinstance(value, FailureFamily):
                families.append((symbol, value))
    return tuple(families)


def test_INVARIANT__p0_failure_families_have_one_canonical_owner() -> None:
    families = _families()
    names = [family.name for _, family in families]

    assert len(families) == 63
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
        assert registered[family.name] == family.codes


def test_INVARIANT__p0_failure_families_are_exported_from_core() -> None:
    for symbol, family in _families():
        assert symbol in core.__all__
        assert getattr(core, symbol) is family
