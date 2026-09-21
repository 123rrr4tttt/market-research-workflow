"""Exact-bound governance checks for the current C9 projection sidecar."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
EVIDENCE_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence"
)
EXACT_REBIND_REL = EVIDENCE_REL / "exact-byte-rebind"
V1_SIDECAR_PATH = ROOT / "docs/governance/generated-evidence-authority-sidecar.c9.v1.json"
SIDECAR_PATHS = {
    1: V1_SIDECAR_PATH,
    2: ROOT / EXACT_REBIND_REL / "stage-b13-2026-09-05/sidecar-inputs/C9.v2.json",
    3: ROOT / EXACT_REBIND_REL / "stage-b15-2026-09-05/sidecar-inputs/C9.v3.json",
    4: ROOT / EXACT_REBIND_REL / "stage-b16-2026-09-05/sidecar-inputs/C9.v4.json",
}
SOURCE_PATH = ROOT / "main/backend/app/successor_runtime/substrate/projections/c9_sources.py"
SOURCE_RELATIVE_PATH = (
    "main/backend/app/successor_runtime/substrate/projections/c9_sources.py"
)
CANONICAL_SOURCE_REL = (
    "main/backend/app/successor_runtime/substrate/postgres/c9_projection_sources.py"
)
SPEC_REL = EVIDENCE_REL / "capability-specs/C9.3.v1.json"
BUILD_REL = EVIDENCE_REL / "capability-spec-builds/C9.3.BuildManifest.v1.json"
PROJECTION_FUNCTIONS = (
    "build_agent_session_payload",
    "build_research_graph_payload",
    "build_search_payload",
)
CANONICAL_FUNCTIONS = (
    "read_runtime_session_source",
    "read_research_graph_source",
    "read_c7_search_source",
    "build_semantic_source_closure",
)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
NON_AUTHORITY_FIELDS = {
    "canonical_source",
    "domain_authoritative",
    "promotion_authority",
    "live_or_cutover_authority",
    "runtime_mutation",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(
        _canonical({key: item for key, item in value.items() if key != "content_digest"})
    ).hexdigest()


def _confined_path(raw: str | Path) -> Path:
    relative = Path(raw)
    assert not relative.is_absolute()
    assert "\\" not in str(raw)
    assert not any(part in {"", ".", ".."} for part in relative.parts)
    path = ROOT / relative
    assert not path.is_symlink()
    resolved = path.resolve(strict=True)
    resolved.relative_to(ROOT.resolve())
    return resolved


def _current_sidecar() -> tuple[int, Path, dict[str, Any]]:
    candidates: list[tuple[int, Path]] = []
    for version, path in SIDECAR_PATHS.items():
        if not path.is_file():
            continue
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        assert value["schema"] == f"mrw.governance.generated_evidence_authority_sidecar.c9.v{version}"
        candidates.append((version, path))
    assert candidates
    version, path = max(candidates, key=lambda item: item[0])
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return version, path, value


def _slice_bytes(raw: bytes, source_slice: dict[str, Any]) -> bytes:
    lines = raw.decode("utf-8").splitlines(keepends=True)
    start = source_slice["start_line"]
    end = source_slice["end_line"]
    assert isinstance(start, int) and isinstance(end, int)
    assert 1 <= start <= end <= len(lines)
    return "".join(lines[start - 1 : end]).encode("utf-8")


def _top_level_functions(
    tree: ast.Module,
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _assert_external_binding(binding: dict[str, Any]) -> tuple[bytes, ast.Module]:
    common_fields = {
        "kind",
        "path",
        "external_sha256",
        "bytes",
        "lines",
        "source_slice",
    }
    if binding["kind"] in {
        "current_c9_projection_source_module",
        "current_c9_canonical_source_closure_reader_module",
    }:
        expected_fields = common_fields | {"functions"}
    else:
        expected_fields = common_fields | {"function"} | NON_AUTHORITY_FIELDS
    assert set(binding) == expected_fields
    path = _confined_path(binding["path"])
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    assert SHA256.fullmatch(binding["external_sha256"])
    assert binding["external_sha256"] == hashlib.sha256(raw).hexdigest()
    assert binding["bytes"] == len(raw)
    assert binding["lines"] == len(text.splitlines())
    selected = _slice_bytes(raw, binding["source_slice"])
    assert binding["source_slice"] == {
        "start_line": binding["source_slice"]["start_line"],
        "end_line": binding["source_slice"]["end_line"],
        "bytes": len(selected),
        "sha256": hashlib.sha256(selected).hexdigest(),
    }
    if binding["kind"] in {
        "current_c9_projection_source_module",
        "c9_projection_payload_builder",
    }:
        assert binding["path"] == SOURCE_RELATIVE_PATH
        assert path == SOURCE_PATH.resolve()
    if binding["kind"] == "current_c9_canonical_source_closure_reader_module":
        assert binding["path"] == CANONICAL_SOURCE_REL
    if binding["kind"] == "c9_canonical_source_closure_reader":
        assert binding["path"] == CANONICAL_SOURCE_REL
    return raw, ast.parse(text)


def _assert_file_reference(reference: dict[str, Any], *, json_reference: bool = False) -> bytes:
    expected = {"path", "file_sha256", "bytes", "lines"}
    if json_reference:
        expected |= {"content_digest"}
    assert set(reference) == expected
    path = _confined_path(reference["path"])
    raw = path.read_bytes()
    assert reference["file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert reference["bytes"] == len(raw)
    assert reference["lines"] == len(raw.decode("utf-8").splitlines())
    if json_reference:
        value = json.loads(raw)
        assert isinstance(value, dict)
        assert reference["content_digest"] == _digest(value)
    return raw


def test_current_sidecar_schema_digest_and_non_authority_ceiling() -> None:
    version, path, sidecar = _current_sidecar()
    assert version >= 3
    assert sidecar["schema"] == f"mrw.governance.generated_evidence_authority_sidecar.c9.v{version}"
    assert sidecar["sidecar_id"] == f"c9.generated-evidence-authority-sidecar.v{version}"
    assert sidecar["version"] == f"{version}.0.0"
    assert sidecar["family"] == "C9"
    assert sidecar["stage"] == f"stage-b{12 + version}-2026-09-05"
    assert sidecar["mutability"] == "immutable"
    assert sidecar["derived_as"] == "view"
    assert sidecar["view_kind"] == "PROJECTION_VIEW"
    assert sidecar["snapshot_scope"] == "CURRENT_CHECKOUT_ONLY"
    assert sidecar["authority_direction"] == (
        "exact current-checkout C9 source/test/candidate identity -> non-authoritative projection view"
    )
    for field in {
        "canonical_source",
        "artifact_identity_authoritative",
        "domain_authoritative",
        "promotion_authority",
        "live_or_cutover_authority",
        "runtime_mutation",
    }:
        assert sidecar[field] is False
    assert sidecar["authority"] == {
        "reverse_write": False,
        "promotion": False,
        "candidate_claim": False,
    }
    assert set(sidecar["authority_ceiling"]) == {
        "canonical_source",
        "domain_authority",
        "canonical_write",
        "reverse_write",
        "promotion",
        "candidate_claim",
        "live_provider",
        "external_delivery",
        "cutover",
        "authority_transfer",
        "runtime_mutation",
    }
    assert all(value is False for value in sidecar["authority_ceiling"].values())
    assert sidecar["content_digest"] == _digest(sidecar)
    assert path == SIDECAR_PATHS[version]

    v1_raw = V1_SIDECAR_PATH.read_bytes()
    assert hashlib.sha256(v1_raw).hexdigest() == (
        "63f4bae0476a968386faec6049f95d0faa414d79bea1f6891868638e12692b15"
    )
    assert path.resolve() != V1_SIDECAR_PATH.resolve()


def test_current_sidecar_has_closed_twelve_binding_inventory() -> None:
    version, _, sidecar = _current_sidecar()
    bindings = sidecar["bindings"]
    assert len(bindings) == 12
    kinds = [binding["kind"] for binding in bindings]
    assert kinds.count("immutable_predecessor_sidecar") == 1
    assert kinds.count("current_c9_projection_source_module") == 1
    assert kinds.count("current_c9_canonical_source_closure_reader_module") == 1
    assert kinds.count("current_c9_capability_spec") == 1
    assert kinds.count("current_c9_capability_spec_build_manifest") == 1
    assert kinds.count("c9_projection_payload_builder") == 3
    assert kinds.count("c9_canonical_source_closure_reader") == 4
    assert {binding["path"] for binding in bindings} == {
        SIDECAR_PATHS[version - 1].relative_to(ROOT).as_posix(),
        SOURCE_RELATIVE_PATH,
        CANONICAL_SOURCE_REL,
        SPEC_REL.as_posix(),
        BUILD_REL.as_posix(),
    }

    predecessor = next(
        binding for binding in bindings if binding["kind"] == "immutable_predecessor_sidecar"
    )
    assert set(predecessor) == {
        "kind",
        "path",
        "file_sha256",
        "bytes",
        "lines",
        "schema",
        "mutability",
    }
    assert predecessor["schema"] == (
        f"mrw.governance.generated_evidence_authority_sidecar.c9.v{version - 1}"
    )
    assert predecessor["mutability"] == "immutable"
    predecessor_raw = _assert_file_reference(
        {key: value for key, value in predecessor.items() if key not in {"kind", "schema", "mutability"}}
    )
    predecessor_value = json.loads(predecessor_raw)
    assert predecessor_value["schema"] == predecessor["schema"]

    source_module = next(
        binding
        for binding in bindings
        if binding["kind"] == "current_c9_projection_source_module"
    )
    assert source_module["functions"] == list(PROJECTION_FUNCTIONS)
    raw, _ = _assert_external_binding(source_module)
    assert source_module["source_slice"] == {
        "start_line": 1,
        "end_line": len(raw.decode("utf-8").splitlines()),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_current_sidecar_exact_current_bytes_and_function_slices() -> None:
    source_before = SOURCE_PATH.read_bytes()
    canonical_before = (ROOT / CANONICAL_SOURCE_REL).read_bytes()
    _, _, sidecar = _current_sidecar()
    bindings = sidecar["bindings"]

    source_module = next(
        binding
        for binding in bindings
        if binding["kind"] == "current_c9_projection_source_module"
    )
    source_raw, source_tree = _assert_external_binding(source_module)
    assert source_raw == source_before
    source_inventory = _top_level_functions(source_tree)

    payload_builders = [
        binding for binding in bindings if binding["kind"] == "c9_projection_payload_builder"
    ]
    assert {binding["function"] for binding in payload_builders} == set(PROJECTION_FUNCTIONS)
    for binding in payload_builders:
        assert all(binding[field] is False for field in NON_AUTHORITY_FIELDS)
        _, tree = _assert_external_binding(binding)
        node = _top_level_functions(tree)[binding["function"]]
        assert node.lineno == binding["source_slice"]["start_line"]
        assert node.end_lineno == binding["source_slice"]["end_line"]
        selected = _slice_bytes(source_raw, binding["source_slice"])
        assert selected.decode("utf-8").startswith(f"def {binding['function']}(")
        assert binding["function"] in source_inventory

    canonical_module = next(
        binding
        for binding in bindings
        if binding["kind"] == "current_c9_canonical_source_closure_reader_module"
    )
    canonical_raw, canonical_tree = _assert_external_binding(canonical_module)
    assert canonical_raw == canonical_before
    canonical_inventory = _top_level_functions(canonical_tree)
    assert canonical_module["functions"] == list(CANONICAL_FUNCTIONS)
    assert set(canonical_module["functions"]) <= set(canonical_inventory)

    readers = [
        binding for binding in bindings if binding["kind"] == "c9_canonical_source_closure_reader"
    ]
    assert {binding["function"] for binding in readers} == set(CANONICAL_FUNCTIONS)
    for binding in readers:
        assert all(binding[field] is False for field in NON_AUTHORITY_FIELDS)
        _, tree = _assert_external_binding(binding)
        node = _top_level_functions(tree)[binding["function"]]
        assert (node.lineno, node.end_lineno) == (
            binding["source_slice"]["start_line"],
            binding["source_slice"]["end_line"],
        )
        selected = _slice_bytes(canonical_raw, binding["source_slice"])
        assert selected.decode("utf-8").startswith(f"def {binding['function']}(")

    assert SOURCE_PATH.read_bytes() == source_before
    assert (ROOT / CANONICAL_SOURCE_REL).read_bytes() == canonical_before


def test_current_sidecar_candidate_and_witness_references() -> None:
    version, _, sidecar = _current_sidecar()
    stage = sidecar["stage"]
    candidate = sidecar["candidate"]
    assert set(candidate) == {
        "path",
        "file_sha256",
        "candidate_id",
        "content_digest",
        "status",
        "amendment",
    }
    candidate_path = _confined_path(candidate["path"])
    assert candidate_path.parent == (
        ROOT / EXACT_REBIND_REL / stage / "candidates/C9"
    ).resolve()
    candidate_raw = candidate_path.read_bytes()
    assert candidate["file_sha256"] == hashlib.sha256(candidate_raw).hexdigest()
    candidate_value = json.loads(candidate_raw)
    assert candidate_value["content_digest"] == _digest(candidate_value)
    assert candidate["content_digest"] == candidate_value["content_digest"]
    assert SHA256.fullmatch(candidate["candidate_id"])
    assert candidate["candidate_id"] == candidate_value["candidate_id"]
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"] == f"STAGE_B{12 + version}_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
    assert candidate_value["status"] == candidate["status"]
    assert candidate_value["amendment"] == candidate["amendment"]

    for reference in sidecar["tests"]:
        _assert_file_reference(reference)
    assert len(sidecar["tests"]) == 6


def test_current_sidecar_c9_3_capability_spec_and_manifest_closures() -> None:
    sys.path.insert(0, str(ROOT / "main/backend"))
    try:
        from app.successor_runtime.specification.capability_cell_spec import (
            CapabilityCellSpec,
        )
        from app.successor_runtime.specification.compiler import (
            compile_capability_spec,
        )
        from app.successor_runtime.specification.runtime_kernel_abi import (
            RuntimeKernelABI,
        )
    finally:
        sys.path.pop(0)

    _, _, sidecar = _current_sidecar()
    spec_binding = next(
        binding for binding in sidecar["bindings"] if binding["kind"] == "current_c9_capability_spec"
    )
    manifest_binding = next(
        binding
        for binding in sidecar["bindings"]
        if binding["kind"] == "current_c9_capability_spec_build_manifest"
    )
    assert set(spec_binding) == {"kind", "path", "file_sha256", "bytes", "lines", "cell_id"}
    assert set(manifest_binding) == {"kind", "path", "file_sha256", "bytes", "lines", "cell_id"}
    assert spec_binding["cell_id"] == manifest_binding["cell_id"] == "C9.3"
    spec_raw = _assert_file_reference(
        {key: value for key, value in spec_binding.items() if key not in {"kind", "cell_id"}}
    )
    manifest_raw = _assert_file_reference(
        {key: value for key, value in manifest_binding.items() if key not in {"kind", "cell_id"}}
    )
    spec = CapabilityCellSpec.from_dict(json.loads(spec_raw))
    manifest = json.loads(manifest_raw)
    compiled = compile_capability_spec(
        spec, RuntimeKernelABI.from_dict(manifest["runtime_kernel_abi"])
    )
    assert manifest["cell_id"] == "C9.3"
    assert manifest["candidate_created"] is False
    assert all(value is False for value in manifest["authority_ceiling"].values())
    assert compiled == manifest
