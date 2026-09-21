from __future__ import annotations

import json
import re
from pathlib import Path

from app.successor_runtime.capabilities.c8_graph_projection_contribution import (
    C8_4_FAILURE_CODES,
)
from mrw_functorial_kit.core.c8_semantics import (
    c8_graph_failures,
    c8_operation_kinds,
    c8_report_delivery_failures,
    c8_typed_knowledge_failures,
    c8_writing_failures,
)


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / "main/backend/app/successor_runtime/capabilities/c8_program.py"
CONTRIBUTION = ROOT / (
    "main/backend/app/successor_runtime/capabilities/"
    "c8_graph_projection_contribution.py"
)


def _quoted_members(section: str) -> tuple[str, ...]:
    if section == "C8.4":
        return C8_4_FAILURE_CODES
    source = PROGRAM.read_text(encoding="utf-8")
    profile = source.split("def _failure_profile", 1)[1].split(
        "def _authority_profile", 1
    )[0]
    match = re.search(rf'"{re.escape(section)}": \((.*?)\),', profile, re.DOTALL)
    assert match is not None
    return tuple(re.findall(r'"([A-Z0-9_]+)"', match.group(1)))


def test_INVARIANT__c8_operation_kinds_match_static_runtime_constants() -> None:
    source = PROGRAM.read_text(encoding="utf-8") + CONTRIBUTION.read_text(
        encoding="utf-8"
    )
    constants = re.findall(
        r'^(?:C8_(?:1_KIND|2_COMPOSE_KIND|2_STAGE_KIND|3_KIND|4_KIND|VERIFY_KIND|'
        r'ADMISSION_KIND|DELIVERY_INTENT_PREPARE_KIND)|DELIVERY_INTERNAL_EXPORT_KIND) '
        r'= "([^"]+)"',
        source,
        re.MULTILINE,
    )
    assert len(constants) == len(set(constants)) == 9
    assert len(c8_operation_kinds.members) == len(set(c8_operation_kinds.members)) == 9
    assert set(c8_operation_kinds.members) == set(constants)


def test_INVARIANT__c8_failure_families_match_runtime_profiles() -> None:
    assert c8_typed_knowledge_failures.codes == _quoted_members("C8.1")
    assert c8_writing_failures.codes == _quoted_members("C8.2")
    assert c8_report_delivery_failures.codes == _quoted_members("C8.3")
    assert c8_graph_failures.codes == _quoted_members("C8.4")


def test_INVARIANT__c8_registry_entries_match_kit_declarations() -> None:
    vocabularies = json.loads((ROOT / "registries/vocabularies.json").read_text())[
        "entries"
    ]
    vocabulary_members = {entry["name"]: tuple(entry["members"]) for entry in vocabularies}
    assert vocabulary_members["c8.operation.kind"] == c8_operation_kinds.members

    failures = json.loads((ROOT / "registries/failures.json").read_text())["entries"]
    failure_codes = {entry["name"]: tuple(entry["codes"]) for entry in failures}
    expected = {
        "c8.typed_knowledge.failure": c8_typed_knowledge_failures,
        "c8.writing.failure": c8_writing_failures,
        "c8.graph.failure": c8_graph_failures,
        "c8.report_delivery.failure": c8_report_delivery_failures,
    }
    for name, family in expected.items():
        assert failure_codes[name] == family.codes


def test_INVARIANT__c8_sketches_have_existing_test_witnesses() -> None:
    sketches = json.loads((ROOT / "sketches.json").read_text())["entries"]
    c8_entries = [
        entry
        for entry in sketches
        if any("/c8_" in obj.get("owner", "") for obj in entry["objects"])
    ]
    assert len(c8_entries) == 2

    witness_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "main/backend/tests/successor_runtime").glob("test_*c8*.py")
    )
    for entry in c8_entries:
        assert entry["failures"]
        for equation in entry["equations"]:
            assert equation["class"] == "testable"
            witness = equation["witness"].removeprefix("test:")
            assert f"def {witness}(" in witness_sources, witness
