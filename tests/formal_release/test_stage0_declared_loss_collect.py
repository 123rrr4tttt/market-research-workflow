from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = (
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release"
    / "stage0-evidence/declared-loss-collect.v1.json"
)
DECISIONS = {
    "ACCEPTED_EXPLICIT_LOSS",
    "IMPLEMENTED",
    "IMPLEMENTATION_REQUIRED",
    "NOT_APPLICABLE",
}


def _load() -> dict[str, object]:
    with EVIDENCE_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    assert isinstance(payload, dict)
    return payload


def test_JSON__stage0_collect_loss_record_is_parseable_and_versioned() -> None:
    payload = _load()
    assert payload["schema"] == "mrw.formal_release.stage0.declared_loss_collect.v1"
    assert payload["schema_version"] == "mrw.stage0.declared-loss-collect.v1"
    assert payload["version"] == "1.0.0"
    assert payload["stage"] == "STAGE_0B"
    assert payload["authoritative"] is False
    assert payload["derived_as"] == "stage0_declared_loss_fact_review"
    assert isinstance(payload["items"], list) and payload["items"]


def test_COMPLETENESS__each_collect_loss_has_required_semantic_fields_and_unique_id() -> None:
    payload = _load()
    items = payload["items"]
    assert isinstance(items, list)
    ids: list[str] = []
    required = {
        "id",
        "source_object",
        "source_morphism",
        "retained",
        "lost",
        "affected_callers",
        "alternative_path",
        "witness",
        "decision",
    }
    for item in items:
        assert isinstance(item, dict)
        assert required <= item.keys()
        item_id = item["id"]
        assert isinstance(item_id, str) and item_id.strip()
        ids.append(item_id)
        assert isinstance(item["retained"], list) and item["retained"]
        assert isinstance(item["lost"], list) and item["lost"]
        assert isinstance(item["alternative_path"], str) and item["alternative_path"].strip()
        assert item["decision"] in DECISIONS
    assert len(ids) == len(set(ids))


def test_TRACEABILITY__all_collect_source_caller_and_witness_paths_exist() -> None:
    payload = _load()
    items = payload["items"]
    assert isinstance(items, list)
    for item in items:
        for reference in (item["source_object"], item["source_morphism"]):
            assert isinstance(reference, dict)
            path = reference["path"]
            assert isinstance(path, str) and (ROOT / path).is_file(), path
            assert isinstance(reference.get("symbol"), str) and reference["symbol"].strip()

        callers = item["affected_callers"]
        assert isinstance(callers, list) and callers
        for caller in callers:
            assert isinstance(caller, dict)
            path = caller["path"]
            assert isinstance(path, str) and (ROOT / path).is_file(), path
            assert isinstance(caller.get("symbol"), str) and caller["symbol"].strip()

        witnesses = item["witness"]
        assert isinstance(witnesses, list) and witnesses
        for witness in witnesses:
            assert isinstance(witness, dict)
            path = witness["path"]
            assert isinstance(path, str) and (ROOT / path).is_file(), path
            test_name = witness.get("test")
            assert isinstance(test_name, str) and test_name.strip()


def test_DECISION_ACCOUNTING__counts_match_items_and_no_parity_disguise() -> None:
    payload = _load()
    items = payload["items"]
    counts = payload["decision_counts"]
    assert isinstance(items, list) and isinstance(counts, dict)
    observed = {decision: 0 for decision in DECISIONS}
    for item in items:
        decision = item["decision"]
        assert decision in DECISIONS
        observed[decision] += 1
        assert item["retained"] and item["lost"]
    assert counts == observed
    assert all("parity" not in str(item.get("decision", "")).lower() for item in items)


def test_SCOPE__record_is_additive_non_authoritative_and_mutation_free() -> None:
    payload = _load()
    assert payload["write_scope"]["mode"] == "ADDITIVE_EVIDENCE_ONLY"
    assert payload["write_scope"]["allowed_files"] == [
        "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage0-evidence/declared-loss-collect.v1.json",
        "tests/formal_release/test_stage0_declared_loss_collect.py",
    ]
    assert all(value is False for value in payload["authority_ceiling"].values())
    assert all(payload["write_scope"][key] is False for key in payload["write_scope"] if key.endswith("_mutation"))
