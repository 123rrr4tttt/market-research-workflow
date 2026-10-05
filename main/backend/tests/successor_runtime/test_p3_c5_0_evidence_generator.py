"""Frozen C5/P3 fragment, adjudication and CLI byte validation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification import c5_p3

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_REPOSITORY_ROOT = _BACKEND_ROOT.parents[1]
_EVIDENCE_ROOT = _REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
_GENERATOR = _BACKEND_ROOT / "scripts/generate_successor_p3_c5_fragment.py"
_FROZEN_FILE_SHA256 = (
    "0e1da888f13adf637774612be90ae367633f565774585b6ad18ace045cdf5231"
)
_FROZEN_CONTENT_DIGEST = (
    "1dedd393e46037ed8cfb66aa43ef32255963da63d98c7f908a2ddee6db0e4c7d"
)


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_successor_p3_c5_fragment", _GENERATOR
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_frozen_fragment_bytes_digest_and_identity_are_exact() -> None:
    data = (_EVIDENCE_ROOT / "p3-fragments/C5.json").read_bytes()
    fragment = json.loads(data)
    body = {key: value for key, value in fragment.items() if key != "content_digest"}

    assert hashlib.sha256(data).hexdigest() == _FROZEN_FILE_SHA256
    assert fragment["content_digest"] == _FROZEN_CONTENT_DIGEST
    assert content_digest(body) == _FROZEN_CONTENT_DIGEST
    assert fragment["family"] == "C5"
    assert [cell["cell_id"] for cell in fragment["cells"]] == [
        "C5.1",
        "C5.2",
        "C5.3",
        "C5.4",
    ]
    assert all(value is False for value in fragment["authority"].values())
    assert {item["id"] for item in fragment["resolved_findings"]} == {
        "C5_4_FROZEN_LOCATOR_CLARIFICATION_REQUIRED"
    }


def test_frozen_adjudication_is_byte_and_content_bound() -> None:
    module = _load_generator()
    data = module.ADJUDICATION_PATH.read_bytes()
    artifact = json.loads(data)
    body = {key: value for key, value in artifact.items() if key != "content_digest"}

    assert hashlib.sha256(data).hexdigest() == c5_p3.ADJUDICATION_FILE_SHA256
    assert artifact["content_digest"] == c5_p3.ADJUDICATION_CONTENT_DIGEST
    assert content_digest(body) == c5_p3.ADJUDICATION_CONTENT_DIGEST
    assert artifact["normative_donor_locators"] == list(
        c5_p3.NORMATIVE_DONOR_LOCATORS
    )
    assert artifact["supplementary_read_only_evidence"] == list(
        c5_p3.SUPPLEMENTARY_READ_ONLY_EVIDENCE
    )
    assert artifact["path_observations"]["source_checkout_dirty"] == {
        "path": c5_p3.PROHIBITED_DIRTY_SOURCE,
        "git_status": "UNTRACKED_EXCLUDED",
        "sha256": c5_p3.PROHIBITED_DIRTY_SOURCE_SHA256,
        "adopted": False,
    }


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
    target = tmp_path / "C5.json"
    target.write_bytes(original)
    monkeypatch.setattr(module, "FRAGMENT_PATH", target)

    assert module.main(["--check"]) == 0
    assert target.read_bytes() == original
    assert canonical.read_bytes() == original


def test_cli_check_drift_exits_one_without_write(tmp_path, monkeypatch) -> None:
    module = _load_generator()
    original = module.FRAGMENT_PATH.read_bytes()
    drifted = original.replace(b'"family":"C5"', b'"family":"C5X"')
    assert drifted != original
    target = tmp_path / "C5.drifted.json"
    target.write_bytes(drifted)
    monkeypatch.setattr(module, "FRAGMENT_PATH", target)

    assert module.main(["--check"]) == 1
    assert target.read_bytes() == drifted


def test_cli_unknown_argument_returns_two_without_write() -> None:
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--unknown-option"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
