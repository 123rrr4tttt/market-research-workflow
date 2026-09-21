from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

BUILDER = load_module("semantic_builder_tests", HERE / "build_semantic_binding_successors_v3.py")
CHECKER = load_module("semantic_checker_tests", HERE / "check_semantic_binding_successors_v3.py")


def _copy(root: Path, relative: Path | str) -> None:
    source = ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _temporary_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    _copy(root, BUILDER.I1_FRAGMENT_REL)
    for repair in BUILDER.SEMANTIC_REPAIRS:
        _copy(root, repair["source_path"])
    fragment = json.loads((ROOT / BUILDER.I1_FRAGMENT_REL).read_text())
    for binding in fragment["bindings"]:
        if any(binding["path"] == repair["source_path"] for repair in BUILDER.SEMANTIC_REPAIRS):
            _copy(root, binding["spec_path"])
    for relative in BUILDER.STATIC_FILES:
        _copy(root, relative)
    return root


def test_positive_build_and_readonly_check(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    assert CHECKER.validate(root) == {
        "status": "PASS",
        "source_count": 6,
        "successor_count": 8,
        "authority_ceiling": BUILDER.AUTHORITY_CEILING,
    }
    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)


@pytest.mark.parametrize("repair_index", range(len(BUILDER.SEMANTIC_REPAIRS)))
def test_rejects_semantic_source_drift(tmp_path: Path, repair_index: int) -> None:
    root = _temporary_root(tmp_path)
    path = root / BUILDER.SEMANTIC_REPAIRS[repair_index]["source_path"]
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="semantic current source drift"):
        BUILDER.expected_documents(root)
