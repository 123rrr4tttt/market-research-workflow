#!/usr/bin/env python3
"""Validate the frozen formal production release evidence manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.formal_release.model import Finding, PreflightReport


SCHEMA_VERSION = "mrw.formal-production-release-evidence.v1"
DERIVED_AS = "preflight"
CHECKER_NAME = "formal-production-release-evidence"
REQUIRED_FAMILIES = (
    "semantic_closure",
    "candidate_identity",
    "artifact_build",
    "business_validation",
    "security_supply_chain",
    "runtime_staging",
    "observability_canary",
    "backup_recovery",
    "independent_review",
    "promotion_authority",
)
VALID_STATUSES = ("PASS", "FAIL", "BLOCKED", "UNEXECUTED")
HEX_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
TOP_LEVEL_RECORD_KEYS = ("records", "gate_records", "gates")


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    gate_id: str
    family: str
    status: str
    required: bool
    evidence_refs: tuple[str, ...]
    evidence_sha256: tuple[str, ...]
    observed_at: str
    owner: str
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleaseReadiness:
    formal_rc_ready: bool
    formal_production_ready: bool
    candidate_identity_exact: bool
    promotion_authority_exact: bool

    def to_dict(self) -> dict[str, bool]:
        return {
            "formal_rc_ready": self.formal_rc_ready,
            "formal_production_ready": self.formal_production_ready,
            "candidate_identity_exact": self.candidate_identity_exact,
            "promotion_authority_exact": self.promotion_authority_exact,
        }


@dataclass(frozen=True, slots=True)
class ValidationResult:
    report: PreflightReport
    readiness: ReleaseReadiness

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "readiness": self.readiness.to_dict(),
        }


def _as_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _as_text_list(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in value:
        text = _as_text(item)
        if text is None:
            return None
        items.append(text)
    return tuple(items)


def _is_valid_digest(value: str) -> bool:
    return bool(HEX_DIGEST_RE.fullmatch(value))


def _issue(
    findings: list[Finding],
    check_id: str,
    summary: str,
    *,
    evidence: tuple[str, ...] = (),
) -> None:
    findings.append(Finding(check_id=check_id, status="FAIL", summary=summary, evidence=evidence))


def _record_summary(record: ManifestRecord) -> str:
    return f"{record.family}:{record.gate_id}"


def _normalize_record(raw: Any) -> tuple[ManifestRecord | None, list[Finding]]:
    findings: list[Finding] = []
    if not isinstance(raw, dict):
        _issue(findings, "record.shape", "record must be a JSON object")
        return None, findings

    gate_id = _as_text(raw.get("gate_id"))
    family = _as_text(raw.get("family"))
    status = _as_text(raw.get("status"))
    required = raw.get("required")
    evidence_refs = _as_text_list(raw.get("evidence_refs"))
    evidence_sha256 = _as_text_list(raw.get("evidence_sha256"))
    observed_at = _as_text(raw.get("observed_at"))
    owner = _as_text(raw.get("owner"))
    notes = _as_text_list(raw.get("notes"))
    issue_prefix = family or gate_id or "record"

    if gate_id is None:
        _issue(findings, f"{issue_prefix}.gate_id", "gate_id is required")
        gate_id = "record-gate-id-missing"
    if family is None:
        _issue(findings, f"{issue_prefix}.family", "family is required")
        family = "family-missing"
    if status not in VALID_STATUSES:
        _issue(findings, f"{issue_prefix}.status", "status must be PASS, FAIL, BLOCKED, or UNEXECUTED")
        status = "FAIL"
    if required is not True:
        _issue(findings, f"{issue_prefix}.required", "required must be true")
    if observed_at is None:
        _issue(findings, f"{issue_prefix}.observed_at", "observed_at is required")
        observed_at = ""
    if owner is None:
        _issue(findings, f"{issue_prefix}.owner", "owner is required")
        owner = ""
    if notes is None:
        _issue(findings, f"{issue_prefix}.notes", "notes must be a string list")
        notes = ()

    normalized_refs = evidence_refs or ()
    normalized_digests = evidence_sha256 or ()
    if evidence_refs is None:
        _issue(findings, f"{issue_prefix}.evidence_refs", "evidence_refs must be a string list")
    if evidence_sha256 is None:
        _issue(findings, f"{issue_prefix}.evidence_sha256", "evidence_sha256 must be a string list")

    if evidence_refs is not None and evidence_sha256 is not None:
        if len(evidence_refs) != len(evidence_sha256):
            _issue(
                findings,
                f"{issue_prefix}.evidence_pair",
                "evidence_refs and evidence_sha256 must be positional pairs of equal length",
            )
        for digest in evidence_sha256:
            if not _is_valid_digest(digest):
                _issue(findings, f"{issue_prefix}.digest", "evidence_sha256 entries must be lowercase 64-character hex digests")
                break

    if status == "PASS":
        if not normalized_refs or not normalized_digests:
            _issue(findings, f"{issue_prefix}.evidence", "PASS requires at least one exact evidence ref and digest")

    return (
        ManifestRecord(
            gate_id=gate_id,
            family=family,
            status=status,
            required=required is True,
            evidence_refs=normalized_refs,
            evidence_sha256=normalized_digests,
            observed_at=observed_at,
            owner=owner,
            notes=notes,
        ),
        findings,
    )


def _records_from_payload(payload: dict[str, Any], findings: list[Finding]) -> list[ManifestRecord]:
    for key in TOP_LEVEL_RECORD_KEYS:
        if key in payload:
            records = payload[key]
            break
    else:
        _issue(findings, "manifest.records", "manifest must contain a records array")
        return []

    if not isinstance(records, list):
        _issue(findings, "manifest.records", "records must be a list")
        return []

    normalized: list[ManifestRecord] = []
    gate_ids: set[str] = set()
    families: set[str] = set()
    for index, raw in enumerate(records):
        record, record_findings = _normalize_record(raw)
        findings.extend(record_findings)
        if record is None:
            continue

        findings.append(
            Finding(
                check_id=f"{record.family}.gate",
                status=record.status,
                summary=_record_summary(record),
                evidence=record.evidence_refs + record.evidence_sha256,
            )
        )

        if record.gate_id in gate_ids:
            _issue(findings, f"{record.family}.duplicate_gate_id", "gate_id values must be unique")
        else:
            gate_ids.add(record.gate_id)

        if record.family not in REQUIRED_FAMILIES:
            _issue(findings, f"{record.family}.family_scope", "family must be one of the required release families")
            continue
        if record.family in families:
            _issue(findings, f"{record.family}.duplicate_family", "each required family must occur exactly once")
            continue
        families.add(record.family)
        normalized.append(record)

    missing_families = [family for family in REQUIRED_FAMILIES if family not in families]
    for family in missing_families:
        _issue(findings, f"family.{family}", "required family is missing")

    if len(normalized) != len(REQUIRED_FAMILIES):
        _issue(findings, "manifest.family_cardinality", "manifest must contain exactly one record for each required family")

    return normalized


def _validate_top_level(payload: Any, findings: list[Finding]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        _issue(findings, "manifest.shape", "manifest must be a JSON object")
        return None

    schema_version = _as_text(payload.get("schema_version"))
    if schema_version != SCHEMA_VERSION:
        _issue(findings, "manifest.schema_version", f"schema_version must be {SCHEMA_VERSION}")

    authoritative = payload.get("authoritative")
    if authoritative is not False:
        _issue(findings, "manifest.authoritative", "authoritative must be false")

    derived_as = _as_text(payload.get("derived_as"))
    if derived_as != DERIVED_AS:
        _issue(findings, "manifest.derived_as", f"derived_as must be {DERIVED_AS}")

    return payload


def validate_manifest(payload: Any) -> ValidationResult:
    findings: list[Finding] = []
    normalized_payload = _validate_top_level(payload, findings)

    records: list[ManifestRecord] = []
    if normalized_payload is not None:
        records = _records_from_payload(normalized_payload, findings)

    record_by_family = {record.family: record for record in records}
    candidate = record_by_family.get("candidate_identity")
    promotion_authority = record_by_family.get("promotion_authority")

    candidate_exact = bool(
        candidate
        and candidate.status == "PASS"
        and len(candidate.evidence_refs) > 0
        and len(candidate.evidence_refs) == len(candidate.evidence_sha256)
        and all(_is_valid_digest(digest) for digest in candidate.evidence_sha256)
    )
    promotion_authority_exact = bool(
        promotion_authority
        and promotion_authority.status == "PASS"
        and len(promotion_authority.evidence_refs) > 0
        and len(promotion_authority.evidence_refs) == len(promotion_authority.evidence_sha256)
        and all(_is_valid_digest(digest) for digest in promotion_authority.evidence_sha256)
    )

    non_promotion_records = [record for record in records if record.family != "promotion_authority"]
    formal_rc_ready = bool(
        candidate_exact
        and all(record.status == "PASS" for record in non_promotion_records)
    )
    formal_production_ready = bool(
        candidate_exact
        and promotion_authority_exact
        and all(record.status == "PASS" for record in records)
    )

    report = PreflightReport(checker=CHECKER_NAME, findings=tuple(findings))
    return ValidationResult(
        report=report,
        readiness=ReleaseReadiness(
            formal_rc_ready=formal_rc_ready,
            formal_production_ready=formal_production_ready,
            candidate_identity_exact=candidate_exact,
            promotion_authority_exact=promotion_authority_exact,
        ),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate formal release evidence manifests.")
    parser.add_argument("--manifest", required=True, help="Path to the manifest JSON file.")
    parser.add_argument("--output", help="Optional output path for the JSON wrapper.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = Path(args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = validate_manifest(payload)
    wrapper = result.to_dict()
    output = json.dumps(wrapper, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")

    return 0 if result.report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
