"""Authority-sidecar tests for the current immutable C7 evidence bindings."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
SIDECAR_PATH = (
    ROOT
    / "docs/governance/generated-evidence-authority-sidecar.c7.v1.json"
)
SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c7.v1"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    assert isinstance(value, dict)
    return value


def _canonical_fragment_digest(value: dict[str, Any]) -> str:
    body = {key: item for key, item in value.items() if key != "content_digest"}
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assert_confined(relative_path: str) -> Path:
    path = (ROOT / relative_path).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise AssertionError(f"path escapes repository root: {path}") from exc
    return path


def _assert_binding_shape(binding: dict[str, Any]) -> None:
    assert isinstance(binding.get("kind"), str) and binding["kind"]
    path = _assert_confined(binding["path"])
    assert path.is_file()
    assert SHA256.fullmatch(binding["external_sha256"])
    internal = binding["internal_digest"]
    assert isinstance(internal, dict)
    assert set(internal) >= {"field", "algorithm", "value"}
    assert SHA256.fullmatch(internal["value"])


def test_sidecar_schema_and_authority_ceiling() -> None:
    sidecar = _load_json(SIDECAR_PATH)
    assert set(sidecar) == {
        "schema",
        "sidecar_id",
        "mutability",
        "derived_as",
        "domain_authoritative",
        "artifact_identity_authoritative",
        "authority_direction",
        "authority",
        "authority_ceiling",
        "bindings",
    }
    assert sidecar["schema"] == SCHEMA
    assert sidecar["mutability"] == "immutable"
    assert sidecar["derived_as"] == "view"
    assert sidecar["domain_authoritative"] is False
    assert sidecar["artifact_identity_authoritative"] is True
    assert sidecar["authority_direction"] == (
        "frozen inputs -> generated evidence"
    )
    assert sidecar["authority"] == {
        "reverse_write": False,
        "promotion": False,
        "candidate_claim": False,
    }
    assert sidecar["authority_ceiling"] == {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
    }
    assert isinstance(sidecar["bindings"], list)
    assert len(sidecar["bindings"]) == 5
    assert len({item["path"] for item in sidecar["bindings"]}) == 5
    for binding in sidecar["bindings"]:
        _assert_binding_shape(binding)


def test_current_c7_fragment_external_and_internal_digests_close() -> None:
    sidecar = _load_json(SIDECAR_PATH)
    binding = next(
        item
        for item in sidecar["bindings"]
        if item["kind"] == "current_c7_family_fragment"
    )
    path = _assert_confirmed_path(binding["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == binding["external_sha256"]
    fragment = _load_json(path)
    assert fragment["schema"] == "mrw.functorial_successor.p4_fragment.v1"
    assert fragment["family"] == "C7"
    assert fragment["phase"] == "P4"
    assert (
        fragment["content_digest"]
        == binding["internal_digest"]["value"]
        == _canonical_fragment_digest(fragment)
    )


def _assert_confirmed_path(relative_path: str) -> Path:
    path = _assert_confined(relative_path)
    return path


def test_c7_1_through_c7_4_manifest_identity_closes() -> None:
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

    sidecar = _load_json(SIDECAR_PATH)
    bindings = {
        item["cell_id"]: item
        for item in sidecar["bindings"]
        if item["kind"] == "capability_spec_build_manifest"
    }
    assert set(bindings) == {"C7.1", "C7.2", "C7.3", "C7.4"}
    for cell_id in ("C7.1", "C7.2", "C7.3", "C7.4"):
        binding = bindings[cell_id]
        path = _assert_confirmed_path(binding["path"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == (
            binding["external_sha256"]
        )
        manifest = _load_json(path)
        assert manifest["schema"] == (
            "mrw.functorial_successor.capability_spec_build_manifest.v1"
        )
        assert manifest["cell_id"] == cell_id
        assert manifest["family_id"] == "C7"
        assert manifest["candidate_created"] is False
        assert set(manifest["authority_ceiling"].values()) == {False}

        expected_internal = manifest["artifact_identity"]["artifact_digest"]
        expected_payload = manifest["artifact_identity"]["generated_payload_digest"]
        assert expected_payload == manifest["artifact_identity"][
            "generated_bytes_sha256"
        ]
        assert binding["internal_digest"]["value"] == expected_internal
        assert binding["internal_digest"]["generated_payload_digest"] == (
            expected_payload
        )

        spec_path = path.parent.parent / "capability-specs" / f"{cell_id}.v1.json"
        spec = CapabilityCellSpec.from_dict(_load_json(spec_path))
        abi = RuntimeKernelABI.from_dict(manifest["runtime_kernel_abi"])
        compiled = compile_capability_spec(spec, abi)
        assert compiled == manifest
        assert manifest["semantic_identity"][
            "does_not_replace_exact_artifact_identity"
        ] is True
