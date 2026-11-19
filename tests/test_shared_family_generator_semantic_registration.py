from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from functorial_kit import Codec, is_failure

from mrw_functorial_kit.core.shared_family_generator_semantics import (
    SharedFamilyFragment,
    SharedFamilyFragmentValue,
    shared_family_generator_failures,
    shared_family_p3_fragment_codec,
    shared_family_p4_fragment_codec,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(params=["p3", "p4"])
def specimen(
    request: pytest.FixtureRequest,
) -> tuple[Codec[SharedFamilyFragment], dict[str, SharedFamilyFragmentValue]]:
    p4 = request.param == "p4"
    codec = shared_family_p4_fragment_codec if p4 else shared_family_p3_fragment_codec
    fragment: dict[str, SharedFamilyFragmentValue] = {
        "authority": {"canonical_write": False},
        "cells": [{"cell_id": "example.1", "observations": [None, "示例"]}],
        "content_digest": "0" * 64,
        "family": "example",
        "fragment_id": "example-local-specimen",
        "implementation_bindings": [],
        "open_findings": [],
        "phase": "P4" if p4 else "P3",
        "schema": "mrw.functorial_successor.p4_fragment.v1" if p4 else "mrw.functorial_successor.p3_fragment.v1",
        "source_bindings": [],
        "status": "SPECIMEN",
        "test_bindings": [],
    }
    if p4:
        fragment["lifecycle_state"] = "SPECIMEN"
    return codec, fragment


def test_INVARIANT__shared_family_fragment_registry_consistency() -> None:
    codecs = json.loads((ROOT / "registries/codecs.json").read_text(encoding="utf-8"))["entries"]
    codec_discriminants = {entry["name"]: entry["discriminant"] for entry in codecs}
    expected = {
        "shared.family.generator.p3_fragment": shared_family_p3_fragment_codec,
        "shared.family.generator.p4_fragment": shared_family_p4_fragment_codec,
    }
    for name, codec in expected.items():
        assert codec_discriminants[name] == codec.discriminant

    failures = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_codes["shared.family.generator.failure"] == (shared_family_generator_failures.codes)

    sketches = json.loads((ROOT / "sketches.json").read_text(encoding="utf-8"))["entries"]
    sketch = next(
        entry for entry in sketches if any(obj["name"] == "P3SharedFamilyFragment" for obj in entry["objects"])
    )
    assert sketch["derived"] == {"authoritative": False, "derived_as": "view"}


def test_INVARIANT__shared_family_exact_keys(
    specimen: tuple[Codec[SharedFamilyFragment], dict[str, SharedFamilyFragmentValue]],
) -> None:
    codec, fragment = specimen
    assert fragment[codec.discriminant_key] == codec.discriminant
    assert set(fragment) == set(codec.keys)
    assert codec.parse(fragment) is fragment
    for drifted in (
        {**fragment, "unexpected": True},
        {key: value for key, value in fragment.items() if key != "cells"},
    ):
        result = codec.parse(drifted)
        assert is_failure(result)
        assert result.code == "CODEC_INVALID_KEYS"


def test_INVARIANT__shared_family_identity_wire_projection_is_lossless(
    specimen: tuple[Codec[SharedFamilyFragment], dict[str, SharedFamilyFragmentValue]],
) -> None:
    codec, fragment = specimen
    before = copy.deepcopy(fragment)
    assert codec.to_wire(fragment) is fragment
    serialized = codec.serialize(fragment)
    assert not is_failure(serialized)
    assert isinstance(serialized, str)
    assert json.loads(serialized) == before
    assert codec.parse(json.loads(serialized)) == before
    assert fragment == before


def test_FAILURE_PRESERVED__shared_family_foreign_discriminant_fails_closed(
    specimen: tuple[Codec[SharedFamilyFragment], dict[str, SharedFamilyFragmentValue]],
) -> None:
    codec, fragment = specimen
    drifted = {**fragment, "schema": "foreign.fragment.v1"}
    result = codec.parse(drifted)
    assert is_failure(result)
    assert result.code == "CODEC_UNKNOWN_DISCRIMINANT"


def test_FAILURE_PRESERVED__shared_family_fragment_invariant_fails_closed(
    specimen: tuple[Codec[SharedFamilyFragment], dict[str, SharedFamilyFragmentValue]],
) -> None:
    codec, fragment = specimen
    drifted = {**fragment, "family": None}
    result = codec.parse(drifted)
    assert is_failure(result)
    assert shared_family_generator_failures.matches(result)
    assert result.code == "fragment_invariant_invalid"
