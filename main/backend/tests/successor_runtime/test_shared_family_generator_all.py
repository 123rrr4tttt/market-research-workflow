"""Shared family generator parity for every migrated family."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    fragment_bytes,
)

_EVIDENCE = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)

_FAMILIES = {
    "C2": ("c2_p3", "generate_successor_p3_c2_fragment.py", "p3-fragments/C2.json"),
    "C3": ("c3_p3", "generate_successor_p3_c3_fragment.py", "p3-fragments/C3.json"),
    "C4": ("c4_p3", "generate_successor_p3_c4_fragment.py", "p3-fragments/C4.json"),
    "C5": ("c5_p3", "generate_successor_p3_c5_fragment.py", "p3-fragments/C5.json"),
    "C6": ("c6_p3", "generate_successor_p3_c6_fragment.py", "p3-fragments/C6.json"),
    "C7": ("c7_p4", "generate_successor_p4_c7_fragment.py", "p4-fragments/C7.json"),
    "C8": ("c8_p4", "generate_successor_p4_c8_fragment.py", "p4-fragments/C8.json"),
    "C9": ("c9_p4", "generate_successor_p4_c9_fragment.py", "p4-fragments/C9.json"),
}


def _load_config(family: str):
    module_name, _, _ = _FAMILIES[family]
    module = __import__(
        f"app.successor_runtime.specification.{module_name}", fromlist=["CONFIG"]
    )
    return module.CONFIG


def _load_legacy(family: str):
    _, script, _ = _FAMILIES[family]
    spec = importlib.util.spec_from_file_location(
        f"legacy_{family.lower()}", _BACKEND_ROOT / "scripts" / script
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _legacy_bytes(family: str, module) -> bytes:
    first = module.build_fragment()
    body = {key: value for key, value in first.items() if key != "content_digest"}
    if family == "C3":
        digest = module._canonical_digest(body)
        first["content_digest"] = digest
        return module.fragment_bytes(first)
    digest = module.content_digest(body)
    first["content_digest"] = digest
    return module._canonical_json(first).encode("utf-8") + b"\n"


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_shared_output_matches_legacy_and_disk_bytes(family: str) -> None:
    config = _load_config(family)
    legacy = _load_legacy(family)
    shared = build_fragment(config, _REPOSITORY_ROOT)
    shared_bytes = fragment_bytes(config, shared)
    assert shared_bytes == _legacy_bytes(family, legacy)
    _, _, fragment_rel = _FAMILIES[family]
    disk = (_EVIDENCE / fragment_rel).read_bytes()
    assert shared_bytes == disk


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_shared_fragment_is_deterministic_and_authority_false(family: str) -> None:
    config = _load_config(family)
    first = build_fragment(config, _REPOSITORY_ROOT)
    second = build_fragment(config, _REPOSITORY_ROOT)
    assert fragment_bytes(config, first) == fragment_bytes(config, second)
    assert first["content_digest"] == second["content_digest"]
    assert all(not value for value in first["authority"].values())
    assert first["open_findings"]
    for label in ("source_bindings", "implementation_bindings", "test_bindings"):
        for binding in first[label]:
            assert len(binding["sha256"]) == 64
            assert binding["bytes"] > 0


@pytest.mark.parametrize("family", sorted(_FAMILIES))
def test_shared_cli_check_is_read_only_match(family: str) -> None:
    _, _, fragment_rel = _FAMILIES[family]
    path = _EVIDENCE / fragment_rel
    before_stat = path.stat()
    before_bytes = path.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(_BACKEND_ROOT / "scripts/generate_family_fragment_shared.py"),
            "--family",
            family,
            "--check",
        ],
        cwd=_BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "MATCH" in result.stdout
    assert path.read_bytes() == before_bytes
    assert path.stat().st_mtime_ns == before_stat.st_mtime_ns


def test_family_fragment_json_is_valid_and_shares_schema() -> None:
    for family, (_, _, fragment_rel) in _FAMILIES.items():
        payload = json.loads((_EVIDENCE / fragment_rel).read_text(encoding="utf-8"))
        assert payload["family"] == family
        assert payload["schema"].startswith("mrw.functorial_successor.")
        assert len(payload["content_digest"]) == 64
