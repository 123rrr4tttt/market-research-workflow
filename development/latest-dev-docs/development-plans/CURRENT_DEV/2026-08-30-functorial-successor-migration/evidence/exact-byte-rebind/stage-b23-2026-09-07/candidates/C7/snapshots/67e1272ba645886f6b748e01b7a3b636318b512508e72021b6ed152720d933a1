from __future__ import annotations

import json
import re
from pathlib import Path

from app.successor_runtime.capabilities import ingest_c7_movements as c7
from mrw_functorial_kit.core.c7_semantics import (
    c7_alternative_codec,
    c7_alternatives,
    c7_content_formats,
    c7_input_kinds,
    c7_movement_dispositions,
    c7_terminal_failures,
)


ROOT = Path(__file__).resolve().parents[1]


def test_INVARIANT__c7_runtime_constants_match_kit_vocabularies() -> None:
    assert c7_alternatives.members == c7.C7_ALTERNATIVES
    assert c7_input_kinds.members == c7.C7_INPUT_KINDS
    assert c7_content_formats.members == c7.C7_CONTENT_FORMATS
    assert c7_movement_dispositions.members == (
        "PRESERVED_AS",
        "MOVED_TO",
        "REIMPLEMENTED_AS",
        "DECLARED_LOSS",
        "EXPLICITLY_REJECTED",
        "UNASSIGNED_BLOCKER",
    )


def test_INVARIANT__c7_registry_members_match_kit_declarations() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())["entries"]
    by_name = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    assert by_name["c7.digestion.alternatives"] == c7_alternatives.members
    assert by_name["c7.ingest.input_kind"] == c7_input_kinds.members
    assert by_name["c7.ingest.content_format"] == c7_content_formats.members
    assert by_name["c7.movement.disposition"] == c7_movement_dispositions.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_by_name = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    assert failure_by_name["c7.movement.terminal_failure"] == c7_terminal_failures.codes


def test_INVARIANT__registered_c7_failure_family_is_closed_and_nonempty() -> None:
    assert c7_terminal_failures.codes
    assert len(set(c7_terminal_failures.codes)) == len(c7_terminal_failures.codes)
    assert c7_terminal_failures.matches(
        c7_terminal_failures.fail(
            "malformed_structured_json", "registered test failure"
        )
    )


def test_INVARIANT__registered_c7_failure_family_covers_static_source_codes() -> None:
    source = (ROOT / "main/backend/app/successor_runtime/capabilities/ingest_c7_movements.py").read_text(
        encoding="utf-8"
    )
    static_codes = set(re.findall(r'failure_code="([a-z0-9_]+)"', source))
    static_codes.update(re.findall(r'rejected\("([a-z0-9_]+)"', source))
    static_codes.update(re.findall(r'return "([a-z0-9_]+)"', source))
    assert static_codes
    assert static_codes <= set(c7_terminal_failures.codes), sorted(
        static_codes - set(c7_terminal_failures.codes)
    )



def test_ROUNDTRIP__registered_c7_token_codecs_reject_unknown_members() -> None:
    decoded = c7_alternative_codec.parse({"kind": "c7.digestion.alternative.v1", "member": "EXTRACT"})
    assert decoded == "EXTRACT"
    wire = c7_alternative_codec.to_wire("CHUNK")
    assert wire == {"kind": "c7.digestion.alternative.v1", "member": "CHUNK"}

    rejected = c7_alternative_codec.parse(
        {"kind": "c7.digestion.alternative.v1", "member": "NOT_A_MEMBER"}
    )
    assert getattr(rejected, "failure", False) is True
