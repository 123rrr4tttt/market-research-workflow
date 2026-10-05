"""Frozen C4/P3 fragment byte, digest and field validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.successor_runtime.capabilities.checksum import content_digest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c4_fragment.py"
_FROZEN_FILE_SHA256 = (
    "058b02345b9d67c1e7ff51006afb4c28e2c8ce4dadf7a505fac6bbac781bd188"
)
_FROZEN_CONTENT_DIGEST = (
    "a8c6ecaf1a3cada4729036b7ff12ee84fbf0353291f85f82f3b5e50dad0160ad"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c4_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_frozen_fragment_bytes_digest_and_identity_are_exact() -> None:
    data = _REPOSITORY_ROOT.joinpath(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C4.json"
    ).read_bytes()
    fragment = json.loads(data)
    body = {key: value for key, value in fragment.items() if key != "content_digest"}

    assert hashlib.sha256(data).hexdigest() == _FROZEN_FILE_SHA256
    assert fragment["content_digest"] == _FROZEN_CONTENT_DIGEST
    assert content_digest(body) == _FROZEN_CONTENT_DIGEST
    assert fragment["schema"] == "mrw.functorial_successor.p3_fragment.v1"
    assert fragment["family"] == "C4"
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C4.1",
        "C4.2",
        "C4.3",
    ]
    assert all(value is False for value in fragment["authority"].values())


def test_frozen_loader_is_deterministic_and_self_checked() -> None:
    module = _load_generator()
    first = module.build_fragment()
    second = module.build_fragment()

    assert first == second
    assert module._canonical_json(first) == module._canonical_json(second)
    module._self_test(first)


def test_cli_check_matches_frozen_bytes_without_write(tmp_path, monkeypatch) -> None:
    module = _load_generator()
    canonical = module.FRAGMENT_PATH
    original = canonical.read_bytes()
    target = tmp_path / "C4.json"
    target.write_bytes(original)
    monkeypatch.setattr(module, "FRAGMENT_PATH", target)

    assert module.main(["--check"]) == 0
    assert target.read_bytes() == original
    assert canonical.read_bytes() == original


def test_cli_check_drift_exits_one_without_write(tmp_path, monkeypatch) -> None:
    module = _load_generator()
    original = module.FRAGMENT_PATH.read_bytes()
    drifted = original.replace(b'"family":"C4"', b'"family":"C4X"')
    assert drifted != original
    target = tmp_path / "C4.drifted.json"
    target.write_bytes(drifted)
    monkeypatch.setattr(module, "FRAGMENT_PATH", target)

    assert module.main(["--check"]) == 1
    assert target.read_bytes() == drifted


def test_cli_unknown_argument_exits_two() -> None:
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--definitely-unknown"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
