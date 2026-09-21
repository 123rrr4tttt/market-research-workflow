from __future__ import annotations

from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

from functorial_kit.arch.gates import scan_project
from functorial_kit.arch.scan import ratchet, violation_key

from app.successor_runtime.specification.c7_p4 import (
    build_observations,
    build_rollback_observation,
)
from app.successor_runtime.specification.compiler import build_manifest_bytes
from app.successor_runtime.specification.shared_family_generator import (
    build_fragment,
    build_fragment_bytes,
)


W08B_EXACT_KEYS = {
    "derived-marked|main/backend/app/successor_runtime/specification/c7_p4.py|"
    "build_observations returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/specification/c7_p4.py|"
    "build_rollback_observation returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/specification/compiler.py|"
    "build_manifest_bytes returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/specification/shared_family_generator.py|"
    "build_fragment returns an unmarked derived value",
    "derived-marked|main/backend/app/successor_runtime/specification/shared_family_generator.py|"
    "build_fragment_bytes returns an unmarked derived value",
}
WITNESS = "test:test_w08b_specification_authority_metadata_preserves_abi"


def _return_metadata(function: object) -> str:
    return_type = get_type_hints(function, include_extras=True)["return"]
    assert get_origin(return_type) is Annotated
    metadata_args = get_args(return_type)[1:]
    metadata = next(
        arg
        for arg in metadata_args
        if isinstance(arg, str) and arg.startswith("kit:")
    )
    assert metadata.endswith(f"witness={WITNESS}")
    return metadata


def test_w08b_specification_authority_metadata_preserves_abi() -> None:
    assert len(W08B_EXACT_KEYS) == 5

    observations = build_observations("C7.1")
    assert len(observations) == 2
    assert all(isinstance(item, dict) for item in observations)
    rollback = build_rollback_observation("C7.1", observations[0], observations[1])
    assert rollback["rollback_digest"]

    generated = (
        build_observations,
        build_rollback_observation,
        build_fragment,
    )
    for function in generated:
        metadata = _return_metadata(function)
        assert metadata.startswith("kit:non-authoritative")
        assert "derived_as=generated_evidence" in metadata
        assert "fact_source=" in metadata

    prepared = (build_manifest_bytes, build_fragment_bytes)
    for function in prepared:
        metadata = _return_metadata(function)
        assert metadata.startswith("kit:prepared-command")
        assert "effect_boundary=" in metadata

    assert build_manifest_bytes({"a": 1}).endswith(b'\n')
    assert build_fragment_bytes({"a": 1}).endswith(b'\n')


def test_w08b_exact_keys_are_removed_from_live_scan() -> None:
    root = Path(__file__).resolve().parents[4]
    scan = scan_project(root)
    result = ratchet(scan.violations, scan.baseline)

    owned_new = {
        violation_key(violation)
        for violation in result.new_violations
        if violation.file
        in {
            "main/backend/app/successor_runtime/specification/c7_p4.py",
            "main/backend/app/successor_runtime/specification/compiler.py",
            "main/backend/app/successor_runtime/specification/shared_family_generator.py",
        }
        and violation.gate == "derived-marked"
    }
    assert owned_new == set()
    assert W08B_EXACT_KEYS.isdisjoint(scan.baseline)
