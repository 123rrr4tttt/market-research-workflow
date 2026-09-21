from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
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


CHECKER = load_module(
    "check_current_byte_binding_successors_v3_tests",
    HERE / "check_current_byte_binding_successors_v3.py",
)
BUILDER = CHECKER.BUILDER


def _copy(root: Path, relative: Path | str) -> None:
    source = ROOT / relative
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert target.read_bytes() == source.read_bytes()
        return
    shutil.copy2(source, target)


def _temporary_root(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    for relative in BUILDER.V2_MEMBER_HASHES:
        _copy(root, relative)
    for relative in (
        BUILDER.RUN_LOOP_PATH,
        BUILDER.PROVIDER_TEST_PATH,
        BUILDER.PREDECESSOR_SNAPSHOT_REL,
        *(item["candidate_path"] for item in BUILDER.CANDIDATE_DECLARATIONS),
        *(item["fragment_path"] for item in BUILDER.FROZEN_CELL_SOURCES),
        *(item["spec_path"] for item in BUILDER.FROZEN_CELL_SOURCES),
        *(item["candidate_path"] for item in BUILDER.PROVIDER_TEST_CANDIDATE_DECLARATIONS),
        *(
            Path(item["candidate_path"]).parent
            / "snapshots"
            / item["predecessor_sha256"]
            for item in BUILDER.PROVIDER_TEST_CANDIDATE_DECLARATIONS
        ),
        BUILDER.BINDINGS_REL / "build_current_byte_binding_successors_v3.py",
        BUILDER.BINDINGS_REL / "check_current_byte_binding_successors_v3.py",
        BUILDER.BINDINGS_REL / "test_current_byte_binding_successors_v3.py",
    ):
        _copy(root, relative)
    for repair in BUILDER.CONTRACT_REPAIRS:
        _copy(root, repair["source_path"])
        for declaration in repair["declarations"]:
            _copy(root, declaration["candidate_path"])
            _copy(root, declaration["snapshot_path"])
        for spec in repair.get("spec_bindings", []):
            _copy(root, spec["spec_path"])
    return root


def _load_generated(root: Path) -> tuple[dict, dict, dict]:
    return (
        json.loads((root / BUILDER.V2_REGISTRY_REL).read_text()),
        json.loads((root / BUILDER.REGISTRY_REL).read_text()),
        json.loads((root / BUILDER.MANIFEST_REL).read_text()),
    )


def _refresh_digest(document: dict) -> dict:
    body = {key: value for key, value in document.items() if key != "content_digest"}
    document["content_digest"] = BUILDER.sha256(BUILDER.canonical_json(body))
    return document


def test_v3_positive_has_all_shared_rows_and_exact_declarations(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)

    assert CHECKER.validate(root) == {
        "status": "PASS",
        "source_count": 16,
        "successor_count": 22,
        "direct_candidate_declaration_count": 22,
        "run_loop_direct_candidate_declaration_count": 3,
        "provider_test_direct_candidate_declaration_count": 7,
        "authority_ceiling": BUILDER.AUTHORITY_CEILING,
    }
    v2, registry, _manifest = _load_generated(root)
    assert registry["successors"][:11] == v2["successors"]
    assert registry["successors"][11:] == [
        BUILDER.shared_run_loop_successor(),
        BUILDER.shared_provider_test_successor(),
        *BUILDER.contract_repair_rows(root),
    ]
    assert registry["successors"][11]["direct_candidate_declarations"] == [
        dict(item) for item in BUILDER.CANDIDATE_DECLARATIONS
    ]
    assert registry["successors"][11]["predecessor_declarations"] == [
        {
            "artifact": item["candidate_path"],
            "artifact_sha256": item["candidate_sha256"],
            "json_pointer": item["json_pointer"],
            "hash_field": "file_sha256",
            "bound_sha256": item["predecessor_sha256"],
        }
        for item in BUILDER.CANDIDATE_DECLARATIONS
    ]
    assert registry["successors"][12]["direct_candidate_declarations"] == [
        dict(item) for item in BUILDER.PROVIDER_TEST_CANDIDATE_DECLARATIONS
    ]
    assert registry["successors"][12]["predecessor_declarations"] == (
        BUILDER.provider_test_predecessor_declarations()
    )
    assert registry["successors"][12]["frozen_source_snapshots"] == (
        BUILDER.provider_test_frozen_source_snapshots()
    )


def test_v3_builder_and_checker_preserve_every_v2_member(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    before = {
        relative: ((root / relative).read_bytes(), (root / relative).stat().st_mtime_ns)
        for relative in BUILDER.V2_MEMBER_HASHES
    }

    BUILDER.write_create_only(root)
    CHECKER.validate(root)
    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    after = {
        relative: ((root / relative).read_bytes(), (root / relative).stat().st_mtime_ns)
        for relative in BUILDER.V2_MEMBER_HASHES
    }
    assert after == before


def test_v3_builder_rejects_existing_target_without_overwrite(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    registry_path = root / BUILDER.REGISTRY_REL
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    original = b"preexisting bytes must remain"
    registry_path.write_bytes(original)

    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)
    assert registry_path.read_bytes() == original
    assert not (root / BUILDER.MANIFEST_REL).exists()
    assert not (root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.SUCCESSOR_SHA256).exists()
    assert not (
        root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.PROVIDER_TEST_SUCCESSOR_SHA256
    ).exists()


def test_v3_builder_preflights_later_target_without_partial_creation(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    manifest_path = root / BUILDER.MANIFEST_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(b"already present")

    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    assert manifest_path.read_bytes() == b"already present"
    assert not (root / BUILDER.REGISTRY_REL).exists()
    assert not (root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.SUCCESSOR_SHA256).exists()
    assert not (
        root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.PROVIDER_TEST_SUCCESSOR_SHA256
    ).exists()


def test_v3_builder_rejects_dangling_symlink_target(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    snapshot = root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.SUCCESSOR_SHA256
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.symlink_to(snapshot.parent / "missing-target")

    with pytest.raises(FileExistsError, match="create-only target exists"):
        BUILDER.write_create_only(root)

    assert snapshot.is_symlink()
    assert not (root / BUILDER.REGISTRY_REL).exists()
    assert not (root / BUILDER.MANIFEST_REL).exists()
    assert not (
        root / BUILDER.BINDINGS_REL / "snapshots" / BUILDER.PROVIDER_TEST_SUCCESSOR_SHA256
    ).exists()


def test_v3_rejects_duplicate_shared_row(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v2, registry, manifest = _load_generated(root)
    registry["successors"].append(deepcopy(registry["successors"][-1]))
    _refresh_digest(registry)

    with pytest.raises(ValueError, match="successor row duplicated"):
        CHECKER.validate_document_semantics(
            root,
            v2=v2,
            registry=registry,
            manifest=manifest,
        )


def test_v3_rejects_run_loop_source_hash_drift(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    source = root / BUILDER.RUN_LOOP_PATH
    source.write_bytes(source.read_bytes() + b"# drift\n")

    with pytest.raises(ValueError, match="current source hash mismatch"):
        BUILDER.validate_inputs(root)


def test_v3_rejects_provider_test_source_hash_drift(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    source = root / BUILDER.PROVIDER_TEST_PATH
    source.write_bytes(source.read_bytes() + b"# drift\n")

    with pytest.raises(ValueError, match="provider test current source hash mismatch"):
        BUILDER.validate_inputs(root)


def test_v3_rejects_candidate_declaration_pointer_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _temporary_root(tmp_path)
    declarations = [dict(item) for item in BUILDER.CANDIDATE_DECLARATIONS]
    candidate_path = root / declarations[0]["candidate_path"]
    candidate = json.loads(candidate_path.read_text())
    candidate["sources"][10]["snapshot_path"] = "snapshots/not-the-frozen-predecessor"
    os.chmod(candidate_path, 0o644)
    candidate_path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    declarations[0]["candidate_sha256"] = BUILDER.sha256(candidate_path.read_bytes())
    monkeypatch.setattr(BUILDER, "CANDIDATE_DECLARATIONS", tuple(declarations))

    with pytest.raises(ValueError, match="candidate declaration pointer drift: C5"):
        BUILDER.validate_inputs(root)


@pytest.mark.parametrize("declaration_index", range(7))
def test_v3_rejects_every_provider_test_candidate_pointer_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    declaration_index: int,
) -> None:
    root = _temporary_root(tmp_path)
    declarations = [dict(item) for item in BUILDER.PROVIDER_TEST_CANDIDATE_DECLARATIONS]
    declaration = declarations[declaration_index]
    candidate_path = root / declaration["candidate_path"]
    candidate = json.loads(candidate_path.read_text())
    pointer_index = int(declaration["json_pointer"].rsplit("/", 1)[1])
    candidate["tests"][pointer_index]["snapshot_path"] = "snapshots/not-the-frozen-predecessor"
    os.chmod(candidate_path, 0o644)
    candidate_path.write_text(json.dumps(candidate, sort_keys=True), encoding="utf-8")
    declaration["candidate_sha256"] = BUILDER.sha256(candidate_path.read_bytes())
    monkeypatch.setattr(BUILDER, "PROVIDER_TEST_CANDIDATE_DECLARATIONS", tuple(declarations))

    with pytest.raises(
        ValueError,
        match=f"provider test candidate declaration pointer drift: {declaration['stage']}",
    ):
        BUILDER.validate_inputs(root)


def test_v3_rejects_provider_shared_declaration_tamper(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v2, registry, manifest = _load_generated(root)
    registry["successors"][12]["direct_candidate_declarations"][0]["json_pointer"] = "/tests/4"
    _refresh_digest(registry)

    with pytest.raises(ValueError, match="exact shared successor identities drift"):
        CHECKER.validate_document_semantics(
            root,
            v2=v2,
            registry=registry,
            manifest=manifest,
        )


@pytest.mark.parametrize("document_name", ["registry", "manifest"])
def test_v3_rejects_authority_tamper(tmp_path: Path, document_name: str) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v2, registry, manifest = _load_generated(root)
    document = registry if document_name == "registry" else manifest
    document["authoritative"] = True
    _refresh_digest(document)

    with pytest.raises(ValueError, match="must remain non-authoritative"):
        CHECKER.validate_document_semantics(
            root,
            v2=v2,
            registry=registry,
            manifest=manifest,
        )


def test_v3_rejects_snapshot_tamper(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    _v2, registry, _manifest = _load_generated(root)
    snapshot = root / BUILDER.BINDINGS_REL / registry["successors"][11]["snapshot_path"]
    os.chmod(snapshot, 0o644)
    snapshot.write_bytes(snapshot.read_bytes() + b"# drift\n")

    with pytest.raises(ValueError, match="run_loop snapshot drift"):
        CHECKER.validate_snapshot(root, registry["successors"][11])


def test_v3_rejects_provider_test_snapshot_tamper(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    _v2, registry, _manifest = _load_generated(root)
    snapshot = root / BUILDER.BINDINGS_REL / registry["successors"][12]["snapshot_path"]
    os.chmod(snapshot, 0o644)
    snapshot.write_bytes(snapshot.read_bytes() + b"# drift\n")

    with pytest.raises(ValueError, match="provider test snapshot drift"):
        CHECKER.validate_provider_test_snapshot(root, registry["successors"][12])


@pytest.mark.parametrize("repair_index", range(len(BUILDER.CONTRACT_REPAIRS)))
def test_v3_rejects_contract_repair_source_drift(tmp_path: Path, repair_index: int) -> None:
    root = _temporary_root(tmp_path)
    path = root / BUILDER.CONTRACT_REPAIRS[repair_index]["source_path"]
    path.chmod(0o644)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="contract repair source identity drift"):
        BUILDER.build_documents(root)


@pytest.mark.parametrize("repair_index", range(len(BUILDER.CONTRACT_REPAIRS)))
def test_v3_rejects_contract_repair_row_tamper(tmp_path: Path, repair_index: int) -> None:
    root = _temporary_root(tmp_path)
    BUILDER.write_create_only(root)
    v2, registry, manifest = _load_generated(root)
    registry["successors"][13 + repair_index]["predecessor_sha256"] = "0" * 64
    registry = _refresh_digest(registry)
    with pytest.raises(ValueError, match="v3 exact shared successor identities drift"):
        CHECKER.validate_document_semantics(root, v2=v2, registry=registry, manifest=manifest)


def test_v3_rejects_c61_spec_binding_role_drift(tmp_path: Path) -> None:
    root = _temporary_root(tmp_path)
    source = next(row for row in BUILDER.FROZEN_CELL_SOURCES if row["cell_id"] == "C6.1")
    path = root / source["spec_path"]
    path.chmod(0o644)
    value = json.loads(path.read_text())
    value["source_bindings"][8]["role"] = "undeclared_role"
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="frozen cell specification binding drift: C6.1"):
        BUILDER.build_documents(root)
