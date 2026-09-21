from __future__ import annotations

import hashlib
import importlib.util
import json
import ast
import shlex
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/generate_c9_authority_sidecar_rebind.py"
SPEC = importlib.util.spec_from_file_location("generate_c9_authority_sidecar_rebind", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _assert_direct_annotated_return(function_name: str, derived_as: str, fact_source: str, witness: str) -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=SCRIPT.as_posix())
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
    )
    assert isinstance(function.returns, ast.Subscript)
    assert isinstance(function.returns.value, ast.Name)
    assert function.returns.value.id == "Annotated"

    return_hint = get_type_hints(MODULE.build_documents, include_extras=True)["return"]
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


def test_generate_c9_authority_sidecar_documents_metadata() -> None:
    _assert_direct_annotated_return(
        "build_documents",
        "view",
        "C9_predecessor_candidate_current_checkout_bindings",
        "test:test_generate_c9_authority_sidecar_documents_metadata",
    )


def test_authority_ceiling_and_content_digest_are_non_authoritative_and_stable() -> None:
    payload = {
        "schema": MODULE.SCHEMA,
        "authority_ceiling": dict(MODULE.AUTHORITY_CEILING),
        "canonical_source": False,
        "domain_authoritative": False,
        "artifact_identity_authoritative": False,
    }
    assert all(value is False for value in payload["authority_ceiling"].values())
    assert MODULE._content_digest(payload) == MODULE._content_digest(dict(payload))
    assert len(MODULE._content_digest(payload)) == 64


def test_stage_and_path_validation_fail_closed() -> None:
    assert MODULE._validate_stage("B13") == MODULE.DEFAULT_STAGE
    assert MODULE._validate_stage("stage-b13-2026-09-06") == "stage-b13-2026-09-06"
    assert MODULE._validate_stage("B15") == MODULE.DEFAULT_B15_STAGE
    assert MODULE._validate_stage("stage-b15-2026-09-06") == "stage-b15-2026-09-06"
    assert MODULE._validate_stage("B16") == MODULE.DEFAULT_B16_STAGE
    assert MODULE._validate_stage("stage-b16-2026-09-06") == "stage-b16-2026-09-06"
    assert MODULE._validate_stage("B17") == MODULE.DEFAULT_B17_STAGE
    assert MODULE._validate_stage("stage-b17-2026-09-06") == "stage-b17-2026-09-06"
    assert MODULE._validate_stage("B18") == MODULE.DEFAULT_B18_STAGE
    assert MODULE._validate_stage("stage-b18-2026-09-06") == "stage-b18-2026-09-06"
    assert MODULE._validate_stage("B19") == MODULE.DEFAULT_B19_STAGE
    assert MODULE._validate_stage("stage-b19-2026-09-06") == "stage-b19-2026-09-06"
    assert MODULE._validate_stage("B23") == MODULE.DEFAULT_B23_STAGE
    assert MODULE._validate_stage("stage-b23-2026-09-06") == "stage-b23-2026-09-06"
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b12-2026-09-05")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("../stage-b13-2026-09-05")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b14-2026-09-05")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b15-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b16-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b17-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b18-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b19-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="invalid stage"):
        MODULE._validate_stage("stage-b23-2026-02-30")
    with pytest.raises(MODULE.GenerationError, match="path escapes"):
        MODULE._safe_relative(ROOT, "stage-b13-2026-09-05/../sidecars/C9.v2.json")
    with pytest.raises(MODULE.GenerationError, match="path escapes"):
        MODULE._safe_relative(ROOT, "/tmp/C9.v2.json")


def test_predecessor_hash_drift_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    predecessor = Path("docs/governance/generated-evidence-authority-sidecar.c9.v1.json")
    path = tmp_path / predecessor
    path.parent.mkdir(parents=True)
    path.write_bytes(b"tampered")
    monkeypatch.setattr(MODULE, "PREDECESSOR_HASHES", {predecessor: hashlib.sha256(b"original").hexdigest()})
    with pytest.raises(MODULE.GenerationError, match="frozen predecessor drift"):
        MODULE._guard_predecessors(tmp_path)


