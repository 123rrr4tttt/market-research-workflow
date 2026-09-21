from __future__ import annotations

import hashlib
import json
import sys
import ast
import shlex
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "main/backend"))
sys.path.insert(0, str(ROOT / "src"))
import generate_stage0_family_exact_byte_rebind as tool  # noqa: E402


def _assert_direct_annotated_return(function_name: str, derived_as: str, fact_source: str, witness: str) -> None:
    source = (ROOT / "scripts/generate_stage0_family_exact_byte_rebind.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="scripts/generate_stage0_family_exact_byte_rebind.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    assert isinstance(function.returns, ast.Subscript)
    assert isinstance(function.returns.value, ast.Name)
    assert function.returns.value.id == "Annotated"

    return_hint = get_type_hints(tool.build_documents, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated
    _, annotation = get_args(return_hint)
    tokens = shlex.split(annotation)
    assert tokens[0] == "kit:non-authoritative"
    fields = dict(token.split("=", 1) for token in tokens[1:])
    assert fields == {
        "derived_as": derived_as,
        "fact_source": fact_source,
        "witness": witness,
    }


def test_generate_stage0_family_documents_metadata() -> None:
    _assert_direct_annotated_return(
        "build_documents",
        "generated_evidence",
        "family_configs_shared_generator_current_repo_bindings",
        "test:test_generate_stage0_family_documents_metadata",
    )


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        _canonical({key: item for key, item in value.items() if key != "content_digest"})
    ).hexdigest()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for relative in ("shared.py", "config.py", "source.py", "test.py"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
    fragment = {
        "schema": "fixture.v1",
        "phase": "P3",
        "family": "C2",
        "fragment_id": "fixture-c2",
        "status": "CANDIDATE_NOT_AUTHORITY",
        "authority": {"cutover": False},
        "cells": [{"cell_id": "C2.1"}],
        "source_bindings": [{"path": "source.py"}],
        "implementation_bindings": [{"path": "shared.py"}],
        "test_bindings": [{"path": "test.py"}],
        "open_findings": [{"id": "OPEN"}],
    }
    fragment["content_digest"] = _digest(fragment)
    monkeypatch.setattr(tool, "COMMON_SOURCE_RELS", ("shared.py",))
    monkeypatch.setattr(tool, "_config_relative", lambda family: "config.py")
    monkeypatch.setattr(tool, "config_for", lambda family: object())
    monkeypatch.setattr(tool, "build_fragment", lambda config, root: fragment)
    monkeypatch.setattr(tool, "fragment_bytes", lambda config, value: _canonical(value) + b"\n")


EXPECTED_B13_PREDECESSOR_HASHES = {
    "stage-b13-2026-09-05/fragments/C2.json": "0185f345f7bd6494251845f0bc302fbe913e317d9dcb8cd294107a9d9613626c",
    "stage-b13-2026-09-05/manifests/C2.json": "e2a22a328f4d1becdd5b60ad7edfceaf04cd3243e3ae55ab531a44fa745143d9",
    "stage-b13-2026-09-05/candidates/C2/candidate.v2.json": "a5f9f704091d9c8baee4a4f0ce3ccf6da4bedab666d427d4b3d50510c136dcf0",
    "stage-b13-2026-09-05/fragments/C3.json": "edbf5e3368745c8d96b21141a0dc13e4bfb93a132de65b0b59f38e298c97965a",
    "stage-b13-2026-09-05/manifests/C3.json": "690c3c01eb9e6e200d2968957d4f1e0f975d5779bc61c2f93c673ca64e38ed09",
    "stage-b13-2026-09-05/candidates/C3/candidate.v2.json": "086d5553e3ad0af9a2693ebfe51e2361526c79d55fd250092222811bfc84747a",
    "stage-b13-2026-09-05/fragments/C4.json": "932d2b019cde0dc620f1a58b22306e3efdb3dc2ecbab675eaeb943a06e60a6d3",
    "stage-b13-2026-09-05/manifests/C4.json": "cbc732402b7a91dd63847f013f524a4e591b14ad991c23fee44cb214b4f7c77a",
    "stage-b13-2026-09-05/candidates/C4/candidate.v2.json": "b873df24712698d1a7c3d28ee5f1d9cafbfb6b755218412eb2bfc6d80d8e4ab7",
    "stage-b13-2026-09-05/fragments/C5.json": "6e36ef77bb743df41159ea6dd732ea6383d6e14532c693dfaebf0146196c8ecc",
    "stage-b13-2026-09-05/manifests/C5.json": "1286a3447e2b0c562cb0b43ca986822ea884366a5815dc00a93d230c1f7e9af5",
    "stage-b13-2026-09-05/candidates/C5/candidate.v2.json": "b9b61dcc18811d99e50cd523d3632bce75c86e6a7a1d9c6874189213e9335173",
    "stage-b13-2026-09-05/fragments/C6.json": "b41f5c2dbbdfd268a86886c9ffc27fe78cfa3fb5914db44272b3dfece65e52bc",
    "stage-b13-2026-09-05/manifests/C6.json": "62ee39752b2057629fba2abdb2e7475053a54164b7eeceedd173874e07c5e117",
    "stage-b13-2026-09-05/candidates/C6/candidate.v2.json": "cd8de95ce3421e679e5b1ed9f4faa72494e348465cb4c084267aa825669a59cc",
    "stage-b13-2026-09-05/fragments/C8.json": "3f3e515948c752e5b8ca8482804d3cc66e891fe2477999c208abf157e2330a9b",
    "stage-b13-2026-09-05/manifests/C8.json": "80e8594920e3373980db162961b615e8a6f5363d4a57ba979e0536dee9b8f285",
    "stage-b13-2026-09-05/candidates/C8/candidate.v2.json": "7ce6102220771c12c90079162aab5fcfa4e48d853c23b5cd85f085cafa6acd1c",
    "stage-b13-2026-09-05/fragments/C9.json": "6ca3cd594d6badd2676de56599f39a8f554011a6ddc00a783aa72eb7cb180ee9",
    "stage-b13-2026-09-05/manifests/C9.json": "6a9ac32e5ac7397708a91b7c915b5d3b916cb3f28a3e61ae642179cf070f5986",
    "stage-b13-2026-09-05/candidates/C9/candidate.v2.json": "107967f2ba458ff902949c49271d09e4f9e55e4ecec35c8127ccdf90ebdaa9f8",
}


EXPECTED_B15_PREDECESSOR_HASHES = {
    "stage-b15-2026-09-05/fragments/C2.json": "3fa5f21281f7df20000914ae48a8cb0ce489f9b7dd2a78a8620511db6104178a",
    "stage-b15-2026-09-05/manifests/C2.json": "5d2514ac6cc4ec2aff8d55a05b4941d8ad03395340f384f964bd64224f22cf0a",
    "stage-b15-2026-09-05/candidates/C2/candidate.v2.json": "de0e01a13efe6aa220a163fb996bb9bddd86800fd1b4579cc5a9fd4a36b87394",
    "stage-b15-2026-09-05/fragments/C3.json": "edbf5e3368745c8d96b21141a0dc13e4bfb93a132de65b0b59f38e298c97965a",
    "stage-b15-2026-09-05/manifests/C3.json": "2634d41d1f75c94b6604c52210cb4756a84ebce63ce4ab5c38b67fd95ed35097",
    "stage-b15-2026-09-05/candidates/C3/candidate.v2.json": "a041ea35f9cb487e18ece3af24b2742784eb9ecb864560b50b26f537de740064",
    "stage-b15-2026-09-05/fragments/C4.json": "932d2b019cde0dc620f1a58b22306e3efdb3dc2ecbab675eaeb943a06e60a6d3",
    "stage-b15-2026-09-05/manifests/C4.json": "5a24b0a072874a49a8887cabb110de00611206f50213e991ec5c3e41e653cd2c",
    "stage-b15-2026-09-05/candidates/C4/candidate.v2.json": "df7df8126b8dbc235f0f75130bae0afc8a34d8f739aa39c63dcbe27c30031f82",
    "stage-b15-2026-09-05/fragments/C5.json": "6e36ef77bb743df41159ea6dd732ea6383d6e14532c693dfaebf0146196c8ecc",
    "stage-b15-2026-09-05/manifests/C5.json": "20ad825d2eb130a6400b1c17f116001729b4a5d817c2faa9e840902712eae49f",
    "stage-b15-2026-09-05/candidates/C5/candidate.v2.json": "2f123b1ca1693643b3b277f79031064089609d3c5bef5ef7570cb580bccaecd2",
    "stage-b15-2026-09-05/fragments/C6.json": "b41f5c2dbbdfd268a86886c9ffc27fe78cfa3fb5914db44272b3dfece65e52bc",
    "stage-b15-2026-09-05/manifests/C6.json": "d756cfbe4434b1e7083fb0c7adb3b0642da92b4340ac3b20df2a74618a255d0d",
    "stage-b15-2026-09-05/candidates/C6/candidate.v2.json": "be186d5824e9125cd8549717c888684a83034b142a8165a1436a5fd1af77b621",
    "stage-b15-2026-09-05/fragments/C8.json": "3f3e515948c752e5b8ca8482804d3cc66e891fe2477999c208abf157e2330a9b",
    "stage-b15-2026-09-05/manifests/C8.json": "7afb8fda6f8f95bf85786c36b8d2142d4cc6a3e87d9560d157c87ff4ea2fd30a",
    "stage-b15-2026-09-05/candidates/C8/candidate.v2.json": "f32b76bdd3a5fe5c59e0e972b2283755129f11df16b72af2579d1a20738acd94",
    "stage-b15-2026-09-05/fragments/C9.json": "6ca3cd594d6badd2676de56599f39a8f554011a6ddc00a783aa72eb7cb180ee9",
    "stage-b15-2026-09-05/manifests/C9.json": "86d6dbe2d73e15a0414312dca290d5ffb43cf148d479627cb16d4de8045226fb",
    "stage-b15-2026-09-05/candidates/C9/candidate.v2.json": "43b11a595d52a62375e1acf9e630965edbe036e3772a3bc038d446b52d850fe2",
}


def test_b13_predecessor_hashes_are_fixed_to_current_repo_bytes() -> None:
    for suffix, expected in EXPECTED_B13_PREDECESSOR_HASHES.items():
        path = ROOT / tool.EXACT_BYTE_REBIND_REL / suffix
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    assert {
        key.relative_to(tool.EXACT_BYTE_REBIND_REL).as_posix(): value
        for key, value in tool.B13_PREDECESSOR_HASHES.items()
    } == EXPECTED_B13_PREDECESSOR_HASHES


def _install_b13_c2_predecessors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[Path, str]:
    predecessors: dict[Path, str] = {}
    payloads = {
        "fragments/C2.json": b"predecessor-fragment",
        "manifests/C2.json": b"predecessor-manifest",
        "candidates/C2/candidate.v2.json": b"predecessor-candidate",
    }
    for suffix, payload in payloads.items():
        relative = tool.EXACT_BYTE_REBIND_REL / "stage-b13-2099-01-01" / suffix
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        predecessors[relative] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(tool, "B13_PREDECESSOR_HASHES", predecessors)
    return predecessors


def _install_b15_c2_predecessors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[Path, str]:
    predecessors: dict[Path, str] = {}
    payloads = {
        "fragments/C2.json": b"b15-fragment",
        "manifests/C2.json": b"b15-manifest",
        "candidates/C2/candidate.v2.json": b"b15-candidate",
    }
    for suffix, payload in payloads.items():
        relative = tool.EXACT_BYTE_REBIND_REL / "stage-b15-2099-01-01" / suffix
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        predecessors[relative] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(tool, "B15_PREDECESSOR_HASHES", predecessors)
    return predecessors


def _install_b16_c2_predecessors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[Path, str]:
    predecessors: dict[Path, str] = {}
    payloads = {
        "fragments/C2.json": b"b16-fragment",
        "manifests/C2.json": b"b16-manifest",
        "candidates/C2/candidate.v2.json": b"b16-candidate",
    }
    for suffix, payload in payloads.items():
        relative = tool.EXACT_BYTE_REBIND_REL / "stage-b16-2099-01-01" / suffix
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        predecessors[relative] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(tool, "B16_PREDECESSOR_HASHES", predecessors)
    return predecessors


def _install_b17_c2_predecessors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[Path, str]:
    predecessors: dict[Path, str] = {}
    payloads = {
        "fragments/C2.json": b"b17-fragment",
        "manifests/C2.json": b"b17-manifest",
        "candidates/C2/candidate.v2.json": b"b17-candidate",
    }
    for suffix, payload in payloads.items():
        relative = tool.EXACT_BYTE_REBIND_REL / "stage-b17-2099-01-01" / suffix
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        predecessors[relative] = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(tool, "B17_PREDECESSOR_HASHES", predecessors)
    return predecessors


def test_b15_uses_new_amendment_and_immutable_b13_predecessor_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    predecessors = _install_b13_c2_predecessors(tmp_path, monkeypatch)
    stage = "stage-b15-2099-01-01"
    other = tmp_path / tool.EXACT_BYTE_REBIND_REL / stage / "fragments/C3.json"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"other-family")

    first = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    second = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    assert first == second
    manifest_path = next(path for path in first if "manifests" in path.parts)
    manifest = json.loads(first[manifest_path])
    assert manifest["amendment"] == "STAGE_B15_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    references = {item["path"]: item["file_sha256"] for item in manifest["sources"]}
    for relative, expected in predecessors.items():
        assert references[relative.as_posix()] == expected

    tool._write_documents(tmp_path, first, stage)
    assert other.read_bytes() == b"other-family"
    with pytest.raises(tool.GenerationError, match="create-only target already exists"):
        tool.build_documents(tmp_path, stage=stage, families=["C2"])


def test_b15_predecessor_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    predecessors = _install_b13_c2_predecessors(tmp_path, monkeypatch)
    drifted = next(iter(predecessors))
    monkeypatch.setitem(tool.B13_PREDECESSOR_HASHES, drifted, "0" * 64)
    with pytest.raises(tool.GenerationError, match="immutable B13 predecessor drift"):
        tool.build_documents(tmp_path, stage="stage-b15-2099-01-01", families=["C2"])


def test_b15_predecessor_hashes_are_fixed_to_current_repo_bytes() -> None:
    for suffix, expected in EXPECTED_B15_PREDECESSOR_HASHES.items():
        path = ROOT / tool.EXACT_BYTE_REBIND_REL / suffix
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    assert {
        key.relative_to(tool.EXACT_BYTE_REBIND_REL).as_posix(): value
        for key, value in tool.B15_PREDECESSOR_HASHES.items()
    } == EXPECTED_B15_PREDECESSOR_HASHES


def test_b16_uses_new_amendment_and_immutable_b15_predecessor_refs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    predecessors = _install_b15_c2_predecessors(tmp_path, monkeypatch)
    stage = "stage-b16-2099-01-01"
    first = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    second = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    assert first == second
    manifest_path = next(path for path in first if "manifests" in path.parts)
    manifest = json.loads(first[manifest_path])
    assert manifest["amendment"] == "STAGE_B16_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    references = {item["path"]: item["file_sha256"] for item in manifest["sources"]}
    for relative, expected in predecessors.items():
        assert references[relative.as_posix()] == expected


def test_b16_predecessor_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    predecessors = _install_b15_c2_predecessors(tmp_path, monkeypatch)
    drifted = next(iter(predecessors))
    monkeypatch.setitem(tool.B15_PREDECESSOR_HASHES, drifted, "0" * 64)
    with pytest.raises(tool.GenerationError, match="immutable B15 predecessor drift"):
        tool.build_documents(tmp_path, stage="stage-b16-2099-01-01", families=["C2"])


def test_b17_uses_new_amendment_and_all_prior_stage_predecessors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    b13 = _install_b13_c2_predecessors(tmp_path, monkeypatch)
    b15 = _install_b15_c2_predecessors(tmp_path, monkeypatch)
    b16 = _install_b16_c2_predecessors(tmp_path, monkeypatch)
    stage = "stage-b17-2099-01-01"

    first = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    second = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    assert first == second
    manifest_path = next(path for path in first if "manifests" in path.parts)
    manifest = json.loads(first[manifest_path])
    assert manifest["amendment"] == "STAGE_B17_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    references = {item["path"]: item["file_sha256"] for item in manifest["sources"]}
    for predecessors in (b13, b15, b16):
        for relative, expected in predecessors.items():
            assert references[relative.as_posix()] == expected


def test_b17_predecessor_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    _install_b13_c2_predecessors(tmp_path, monkeypatch)
    _install_b15_c2_predecessors(tmp_path, monkeypatch)
    b16 = _install_b16_c2_predecessors(tmp_path, monkeypatch)
    monkeypatch.setitem(tool.B16_PREDECESSOR_HASHES, next(iter(b16)), "0" * 64)
    with pytest.raises(tool.GenerationError, match="immutable B16 predecessor drift"):
        tool.build_documents(tmp_path, stage="stage-b17-2099-01-01", families=["C2"])


def test_b18_uses_new_amendment_and_b17_chain_predecessors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    b13 = _install_b13_c2_predecessors(tmp_path, monkeypatch)
    b15 = _install_b15_c2_predecessors(tmp_path, monkeypatch)
    b16 = _install_b16_c2_predecessors(tmp_path, monkeypatch)
    b17 = _install_b17_c2_predecessors(tmp_path, monkeypatch)
    stage = "stage-b18-2099-01-01"

    first = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    second = tool.build_documents(tmp_path, stage=stage, families=["C2"])
    assert first == second
    manifest_path = next(path for path in first if "manifests" in path.parts)
    manifest = json.loads(first[manifest_path])
    assert manifest["amendment"] == "STAGE_B18_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    references = {item["path"]: item["file_sha256"] for item in manifest["sources"]}
    for predecessors in (b13, b15, b16, b17):
        for relative, expected in predecessors.items():
            assert references[relative.as_posix()] == expected


def test_b18_predecessor_drift_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fixture(tmp_path, monkeypatch)
    _install_b13_c2_predecessors(tmp_path, monkeypatch)
    _install_b15_c2_predecessors(tmp_path, monkeypatch)
    _install_b16_c2_predecessors(tmp_path, monkeypatch)
    b17 = _install_b17_c2_predecessors(tmp_path, monkeypatch)
    monkeypatch.setitem(tool.B17_PREDECESSOR_HASHES, next(iter(b17)), "0" * 64)
    with pytest.raises(tool.GenerationError, match="immutable B17 predecessor drift"):
        tool.build_documents(tmp_path, stage="stage-b18-2099-01-01", families=["C2"])


def test_create_only_and_manifest_source_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture(tmp_path, monkeypatch)
    docs = tool.build_documents(tmp_path, stage="stage-b13-2099-01-01", families=["C2"])
    assert len(docs) == 2
    manifest_path = next(path for path in docs if path.name == "C2.json" and "manifests" in path.parts)
    manifest = json.loads(docs[manifest_path])
    for reference in manifest["sources"] + manifest["tests"]:
        assert reference["file_sha256"] == hashlib.sha256(
            (tmp_path / reference["path"]).read_bytes()
        ).hexdigest()
    tool._write_documents(tmp_path, docs, "stage-b13-2099-01-01")
    with pytest.raises(tool.GenerationError, match="already exists"):
        tool.build_documents(tmp_path, stage="stage-b13-2099-01-01", families=["C2"])


def test_frozen_predecessor_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture(tmp_path, monkeypatch)
    frozen = tmp_path / "p3-fragments/C2.json"
    frozen.parent.mkdir(parents=True)
    frozen.write_text("frozen", encoding="utf-8")
    frozen_fragment = {
        "schema": "fixture.v1",
        "phase": "P3",
        "family": "C2",
        "fragment_id": "fixture-c2",
        "status": "CANDIDATE_NOT_AUTHORITY",
        "authority": {"cutover": False},
        "cells": [{"cell_id": "C2.1"}],
        "source_bindings": [{"path": "p3-fragments/C2.json"}],
        "implementation_bindings": [{"path": "shared.py"}],
        "test_bindings": [{"path": "test.py"}],
        "open_findings": [{"id": "OPEN"}],
    }
    frozen_fragment["content_digest"] = _digest(frozen_fragment)
    monkeypatch.setattr(tool, "build_fragment", lambda config, root: frozen_fragment)
    with pytest.raises(tool.GenerationError, match="frozen P3/P4"):
        tool.build_documents(tmp_path, stage="stage-b13-2099-01-01", families=["C2"])


def test_unknown_family_stage_and_traversal_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(tool.GenerationError, match="unknown family"):
        tool.validate_families(["C7"])
    with pytest.raises(tool.GenerationError, match="stage-b13"):
        tool.validate_stage("stage-b12-2026-09-05")
    with pytest.raises(tool.GenerationError, match="stage-b13"):
        tool.validate_stage("../stage-b13-2026-09-05")
    with pytest.raises(tool.GenerationError, match="stage-b13/stage-b15"):
        tool.validate_stage("stage-b14-2026-09-05")
    with pytest.raises(tool.GenerationError, match="stage-b13/stage-b15"):
        tool.validate_stage("stage-b15-2026-02-30")
    with pytest.raises(tool.GenerationError, match="stage-b13/stage-b15/stage-b16"):
        tool.validate_stage("stage-b16-2026-02-30")
    assert tool.validate_stage("B17") == tool.DEFAULT_B17_STAGE
    assert tool.validate_stage("stage-b17-2099-01-01") == "stage-b17-2099-01-01"
    assert tool.validate_stage("B18") == tool.DEFAULT_B18_STAGE
    assert tool.validate_stage("stage-b18-2099-01-01") == "stage-b18-2099-01-01"
    assert tool.validate_stage("B19") == tool.DEFAULT_B19_STAGE
    assert tool.validate_stage("stage-b19-2099-01-01") == "stage-b19-2099-01-01"
    with pytest.raises(tool.GenerationError, match="stage-b18"):
        tool.validate_stage("stage-b18-2026-02-30")


def test_b19_uses_b18_as_direct_immutable_predecessor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture(tmp_path, monkeypatch)
    predecessor_root = tool.EXACT_BYTE_REBIND_REL / "stage-b18-2026-09-05"
    predecessor_hashes: dict[Path, str] = {}
    for relative in (
        predecessor_root / "fragments/C2.json",
        predecessor_root / "manifests/C2.json",
        predecessor_root / "candidates/C2/candidate.v2.json",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(relative.name.encode())
        predecessor_hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(tool, "B19_PREDECESSOR_HASHES", predecessor_hashes)
    first = tool.build_documents(tmp_path, stage="B19", families=["C2"])
    second = tool.build_documents(tmp_path, stage="B19", families=["C2"])
    assert first == second
    manifest = json.loads(next(payload for path, payload in first.items() if path.parent.name == "manifests"))
    assert manifest["amendment"] == "STAGE_B19_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    assert {item["path"] for item in manifest["sources"]} >= {
        path.as_posix() for path in predecessor_hashes
    }


def test_b23_predecessor_hashes_are_fixed_to_current_b19_artifacts() -> None:
    expected_rels = [
        tool.EXACT_BYTE_REBIND_REL / "stage-b19-2026-09-05" / suffix.format(family=family)
        for family in sorted(tool.ALLOWED_FAMILIES)
        for suffix in (
            "fragments/{family}.json",
            "manifests/{family}.json",
            "candidates/{family}/candidate.v2.json",
        )
    ]
    assert set(tool.B23_PREDECESSOR_HASHES) == set(expected_rels)
    for relative, expected in tool.B23_PREDECESSOR_HASHES.items():
        path = ROOT / relative
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_b23_alias_is_valid_and_uses_b19_as_direct_immutable_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert tool.validate_stage("B23") == tool.DEFAULT_B23_STAGE
    assert tool.validate_stage("stage-b23-2099-01-01") == "stage-b23-2099-01-01"
    _fixture(tmp_path, monkeypatch)
    predecessor_root = tool.EXACT_BYTE_REBIND_REL / "stage-b19-2026-09-05"
    predecessor_hashes: dict[Path, str] = {}
    for family in sorted(tool.ALLOWED_FAMILIES):
        for relative in (
            predecessor_root / f"fragments/{family}.json",
            predecessor_root / f"manifests/{family}.json",
            predecessor_root / f"candidates/{family}/candidate.v2.json",
        ):
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(relative.as_posix().encode())
            predecessor_hashes[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(tool, "B23_PREDECESSOR_HASHES", predecessor_hashes)

    first = tool.build_documents(tmp_path, stage="stage-b23-2099-01-01", families=["C2"])
    second = tool.build_documents(tmp_path, stage="stage-b23-2099-01-01", families=["C2"])
    assert first == second
    manifest_path = next(path for path in first if path.parent.name == "manifests")
    manifest = json.loads(first[manifest_path])
    assert manifest["amendment"] == "STAGE_B23_C2_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    references = {item["path"]: item["file_sha256"] for item in manifest["sources"]}
    for relative, expected in predecessor_hashes.items():
        if "C2" in relative.as_posix():
            assert references[relative.as_posix()] == expected

    with pytest.raises(tool.GenerationError, match="immutable B19 predecessor drift"):
        monkeypatch.setitem(
            tool.B23_PREDECESSOR_HASHES,
            next(iter(tool.B23_PREDECESSOR_HASHES)),
            "0" * 64,
        )
        tool.build_documents(tmp_path, stage="B23", families=["C2"])


def test_repeated_dry_run_is_byte_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture(tmp_path, monkeypatch)
    first = tool.build_documents(tmp_path, stage="stage-b13-2099-01-02", families=["C2"])
    second = tool.build_documents(tmp_path, stage="stage-b13-2099-01-02", families=["C2"])
    assert first == second
