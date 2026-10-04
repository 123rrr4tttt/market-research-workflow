from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/materialize_functorial_kit_consumer_gate.py"
MANIFEST = ROOT / "tools/functorial-kit/consumer-gate.manifest.json"
PATCH = ROOT / "tools/functorial-kit/consumer-gate.patch"
SPEC = importlib.util.spec_from_file_location("materialize_functorial_kit_consumer_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
materializer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = materializer
SPEC.loader.exec_module(materializer)


def _historical_pyproject_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    root = tmp_path / "consumer-gate-history"
    root.mkdir()
    pyproject = root / "pyproject.toml"
    completed = subprocess.run(
        ("git", "-C", str(ROOT), "show", "HEAD:pyproject.toml"),
        check=True,
        capture_output=True,
    )
    pyproject.write_bytes(completed.stdout)
    tool_root = root / "tools" / "functorial-kit"
    tool_root.mkdir(parents=True)
    shutil.copy2(MANIFEST, tool_root / MANIFEST.name)
    shutil.copy2(PATCH, tool_root / PATCH.name)
    monkeypatch.setattr(materializer, "ROOT", root)
    return root


def test_INVARIANT__manifest_pins_exact_base_patch_and_runtime_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    historical_root = _historical_pyproject_root(tmp_path, monkeypatch)
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dependency = payload["runtime_identity"]["pyproject_runtime_dependency"]

    assert materializer.load_manifest(MANIFEST) == payload
    assert payload["base"]["git_commit"] == "785ff25e201c9eae84c862e68e786bc975e7a800"
    assert materializer._sha256(PATCH) == payload["patch"]["sha256"]
    assert dependency in (historical_root / "pyproject.toml").read_text(encoding="utf-8")
    assert payload["runtime_identity"]["pyproject_runtime_pin_modified"] is False
    assert payload["role"] == "test_tool_only"


def test_INVARIANT__authority_ceiling_is_all_false() -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert materializer._all_authority_false(payload["authority"]) is True


def test_INVARIANT__patch_contains_only_consumer_gate_targets() -> None:
    targets = materializer._patch_targets(PATCH.read_text(encoding="utf-8"))

    assert set(targets) == {
        "python/functorial_kit/arch/gates.py",
        "python/functorial_kit/arch/scan.py",
        "python/tests/test_arch.py",
    }


def test_NEGATIVE__patch_path_escape_is_rejected() -> None:
    patch = "+++ b/python/../../escape.py\n"

    with pytest.raises(materializer.MaterializationError, match="path escape"):
        materializer._patch_targets(patch)


def test_NEGATIVE__existing_output_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "already-dirty"
    output.mkdir()

    with pytest.raises(materializer.MaterializationError, match="must not already exist"):
        materializer.materialize(tmp_path, output)


def test_NEGATIVE__wrong_commit_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _historical_pyproject_root(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ("init",),
        ("config", "user.email", "test@example.invalid"),
        ("config", "user.name", "Test"),
    ):
        subprocess.run(("git", "-C", str(repo), *args), check=True, capture_output=True, text=True)
    (repo / "tracked.txt").write_text("unrelated\n", encoding="utf-8")
    subprocess.run(("git", "-C", str(repo), "add", "tracked.txt"), check=True, capture_output=True)
    subprocess.run(("git", "-C", str(repo), "commit", "-m", "unrelated"), check=True, capture_output=True)
    output = tmp_path / "output"

    with pytest.raises(materializer.MaterializationError, match="wrong base commit|git rev-parse"):
        materializer.materialize(repo, output)
    assert not output.exists()
