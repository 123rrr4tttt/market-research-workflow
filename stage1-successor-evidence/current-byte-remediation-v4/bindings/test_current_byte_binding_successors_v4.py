# ruff: noqa: E501, TRY003
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = _load_module(
    "build_current_byte_binding_successors_v4_test",
    HERE / "build_current_byte_binding_successors_v4.py",
)
CHECKER = _load_module(
    "check_current_byte_binding_successors_v4_test",
    HERE / "check_current_byte_binding_successors_v4.py",
)


def _copy(root: Path, relative: Path) -> None:
    source = BUILDER.REPOSITORY_ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _temporary_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    _copy(root, BUILDER.V3_REGISTRY_REL)
    for relative in BUILDER.STATIC_RELS:
        _copy(root, relative)
    return root


def _load_documents(root: Path) -> tuple[dict, dict, dict]:
    return (
        BUILDER.load_object(root / BUILDER.V3_REGISTRY_REL),
        BUILDER.load_object(root / BUILDER.REGISTRY_REL),
        BUILDER.load_object(root / BUILDER.MANIFEST_REL),
    )


def _refresh_digest(document: dict) -> dict:
    body = {key: value for key, value in document.items() if key != "content_digest"}
    document["content_digest"] = BUILDER.sha256(BUILDER.canonical_json(body))
    return document


def test_current_v4_bundle_passes() -> None:
    assert CHECKER.validate(BUILDER.REPOSITORY_ROOT) == {
        "status": "PASS",
        "inherited_successor_count": 22,
        "added_successor_count": 0,
        "new_snapshot_count": 0,
        "authority_ceiling": BUILDER.AUTHORITY_CEILING,
    }


def test_v4_builder_inherits_all_v3_rows_without_delta(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)

    assert registry["successors"] == v3["successors"]
    assert BUILDER.canonical_json(registry["successors"]) == BUILDER.canonical_json(v3["successors"])
    assert registry["inherited_successor_count"] == 22
    assert registry["added_successor_count"] == 0
    assert registry["new_snapshot_count"] == 0
    assert manifest["new_snapshot_count"] == 0
    assert not (root / BUILDER.BINDINGS_REL / "snapshots").exists()


def test_v4_builder_and_checker_do_not_write_v3(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    predecessor = root / BUILDER.V3_REGISTRY_REL
    before = (predecessor.read_bytes(), predecessor.stat().st_mtime_ns)

    BUILDER.write_create_only(root)
    CHECKER.validate(root)
    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    assert (predecessor.read_bytes(), predecessor.stat().st_mtime_ns) == before


@pytest.mark.parametrize("target_rel", [BUILDER.REGISTRY_REL, BUILDER.MANIFEST_REL])
def test_v4_builder_preflights_all_targets_without_partial_publication(
    tmp_path: Path,
    target_rel: Path,
) -> None:
    root = _temporary_root(tmp_path)
    target = root / target_rel
    target.write_bytes(b"preexisting bytes")

    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    assert target.read_bytes() == b"preexisting bytes"
    other = BUILDER.MANIFEST_REL if target_rel == BUILDER.REGISTRY_REL else BUILDER.REGISTRY_REL
    assert not (root / other).exists()


def test_v4_builder_rejects_dangling_symlink_target(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    target = root / BUILDER.MANIFEST_REL
    target.symlink_to(target.parent / "missing-target")

    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    assert target.is_symlink()
    assert not (root / BUILDER.REGISTRY_REL).exists()


def test_v4_builder_rolls_back_interrupted_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _temporary_root(tmp_path)
    original = BUILDER._write_new_file
    calls = 0

    def fail_second(path: Path, payload: bytes):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected failure")
        return original(path, payload)

    monkeypatch.setattr(BUILDER, "_write_new_file", fail_second)
    with pytest.raises(OSError, match="injected failure"):
        BUILDER.write_create_only(root)

    assert not (root / BUILDER.REGISTRY_REL).exists()
    assert not (root / BUILDER.MANIFEST_REL).exists()


def test_v4_builder_rejects_v3_byte_drift(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    predecessor = root / BUILDER.V3_REGISTRY_REL
    predecessor.write_bytes(predecessor.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="v3 predecessor registry byte drift"):
        BUILDER.build_registry(root)


def test_v4_checker_rejects_inherited_row_mutation(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)
    registry["successors"][0]["successor_sha256"] = "0" * 64
    _refresh_digest(registry)

    with pytest.raises(ValueError, match="inherited successor row mutation"):
        CHECKER.validate_document_semantics(root, v3=v3, registry=registry, manifest=manifest)


@pytest.mark.parametrize("field", ["added_successor_count", "new_snapshot_count"])
def test_v4_checker_rejects_false_zero_delta_counts(tmp_path: Path, field: str) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)
    registry[field] = 1
    _refresh_digest(registry)

    with pytest.raises(ValueError, match="zero-delta counts drift"):
        CHECKER.validate_document_semantics(root, v3=v3, registry=registry, manifest=manifest)


@pytest.mark.parametrize("document_name", ["registry", "manifest"])
def test_v4_checker_rejects_new_authority(tmp_path: Path, document_name: str) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)
    document = registry if document_name == "registry" else manifest
    document["authority"]["production_release"] = True
    _refresh_digest(document)

    with pytest.raises(ValueError, match="expands authority"):
        CHECKER.validate_document_semantics(root, v3=v3, registry=registry, manifest=manifest)


def test_v4_checker_rejects_unexpected_snapshot_file(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    snapshot = root / BUILDER.BINDINGS_REL / "snapshots" / ("0" * 64)
    snapshot.parent.mkdir()
    snapshot.write_bytes(b"")

    with pytest.raises(ValueError, match="missing or unexpected files"):
        CHECKER.validate(root)


def test_v4_checker_rejects_extension_drift(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)
    registry["extends"]["mutation"] = True
    _refresh_digest(registry)

    with pytest.raises(ValueError, match="predecessor extension drift"):
        CHECKER.validate_document_semantics(root, v3=v3, registry=registry, manifest=manifest)


def test_v4_checker_rejects_manifest_snapshot_claim(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v3, registry, manifest = _load_documents(root)
    manifest["new_snapshot_count"] = 1
    _refresh_digest(manifest)

    with pytest.raises(ValueError, match="falsely declares"):
        CHECKER.validate_document_semantics(root, v3=v3, registry=registry, manifest=manifest)
