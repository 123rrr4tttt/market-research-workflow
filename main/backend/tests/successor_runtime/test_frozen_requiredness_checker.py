import json
from pathlib import Path

from scripts.check_successor_frozen_requiredness import check

TOPIC = Path(__file__).resolve().parents[4] / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)


def test_frozen_v1_schema_exposes_the_requiredness_contradiction() -> None:
    report = check(
        TOPIC / "10_functorial-successor-domain-contract-snapshot.v1.json",
        TOPIC / "12_functorial-successor-first-specimen-schema-bundle.v1.schema.json",
    )
    assert not report["ok"]
    missing = {(item["type_id"], item["field"]) for item in report["missing"]}
    assert ("ResearchIntent.v1", "audience_or_use") in missing
    assert ("EvidenceQualification.v1", "validity") in missing
    assert ("Claim.v1", "scope") in missing


def test_v11_normative_schema_closes_the_requiredness_contradiction() -> None:
    report = check(
        TOPIC / "10_functorial-successor-domain-contract-snapshot.v1.json",
        TOPIC / "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json",
    )
    assert report["ok"], report["missing"]
    assert not report["representation_mapping_issues"]
    assert not report["schema_type_issues"]


def test_checker_rejects_evidence_type_and_nullability_drift(tmp_path: Path) -> None:
    schema = json.loads(
        (
            TOPIC
            / "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json"
        ).read_text()
    )
    evidence = schema["$defs"]["evidenceQualification"]
    evidence["properties"]["material_ref"] = {"type": "object"}
    evidence["properties"]["claim_ref"] = {"type": "string"}
    evidence["properties"]["validity"] = {"type": "string"}
    candidate = tmp_path / "candidate.schema.json"
    candidate.write_text(json.dumps(schema), encoding="utf-8")

    report = check(
        TOPIC / "10_functorial-successor-domain-contract-snapshot.v1.json",
        candidate,
        TOPIC
        / "17_functorial-successor-requiredness-correction.freeze-amendment.v1.json",
    )
    assert not report["ok"]
    paths = {item["path"] for item in report["schema_type_issues"]}
    assert "$defs.evidenceQualification.properties.material_ref.$ref" in paths
    assert "$defs.evidenceQualification.properties.claim_ref.type" in paths
    assert "$defs.evidenceQualification.properties.validity.type" in paths


def test_checker_rejects_representation_mapping_drift(tmp_path: Path) -> None:
    amendment = json.loads(
        (
            TOPIC
            / "17_functorial-successor-requiredness-correction.freeze-amendment.v1.json"
        ).read_text()
    )
    amendment["representation_mappings"]["MaterialRef.snapshot_value_ref"] = (
        "materialRef.snapshot_value_ref"
    )
    candidate_amendment = tmp_path / "amendment.json"
    candidate_amendment.write_text(json.dumps(amendment), encoding="utf-8")

    report = check(
        TOPIC / "10_functorial-successor-domain-contract-snapshot.v1.json",
        TOPIC / "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json",
        candidate_amendment,
    )
    assert not report["ok"]
    assert report["representation_mapping_issues"][0]["reason"] == "MAPPING_MISMATCH"
