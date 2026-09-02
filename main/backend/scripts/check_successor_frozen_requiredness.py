from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REQUIREDNESS_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "ResearchIntent.v1": (
        "researchIntent",
        (
            "purpose",
            "audience_or_use",
            "scope",
            "as_of",
            "constraints",
            "expected_delivery",
        ),
    ),
    "Inquiry.v1": (
        "inquiry",
        (
            "question_or_hypothesis",
            "acceptance_conditions",
            "stop_conditions",
            "uncertainty_ceiling",
        ),
    ),
    "ResearchPlan.v1": (
        "researchPlan",
        ("inquiry_ref", "work_items", "budget", "deadline", "replan_policy"),
    ),
    "SourceRef.v1": (
        "sourceRef",
        ("owner_id", "locator", "source_class", "access_profile_ref", "observed_at"),
    ),
    "Claim.v1": (
        "claim",
        (
            "statement_ref",
            "scope",
            "support_relation_refs",
            "contradiction_relation_refs",
            "uncertainty_profile_ref",
            "lifecycle_state",
        ),
    ),
    "Gap.v1": (
        "gap",
        (
            "inquiry_ref",
            "requirement",
            "reason",
            "missing_evidence_or_decision",
            "reopen_policy",
            "closure_condition",
        ),
    ),
    "ResearchArtifact.v1": (
        "researchArtifact",
        (
            "content_ref",
            "content_digest",
            "claim_closure",
            "evidence_relation_closure",
            "citation_closure",
            "format",
            "revision",
            "lifecycle_state",
        ),
    ),
    "DeliveryIntent.v1": (
        "deliveryIntent",
        (
            "artifact_ref",
            "audience",
            "channel",
            "format",
            "approval_refs",
            "authority_digest",
            "idempotency_key",
            "irreversibility_profile",
        ),
    ),
    "DeliveryAttempt.v1": (
        "deliveryAttempt",
        (
            "attempt_id",
            "delivery_intent_ref",
            "handler_binding_digest",
            "effect_disposition",
        ),
    ),
    "DeliveryReceiptRef.v1": (
        "deliveryReceiptRef",
        (
            "delivery_intent_ref",
            "attempt_ref",
            "provider_locator",
            "receipt_digest",
            "outcome_time",
        ),
    ),
    "EvidenceQualification.v1": (
        "evidenceQualification",
        (
            "qualification_id",
            "material_ref",
            "inquiry_ref",
            "claim_ref",
            "direction",
            "scope_statement_ref",
            "uncertainty_profile_ref",
            "validity",
            "verifier_profile_ref",
            "provenance_closure_digest",
        ),
    ),
}

AMENDMENT_NAME = (
    "17_functorial-successor-requiredness-correction.freeze-amendment.v1.json"
)
EXPECTED_REPRESENTATION_MAPPINGS = {
    "SourceRef.access_profile": "sourceRef.access_profile_ref",
    "EvidenceQualification.optional_claim_ref": "evidenceQualification.claim_ref required but nullable",
    "EvidenceQualification.validity": "evidenceQualification.validity object",
    "ResearchPlan.ordered_or_partial_order_work": "researchPlan.work_items with depends_on edges",
    "MaterialRef.snapshot_value_ref": "materialRef.snapshot.value_ref",
    "MaterialRef.source_observed_hash": "materialRef.snapshot.observed_text_hash",
    "MaterialRef.source_observed_updated_at": "materialRef.snapshot.observed_updated_at",
    "DeliveryAttempt.intent_ref": "deliveryAttempt.delivery_intent_ref",
    "DeliveryReceiptRef.intent_ref": "deliveryReceiptRef.delivery_intent_ref",
}


def _issue(
    path: str, reason: str, expected: object, actual: object
) -> dict[str, object]:
    return {"path": path, "reason": reason, "expected": expected, "actual": actual}