def test_b13_sidecar_predecessor_hash_is_fixed_to_current_repo_bytes() -> None:
    path = ROOT / MODULE.B13_SIDECAR_REL
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "2155083e699725c78eebf8fd6ecae008c5bf4f97c8cd28c103b777e821e8b2da"
    )
    assert MODULE.B13_PREDECESSOR_HASHES == {
        MODULE.B13_SIDECAR_REL: "2155083e699725c78eebf8fd6ecae008c5bf4f97c8cd28c103b777e821e8b2da"
    }


def test_b15_sidecar_predecessor_hash_is_fixed_to_current_repo_bytes() -> None:
    path = ROOT / MODULE.B15_SIDECAR_REL
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "d1c4472a1efc1b64d4a5b928547882eb61ed82ac314cd32b3ab14d9e41507b37"
    )
    assert MODULE.B15_PREDECESSOR_HASHES == {
        MODULE.B15_SIDECAR_REL: "d1c4472a1efc1b64d4a5b928547882eb61ed82ac314cd32b3ab14d9e41507b37"
    }


def test_b17_sidecar_predecessor_hash_is_fixed_to_current_repo_bytes() -> None:
    path = ROOT / MODULE.B17_SIDECAR_REL
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "dc3b7a9296ea2f358778081b8a1aa65a5383526f201192098c424dd6ef49ae78"
    )
    assert MODULE.B17_PREDECESSOR_HASHES == {
        MODULE.B17_SIDECAR_REL: "dc3b7a9296ea2f358778081b8a1aa65a5383526f201192098c424dd6ef49ae78"
    }


def test_b15_requires_a_same_stage_live_candidate_before_sidecar_generation() -> None:
    with pytest.raises(MODULE.GenerationError, match="required input missing"):
        MODULE.build_documents(ROOT, "stage-b15-2099-01-01")


def test_b16_requires_a_same_stage_live_candidate_before_sidecar_generation() -> None:
    with pytest.raises(MODULE.GenerationError, match="required input missing"):
        MODULE.build_documents(ROOT, "stage-b16-2099-01-01")


def test_b18_requires_a_same_stage_live_candidate_before_sidecar_generation() -> None:
    with pytest.raises(MODULE.GenerationError, match="required input missing"):
        MODULE.build_documents(ROOT, "stage-b18-2099-01-01")


