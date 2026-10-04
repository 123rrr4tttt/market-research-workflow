from __future__ import annotations

import json
import re
from pathlib import Path

from app.successor_runtime.capabilities import material_ingest_movements as c7
from mrw_functorial_kit.core.material_semantics import MATERIAL_INGEST_FAILURE_CODES, MATERIAL_INGEST_STAGE_FAILURE_CODES, MATERIAL_INGEST_TERMINAL_FAILURE_CODES, material_digestion_alternative_codec, material_digestion_alternatives, material_ingest_content_formats, material_ingest_failures, material_ingest_input_kinds, material_ingest_movement_dispositions, read_historical_c7_alternative_codec, read_historical_c7_content_format_codec, read_historical_c7_input_kind_codec, read_historical_c7_movement_disposition_codec, read_historical_c7_terminal_failure_family, read_historical_c7_terminal_outcome_codec


ROOT = Path(__file__).resolve().parents[1]


def test_INVARIANT__runtime_constants_share_material_authority() -> None:
    assert c7.MATERIAL_INGEST_ALTERNATIVES is material_digestion_alternatives.members
    assert c7.MATERIAL_INGEST_INPUT_KINDS is material_ingest_input_kinds.members
    assert c7.MATERIAL_INGEST_CONTENT_FORMATS is material_ingest_content_formats.members
    assert material_ingest_movement_dispositions.members == (
        "PRESERVED_AS",
        "MOVED_TO",
        "REIMPLEMENTED_AS",
        "DECLARED_LOSS",
        "EXPLICITLY_REJECTED",
        "UNASSIGNED_BLOCKER",
    )
    assert c7.MATERIAL_INGEST_TERMINAL_FAILURE_CODES == MATERIAL_INGEST_TERMINAL_FAILURE_CODES


def test_INVARIANT__material_registry_members_match_authority() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())["entries"]
    by_name = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    assert by_name["material.digestion.alternatives"] == material_digestion_alternatives.members
    assert by_name["material.ingest.input_kind"] == material_ingest_input_kinds.members
    assert by_name["material.ingest.content_format"] == material_ingest_content_formats.members
    assert by_name["material.ingest.movement_disposition"] == material_ingest_movement_dispositions.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_by_name = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_by_name["material.ingest.failure"] == material_ingest_failures.codes


def test_INVARIANT__material_ingest_failure_family_is_closed_and_complete() -> None:
    assert material_ingest_failures.codes == MATERIAL_INGEST_FAILURE_CODES
    assert MATERIAL_INGEST_FAILURE_CODES == (
        *MATERIAL_INGEST_STAGE_FAILURE_CODES,
        *MATERIAL_INGEST_TERMINAL_FAILURE_CODES,
    )
    assert len(set(material_ingest_failures.codes)) == len(material_ingest_failures.codes)
    assert material_ingest_failures.matches(
        material_ingest_failures.fail("malformed_structured_json", "registered test failure")
    )


def test_INVARIANT__material_failure_family_covers_static_movement_codes() -> None:
    source = (
        ROOT / "main/backend/app/successor_runtime/capabilities/material_ingest_movements.py"
    ).read_text(encoding="utf-8")
    static_codes = set(re.findall(r'failure_code="([a-z0-9_]+)"', source))
    static_codes.update(re.findall(r'rejected\("([a-z0-9_]+)"', source))
    static_codes.update(re.findall(r'return "([a-z0-9_]+)"', source))
    assert static_codes
    assert static_codes <= set(material_ingest_failures.codes), sorted(
        static_codes - set(material_ingest_failures.codes)
    )


def test_ROUNDTRIP__current_codec_uses_material_v2_discriminant() -> None:
    decoded = material_digestion_alternative_codec.parse(
        {"kind": "material.digestion.alternative.v2", "member": "EXTRACT"}
    )
    assert decoded == "EXTRACT"
    assert material_digestion_alternative_codec.to_wire("CHUNK") == {
        "kind": "material.digestion.alternative.v2",
        "member": "CHUNK",
    }

    rejected = material_digestion_alternative_codec.parse(
        {"kind": "material.digestion.alternative.v2", "member": "NOT_A_MEMBER"}
    )
    assert getattr(rejected, "failure", False) is True


def test_HISTORY_PRESERVED__retired_c7_codec_bytes_and_failure_metadata_are_exact() -> None:
    historical_codecs = (
        (
            read_historical_c7_alternative_codec(),
            "c7.digestion.alternative",
            "c7.digestion.alternative.v1",
            "EXTRACT",
        ),
        (
            read_historical_c7_input_kind_codec(),
            "c7.ingest.input_kind",
            "c7.ingest.input_kind.v1",
            "raw_import",
        ),
        (
            read_historical_c7_content_format_codec(),
            "c7.ingest.content_format",
            "c7.ingest.content_format.v1",
            "markdown",
        ),
        (
            read_historical_c7_movement_disposition_codec(),
            "c7.movement.disposition",
            "c7.movement.disposition.v1",
            "MOVED_TO",
        ),
        (
            read_historical_c7_terminal_outcome_codec(),
            "c7.movement.terminal_outcome",
            "c7.movement.terminal_outcome.v1",
            "REJECTED",
        ),
    )
    for codec, name, discriminant, member in historical_codecs:
        assert (codec.name, codec.discriminant) == (name, discriminant)
        assert codec.serialize(member) == (
            f'{{"kind":"{discriminant}","member":"{member}"}}'
        )
        assert codec.parse({"kind": discriminant, "member": member}) == member

    historical_failure = read_historical_c7_terminal_failure_family()
    assert historical_failure.name == "c7.movement.terminal_failure"
    assert historical_failure.codes == MATERIAL_INGEST_TERMINAL_FAILURE_CODES