def _property(schema: dict[str, Any], definition: str, *path: str) -> Any:
    value: Any = schema.get("$defs", {}).get(definition, {}).get("properties", {})
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _validate_representation_shapes(schema: dict[str, Any]) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []

    def expect(path: str, actual: object, expected: object) -> None:
        if actual != expected:
            issues.append(_issue(path, "SCHEMA_SHAPE_MISMATCH", expected, actual))

    expect(
        "$defs.ref.type", schema.get("$defs", {}).get("ref", {}).get("type"), "string"
    )
    expect(
        "$defs.digest.pattern",
        schema.get("$defs", {}).get("digest", {}).get("pattern"),
        "^[0-9a-f]{64}$",
    )

    source = schema.get("$defs", {}).get("sourceRef", {})
    expect(
        "$defs.sourceRef.required.access_profile_ref",
        "access_profile_ref" in source.get("required", ()),
        True,
    )
    access_type = _property(schema, "sourceRef", "access_profile_ref", "type")
    if access_type != "string" and not (
        isinstance(access_type, list) and "string" in access_type
    ):
        issues.append(
            _issue(
                "$defs.sourceRef.properties.access_profile_ref.type",
                "JSON_TYPE_MISMATCH",
                "string-capable",
                access_type,
            )
        )

    evidence = schema.get("$defs", {}).get("evidenceQualification", {})
    expect("$defs.evidenceQualification.type", evidence.get("type"), "object")
    expect(
        "$defs.evidenceQualification.additionalProperties",
        evidence.get("additionalProperties"),
        False,
    )
    expect(
        "$defs.evidenceQualification.properties.material_ref.$ref",
        _property(schema, "evidenceQualification", "material_ref", "$ref"),
        "#/$defs/ref",
    )
    expect(
        "$defs.evidenceQualification.required.claim_ref",
        "claim_ref" in evidence.get("required", ()),
        True,
    )
    expect(
        "$defs.evidenceQualification.properties.claim_ref.type",
        _property(schema, "evidenceQualification", "claim_ref", "type"),
        ["string", "null"],
    )
    validity = _property(schema, "evidenceQualification", "validity") or {}
    expect(
        "$defs.evidenceQualification.properties.validity.type",
        validity.get("type"),
        "object",
    )
    expect(
        "$defs.evidenceQualification.properties.validity.required",
        sorted(validity.get("required", ())),
        ["valid_from", "valid_to"],
    )
    expect(
        "$defs.evidenceQualification.properties.validity.additionalProperties",
        validity.get("additionalProperties"),
        False,
    )
    for field in ("valid_from", "valid_to"):
        field_schema = validity.get("properties", {}).get(field, {})
        expect(
            f"$defs.evidenceQualification.properties.validity.properties.{field}.type",
            field_schema.get("type"),
            ["string", "null"],
        )
        expect(
            f"$defs.evidenceQualification.properties.validity.properties.{field}.format",
            field_schema.get("format"),
            "date-time",
        )

    work_items = _property(schema, "researchPlan", "work_items") or {}
    depends_on = work_items.get("items", {}).get("properties", {}).get("depends_on", {})
    expect(
        "$defs.researchPlan.properties.work_items.type", work_items.get("type"), "array"
    )
    expect(
        "$defs.researchPlan.properties.work_items.items.properties.depends_on.type",
        depends_on.get("type"),
        "array",
    )
    expect(
        "$defs.researchPlan.properties.work_items.items.properties.depends_on.items.$ref",
        depends_on.get("items", {}).get("$ref"),
        "#/$defs/ref",
    )

    expect(
        "$defs.materialRef.properties.snapshot.$ref",
        _property(schema, "materialRef", "snapshot", "$ref"),
        "#/$defs/capturedMaterialSnapshot",
    )
    snapshot_expectations = {
        "value_ref": ("$ref", "#/$defs/ref"),
        "observed_text_hash": ("type", ["string", "null"]),
        "observed_updated_at": ("type", "string"),
    }
    for field, (key, expected) in snapshot_expectations.items():
        expect(
            f"$defs.capturedMaterialSnapshot.properties.{field}.{key}",
            _property(schema, "capturedMaterialSnapshot", field, key),
            expected,
        )
    expect(
        "$defs.capturedMaterialSnapshot.properties.observed_updated_at.format",
        _property(schema, "capturedMaterialSnapshot", "observed_updated_at", "format"),
        "date-time",
    )

    for definition in ("deliveryAttempt", "deliveryReceiptRef"):
        item = schema.get("$defs", {}).get(definition, {})
        expect(
            f"$defs.{definition}.required.delivery_intent_ref",
            "delivery_intent_ref" in item.get("required", ()),
            True,
        )
        expect(
            f"$defs.{definition}.properties.delivery_intent_ref.$ref",
            _property(schema, definition, "delivery_intent_ref", "$ref"),
            "#/$defs/ref",
        )
    return issues


def check(
    snapshot_path: Path,
    schema_path: Path,
    amendment_path: Path | None = None,
) -> dict[str, object]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    known = {item["type_id"] for item in snapshot["object_contracts"]}
    known.add("EvidenceQualification.v1")
    missing: list[dict[str, str]] = []
    for type_id, (definition, fields) in REQUIREDNESS_MAP.items():
        if type_id not in known:
            continue
        required = set(schema["$defs"][definition].get("required", ()))
        properties = set(schema["$defs"][definition].get("properties", ()))
        for field in fields:
            if field not in properties:
                missing.append(
                    {"type_id": type_id, "field": field, "reason": "PROPERTY_MISSING"}
                )
            elif field not in required:
                missing.append(
                    {"type_id": type_id, "field": field, "reason": "NOT_REQUIRED"}
                )
    representation_mapping_issues: list[dict[str, object]] = []
    resolved_amendment = amendment_path or schema_path.with_name(AMENDMENT_NAME)
    if not resolved_amendment.is_file():
        representation_mapping_issues.append(
            _issue(str(resolved_amendment), "AMENDMENT_MISSING", "existing file", None)
        )
    else:
        amendment = json.loads(resolved_amendment.read_text(encoding="utf-8"))
        actual_mappings = amendment.get("representation_mappings")
        if actual_mappings != EXPECTED_REPRESENTATION_MAPPINGS:
            representation_mapping_issues.append(
                _issue(
                    "representation_mappings",
                    "MAPPING_MISMATCH",
                    EXPECTED_REPRESENTATION_MAPPINGS,
                    actual_mappings,
                )
            )
    schema_type_issues = _validate_representation_shapes(schema)
    return {
        "schema": "mrw.functorial_successor.requiredness_check.v1",
        "ok": not missing
        and not representation_mapping_issues
        and not schema_type_issues,
        "snapshot": str(snapshot_path),
        "candidate_schema": str(schema_path),
        "amendment": str(resolved_amendment),
        "missing": missing,
        "representation_mapping_issues": representation_mapping_issues,
        "schema_type_issues": schema_type_issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("schema", type=Path)
    parser.add_argument("--amendment", type=Path)
    args = parser.parse_args()
    report = check(args.snapshot, args.schema, args.amendment)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