def test_b15_outputs_v3_after_same_stage_candidate_live_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b15-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    predecessor_rel = MODULE.B13_SIDECAR_REL
    monkeypatch.setattr(MODULE, "_guard_predecessors", lambda root, stage_name: None)
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B15_C9_AMENDMENT,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_raw_ref",
        lambda root, relative: {
            "path": Path(relative).as_posix(),
            "file_sha256": hashlib.sha256(Path(relative).as_posix().encode()).hexdigest(),
            "bytes": len(Path(relative).as_posix().encode()),
            "lines": 1,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_module_binding",
        lambda root, relative, kind, functions: {"kind": kind, "functions": list(functions)},
    )
    monkeypatch.setattr(MODULE, "_function_bindings", lambda root, relative, kind, functions: [])

    documents = MODULE.build_documents(tmp_path, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / "sidecar-inputs/C9.v3.json"
    assert list(documents) == [relative]
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B15_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B15_SIDECAR_ID
    assert sidecar["version"] == "3.0.0"
    assert sidecar["predecessor"]["path"] == predecessor_rel.as_posix()
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B15_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


def test_b16_outputs_v4_after_same_stage_candidate_live_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b16-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    monkeypatch.setattr(MODULE, "_guard_predecessors", lambda root, stage_name: None)
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B16_C9_AMENDMENT,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_raw_ref",
        lambda root, relative: {
            "path": Path(relative).as_posix(),
            "file_sha256": hashlib.sha256(Path(relative).as_posix().encode()).hexdigest(),
            "bytes": len(Path(relative).as_posix().encode()),
            "lines": 1,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_module_binding",
        lambda root, relative, kind, functions: {"kind": kind, "functions": list(functions)},
    )
    monkeypatch.setattr(MODULE, "_function_bindings", lambda root, relative, kind, functions: [])
    documents = MODULE.build_documents(tmp_path, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / "sidecar-inputs/C9.v4.json"
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B16_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B16_SIDECAR_ID
    assert sidecar["version"] == "4.0.0"
    assert sidecar["predecessor"]["path"] == MODULE.B15_SIDECAR_REL.as_posix()
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B16_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


def test_b17_outputs_v5_after_same_stage_candidate_live_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b17-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    monkeypatch.setattr(MODULE, "_guard_predecessors", lambda root, stage_name: None)
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B17_C9_AMENDMENT,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_raw_ref",
        lambda root, relative: {
            "path": Path(relative).as_posix(),
            "file_sha256": hashlib.sha256(Path(relative).as_posix().encode()).hexdigest(),
            "bytes": len(Path(relative).as_posix().encode()),
            "lines": 1,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_module_binding",
        lambda root, relative, kind, functions: {"kind": kind, "functions": list(functions)},
    )
    monkeypatch.setattr(MODULE, "_function_bindings", lambda root, relative, kind, functions: [])

    documents = MODULE.build_documents(tmp_path, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / "sidecar-inputs/C9.v5.json"
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B17_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B17_SIDECAR_ID
    assert sidecar["version"] == "5.0.0"
    assert sidecar["predecessor"]["path"] == MODULE.B16_SIDECAR_REL.as_posix()
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B17_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


def test_b18_outputs_v6_after_same_stage_candidate_live_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b18-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    monkeypatch.setattr(MODULE, "_guard_predecessors", lambda root, stage_name: None)
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B18_C9_AMENDMENT,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_raw_ref",
        lambda root, relative: {
            "path": Path(relative).as_posix(),
            "file_sha256": hashlib.sha256(Path(relative).as_posix().encode()).hexdigest(),
            "bytes": len(Path(relative).as_posix().encode()),
            "lines": 1,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_module_binding",
        lambda root, relative, kind, functions: {"kind": kind, "functions": list(functions)},
    )
    monkeypatch.setattr(MODULE, "_function_bindings", lambda root, relative, kind, functions: [])

    documents = MODULE.build_documents(tmp_path, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / "sidecar-inputs/C9.v6.json"
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B18_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B18_SIDECAR_ID
    assert sidecar["version"] == "6.0.0"
    assert sidecar["predecessor"]["path"] == MODULE.B17_SIDECAR_REL.as_posix()
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B18_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


def test_b19_outputs_v7_with_b18_direct_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b19-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    monkeypatch.setattr(MODULE, "_guard_predecessors", lambda root, stage_name: None)
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B19_C9_AMENDMENT,
        },
    )
    monkeypatch.setattr(
        MODULE,
        "_raw_ref",
        lambda root, relative: {
            "path": Path(relative).as_posix(),
            "file_sha256": hashlib.sha256(Path(relative).as_posix().encode()).hexdigest(),
            "bytes": len(Path(relative).as_posix().encode()),
            "lines": 1,
        },
    )
    monkeypatch.setattr(MODULE, "_module_binding", lambda root, relative, kind, functions: {"kind": kind, "functions": list(functions)})
    monkeypatch.setattr(MODULE, "_function_bindings", lambda root, relative, kind, functions: [])

    documents = MODULE.build_documents(tmp_path, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / "sidecar-inputs/C9.v7.json"
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B19_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B19_SIDECAR_ID
    assert sidecar["version"] == "7.0.0"
    assert sidecar["predecessor"]["path"] == MODULE.B18_SIDECAR_REL.as_posix()
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B19_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


def test_b23_sidecar_predecessor_hash_is_fixed_to_current_repo_bytes() -> None:
    path = ROOT / MODULE.B23_PREDECESSOR_REL
    assert path.is_file()
    expected = "1272158927d5d6d3ded1d5dc07a888dce6d5353b76059fc17f328666fe92edc8"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    assert MODULE.B23_PREDECESSOR_HASHES == {MODULE.B23_PREDECESSOR_REL: expected}


def test_b23_requires_a_same_stage_live_candidate_before_sidecar_generation() -> None:
    with pytest.raises(MODULE.GenerationError, match="required input missing"):
        MODULE.build_documents(ROOT, "stage-b23-2099-01-01")


def test_b23_outputs_v8_with_b19_direct_predecessor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = "stage-b23-2099-01-01"
    candidate_rel = MODULE.EXACT_REBIND_REL / stage / "candidates/C9/candidate.v2.json"
    monkeypatch.setattr(
        MODULE,
        "_guard_predecessors",
        lambda root, stage_name: None,
    )
    monkeypatch.setattr(
        MODULE,
        "_validate_candidate",
        lambda root, stage_name: {
            "path": candidate_rel.as_posix(),
            "file_sha256": "1" * 64,
            "candidate_id": "2" * 64,
            "content_digest": "3" * 64,
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            "amendment": MODULE.B23_C9_AMENDMENT,
        },
    )

    documents = MODULE.build_documents(ROOT, stage)
    relative = MODULE.EXACT_REBIND_REL / stage / MODULE.B23_SIDECAR_INPUT_NAME
    assert set(documents) == {relative}
    sidecar = json.loads(documents[relative])
    assert sidecar["schema"] == MODULE.B23_SCHEMA
    assert sidecar["sidecar_id"] == MODULE.B23_SIDECAR_ID
    assert sidecar["version"] == "8.0.0"
    assert sidecar["stage"] == stage
    assert sidecar["predecessor"]["path"] == MODULE.B23_PREDECESSOR_REL.as_posix()
    assert sidecar["predecessor"]["file_sha256"] == hashlib.sha256(
        (ROOT / MODULE.B23_PREDECESSOR_REL).read_bytes()
    ).hexdigest()
    predecessor_binding = next(
        item for item in sidecar["bindings"]
        if item.get("path") == MODULE.B23_PREDECESSOR_REL.as_posix()
    )
    assert predecessor_binding["schema"] == MODULE.B19_SCHEMA
    assert sidecar["candidate"]["path"] == candidate_rel.as_posix()
    assert sidecar["candidate"]["amendment"] == MODULE.B23_C9_AMENDMENT
    assert sidecar["content_digest"] == MODULE._content_digest(sidecar)
    assert all(value is False for value in sidecar["authority_ceiling"].values())


@pytest.mark.parametrize(
    ("stage_name", "amendment"),
    [
        ("stage-b15-2099-01-01", MODULE.B15_C9_AMENDMENT),
        ("stage-b16-2099-01-01", MODULE.B16_C9_AMENDMENT),
        ("stage-b18-2099-01-01", MODULE.B18_C9_AMENDMENT),
        ("stage-b19-2099-01-01", MODULE.B19_C9_AMENDMENT),
    ],
)
def test_current_stage_candidate_must_bind_same_stage_and_pass_live_checker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage_name: str,
    amendment: str,
) -> None:
    stage = stage_name
    stage_rel = MODULE.EXACT_REBIND_REL / stage
    candidate_rel = stage_rel / "candidates/C9/candidate.v2.json"
    candidate_path = tmp_path / candidate_rel
    candidate_path.parent.mkdir(parents=True)

    def write_candidate(
        manifest_path: str | None = (stage_rel / "manifests/C9.json").as_posix(),
        amendment: str = amendment,
    ) -> None:
        value = {
            "amendment": amendment,
            "candidate_id": "2" * 64,
            "family": "C9",
            "fragments": [{"path": (stage_rel / "fragments/C9.json").as_posix()}],
            "manifest": {"path": manifest_path},
            "schema": "mrw.family_fragment_rebind.candidate.v2",
            "status": "CANDIDATE_VALID_NOT_AUTHORITY",
        }
        value["content_digest"] = MODULE._content_digest(value)
        candidate_path.write_text(json.dumps(value), encoding="utf-8")

    class Checker:
        def __init__(self) -> None:
            self.calls: list[tuple[Path, bool]] = []

        def check_candidate(self, path: Path, repo_root: Path, history_only: bool) -> None:
            self.calls.append((path, history_only))

    checker = Checker()
    monkeypatch.setattr(MODULE, "_load_candidate_checker", lambda root: checker)
    write_candidate((stage_rel / "manifests/C9.json").as_posix())
    result = MODULE._validate_candidate(tmp_path, stage)
    assert result["amendment"] == amendment
    assert checker.calls == [(candidate_path, False)]

    write_candidate((MODULE.EXACT_REBIND_REL / "stage-b14-2099-01-01/manifests/C9.json").as_posix())
    with pytest.raises(MODULE.GenerationError, match="same stage"):
        MODULE._validate_candidate(tmp_path, stage)
    write_candidate(amendment="STAGE_B14_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY")
    with pytest.raises(MODULE.GenerationError, match="amendment mismatch"):
        MODULE._validate_candidate(tmp_path, stage)


def test_create_only_allows_existing_stage_but_rejects_own_target(tmp_path: Path) -> None:
    stage = tmp_path / (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2026-09-05"
    )
    stage.mkdir(parents=True)
    relative = MODULE.EXACT_REBIND_REL / "stage-b13-2026-09-05/sidecar-inputs/C9.v2.json"
    MODULE._guard_create_only(tmp_path, {relative: b"{}"})
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing")
    with pytest.raises(MODULE.GenerationError, match="existing sidecar input"):
        MODULE._guard_create_only(tmp_path, {relative: b"{}"})


def test_write_coexists_with_other_families_and_preserves_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = tmp_path / (
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
        "stage-b13-2026-09-05"
    )
    other = stage / "fragments/C2.json"
    other.parent.mkdir(parents=True)
    other.write_bytes(b"other-family")
    relative = MODULE.EXACT_REBIND_REL / "stage-b13-2026-09-05/sidecar-inputs/C9.v2.json"
    payload = b'{"schema":"test"}\n'
    monkeypatch.setattr(MODULE, "build_documents", lambda root, stage: {relative: payload})

    assert MODULE.main(["--repo-root", str(tmp_path), "--stage", "B13", "--write"]) == 0
    assert json.loads(capsys.readouterr().out) == {"paths": [relative.as_posix()], "status": "WROTE"}
    assert (tmp_path / relative).read_bytes() == payload
    assert other.read_bytes() == b"other-family"

    assert MODULE.main(["--repo-root", str(tmp_path), "--stage", "B13", "--write"]) == 2
    assert "existing sidecar input" in capsys.readouterr().err
    assert other.read_bytes() == b"other-family"


def test_dry_run_is_deterministic_and_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative = MODULE.EXACT_REBIND_REL / "stage-b13-2026-09-05/sidecars/C9.v2.json"
    payload = json.dumps({"schema": MODULE.SCHEMA}, sort_keys=True).encode()
    monkeypatch.setattr(MODULE, "build_documents", lambda root, stage: {relative: payload})
    monkeypatch.setattr(MODULE, "_guard_create_only", lambda root, documents: None)
    assert MODULE.main(["--repo-root", str(tmp_path), "--stage", "B13"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"paths": [relative.as_posix()], "status": "READY"}
    assert not (tmp_path / relative).exists()
    assert MODULE.main(["--repo-root", str(tmp_path), "--stage", "B13"]) == 0
    assert json.loads(capsys.readouterr().out) == output


def test_candidate_status_and_digest_are_checked(tmp_path: Path) -> None:
    candidate = tmp_path / MODULE.B8_CANDIDATE_REL
    candidate.parent.mkdir(parents=True)
    value = {
        "schema": "mrw.family_fragment_rebind.candidate.v2",
        "family": "C9",
        "status": "NOT_VALID",
        "content_digest": "0" * 64,
    }
    candidate.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(MODULE.GenerationError, match="not valid"):
        MODULE._validate_candidate(tmp_path, MODULE.DEFAULT_STAGE)
