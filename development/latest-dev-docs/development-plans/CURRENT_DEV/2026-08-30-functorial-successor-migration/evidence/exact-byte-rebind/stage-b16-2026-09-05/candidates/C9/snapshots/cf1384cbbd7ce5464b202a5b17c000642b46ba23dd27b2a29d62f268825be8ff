"""P4 C9 fragment stability: mutable 03/04 isolation and exact-input drift."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p4_c9_fragment.py"
_MUTABLE_MARKERS = (
    "03_functorial-successor-migration-development-progress.md",
    "04_functorial-successor-capability-ledger.json",
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p4_c9_fragment",
        _GENERATOR,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _digest(module, fragment: dict[str, object]) -> str:
    return module.content_digest(
        {key: value for key, value in fragment.items() if key != "content_digest"}
    )


def test_mutable_03_04_files_are_not_bound_or_read(monkeypatch) -> None:
    module = _load_generator()
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(self, *args, **kwargs):
        path = str(self)
        if any(marker in path for marker in _MUTABLE_MARKERS):
            raise AssertionError(f"fragment must not read mutable file: {path}")
        return original_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    fragment = module.build_fragment()
    bound_paths = [
        binding["path"]
        for binding in (
            *fragment["source_bindings"],
            *fragment["implementation_bindings"],
            *fragment["test_bindings"],
        )
    ]
    assert not any(
        marker in path for marker in _MUTABLE_MARKERS for path in bound_paths
    )
    assert fragment["p4_status"] == "P4_NOT_STARTED"


@pytest.mark.parametrize(
    "marker",
    (
        "01_functorial-successor-migration-development-contract.md",
        "P1FunctorizationEligibility.v1.json",
        "runtime/facade_contracts.py",
    ),
)
def test_frozen_p1_and_implementation_changes_change_fragment(
    monkeypatch,
    marker: str,
) -> None:
    module = _load_generator()
    baseline = _digest(module, module.build_fragment())
    original_read_bytes = Path.read_bytes

    def changed_read_bytes(self, *args, **kwargs):
        data = original_read_bytes(self, *args, **kwargs)
        if str(self).endswith(marker):
            return data + b"#drift"
        return data

    monkeypatch.setattr(Path, "read_bytes", changed_read_bytes)
    changed = _digest(module, module.build_fragment())
    assert changed != baseline


def test_implementation_binding_missing_fails_closed(monkeypatch) -> None:
    module = _load_generator()
    original_exists = Path.exists

    def missing_exists(self):
        if str(self).endswith("runtime/facade_contracts.py"):
            return False
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", missing_exists)
    with pytest.raises(FileNotFoundError):
        module.build_fragment()
