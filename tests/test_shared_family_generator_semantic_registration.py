from __future__ import annotations

import json
from pathlib import Path

from functorial_kit import is_failure

from mrw_functorial_kit.core.shared_family_generator_semantics import (
    shared_family_generator_failures,
    shared_family_p3_fragment_codec,
    shared_family_p4_fragment_codec,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    / "2026-08-30-functorial-successor-migration/evidence"
)
P3_FRAGMENT = EVIDENCE / "p3-fragments/C2.json"
P4_FRAGMENT = EVIDENCE / "p4-fragments/C7.json"


def test_INVARIANT__shared_family_fragment_registry_consistency() -> None:
    codecs = json.loads((ROOT / "registries/codecs.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    codec_discriminants = {entry["name"]: entry["discriminant"] for entry in codecs}
    expected = {
        "shared.family.generator.p3_fragment": shared_family_p3_fragment_codec,
        "shared.family.generator.p4_fragment": shared_family_p4_fragment_codec,
    }
    for name, codec in expected.items():
        assert codec_discriminants[name] == codec.discriminant

    failures = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_codes["shared.family.generator.failure"] == (
        shared_family_generator_failures.codes
    )

    sketches = json.loads((ROOT / "sketches.json").read_text(encoding="utf-8"))["entries"]
    sketch = next(
        entry
        for entry in sketches
        if any(obj["name"] == "P3SharedFamilyFragment" for obj in entry["objects"])
    )
    assert sketch["derived"] == {"authoritative": False, "derived_as": "view"}


def test_INVARIANT__shared_family_exact_keys_match_disk_representatives() -> None:
    for codec, path in (
        (shared_family_p3_fragment_codec, P3_FRAGMENT),
        (shared_family_p4_fragment_codec, P4_FRAGMENT),
    ):
        fragment = json.loads(path.read_text(encoding="utf-8"))
        assert fragment[codec.discriminant_key] == codec.discriminant
        assert set(fragment) == set(codec.keys)
        parsed = codec.parse(fragment)
        assert not is_failure(parsed)
        assert parsed is fragment


def test_INVARIANT__shared_family_identity_wire_projection_is_lossless() -> None:
    for codec, path in (
        (shared_family_p3_fragment_codec, P3_FRAGMENT),
        (shared_family_p4_fragment_codec, P4_FRAGMENT),
    ):
        before = path.read_bytes()
        fragment = json.loads(before.decode(encoding="utf-8"))
        assert codec.to_wire(fragment) is fragment
        assert json.loads(codec.serialize(fragment)) == fragment
        assert path.read_bytes() == before


def test_FAILURE_PRESERVED__shared_family_foreign_discriminant_fails_closed() -> None:
    fragment = json.loads(P4_FRAGMENT.read_text(encoding="utf-8"))
    drifted = dict(fragment)
    drifted["schema"] = "mrw.functorial_successor.p4_fragment.v0"
    result = shared_family_p4_fragment_codec.parse(drifted)
    assert is_failure(result)
    assert result.code == "CODEC_UNKNOWN_DISCRIMINANT"


def test_FAILURE_PRESERVED__shared_family_fragment_invariant_fails_closed() -> None:
    fragment = json.loads(P3_FRAGMENT.read_text(encoding="utf-8"))
    drifted = dict(fragment)
    drifted["family"] = None
    result = shared_family_p3_fragment_codec.parse(drifted)
    assert is_failure(result)
    assert shared_family_generator_failures.matches(result)
    assert result.code == "fragment_invariant_invalid"
