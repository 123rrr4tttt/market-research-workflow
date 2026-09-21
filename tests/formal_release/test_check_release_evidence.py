from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.formal_release import model


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "formal_release" / "check_release_evidence.py"
SPEC = importlib.util.spec_from_file_location("check_release_evidence", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def digest(seed: str) -> str:
    return (seed.encode("utf-8").hex() * 32)[:64]


def make_record(
    family: str,
    *,
    gate_id: str | None = None,
    status: str = "PASS",
    evidence_refs: list[str] | None = None,
    evidence_sha256: list[str] | None = None,
    required: bool = True,
) -> dict[str, object]:
    if gate_id is None:
        gate_id = f"{family}.gate"
    if evidence_refs is None:
        evidence_refs = [f"{family}.ref"]
    if evidence_sha256 is None:
        evidence_sha256 = [digest(family[:1] or "a")]
    return {
        "gate_id": gate_id,
        "family": family,
        "status": status,
        "required": required,
        "evidence_refs": evidence_refs,
        "evidence_sha256": evidence_sha256,
        "observed_at": "2026-09-04T00:00:00Z",
        "owner": "release-check",
        "notes": [f"{family} note"],
    }


def make_manifest(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": checker.SCHEMA_VERSION,
        "authoritative": False,
        "derived_as": checker.DERIVED_AS,
        "records": records,
    }


def base_records(
    *,
    promotion_status: str = "PASS",
    candidate_status: str = "PASS",
    candidate_refs: list[str] | None = None,
    candidate_digests: list[str] | None = None,
    authority_refs: list[str] | None = None,
    authority_digests: list[str] | None = None,
    other_status: str = "PASS",
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for family in checker.REQUIRED_FAMILIES:
        status = promotion_status if family == "promotion_authority" else candidate_status if family == "candidate_identity" else other_status
        refs = candidate_refs if family == "candidate_identity" else authority_refs if family == "promotion_authority" else [f"{family}.ref"]
        digests = candidate_digests if family == "candidate_identity" else authority_digests if family == "promotion_authority" else [digest(family[:1] or "a")]
        records.append(
            make_record(
                family,
                status=status,
                evidence_refs=refs,
                evidence_sha256=digests,
            )
        )
    return records


def test_validate_manifest_accepts_rc_ready_manifest() -> None:
    manifest = make_manifest(
        base_records(
            promotion_status="BLOCKED",
            authority_refs=[],
            authority_digests=[],
        )
    )

    result = checker.validate_manifest(manifest)

    assert result.readiness.formal_rc_ready is True
    assert result.readiness.formal_production_ready is False
    assert result.readiness.candidate_identity_exact is True
    assert result.readiness.promotion_authority_exact is False
    assert result.report.status == "BLOCKED"
    assert [finding.status for finding in result.report.findings if finding.check_id == "promotion_authority.gate"] == [
        "BLOCKED"
    ]


def test_validate_manifest_accepts_production_ready_manifest() -> None:
    manifest = make_manifest(base_records())

    result = checker.validate_manifest(manifest)

    assert result.readiness.formal_rc_ready is True
    assert result.readiness.formal_production_ready is True
    assert result.readiness.candidate_identity_exact is True
    assert result.readiness.promotion_authority_exact is True
    assert result.report.status == "PASS"


def test_duplicate_gate_id_is_rejected() -> None:
    records = base_records()
    records[1]["gate_id"] = records[0]["gate_id"]
    manifest = make_manifest(records)

    result = checker.validate_manifest(manifest)

    assert result.report.status == "FAIL"
    assert any(finding.check_id.endswith("duplicate_gate_id") for finding in result.report.findings)


def test_missing_family_is_rejected() -> None:
    records = base_records()
    records.pop()
    manifest = make_manifest(records)

    result = checker.validate_manifest(manifest)

    assert result.report.status == "FAIL"
    assert any(finding.check_id == "family.promotion_authority" for finding in result.report.findings)
    assert result.readiness.formal_production_ready is False


def test_invalid_digest_is_rejected() -> None:
    records = base_records()
    records[0]["evidence_sha256"] = ["not-a-digest"]
    manifest = make_manifest(records)

    result = checker.validate_manifest(manifest)

    assert result.report.status == "FAIL"
    assert any("digest" in finding.check_id for finding in result.report.findings)


def test_pass_without_evidence_is_rejected() -> None:
    records = base_records()
    records[0]["evidence_refs"] = []
    records[0]["evidence_sha256"] = []
    manifest = make_manifest(records)

    result = checker.validate_manifest(manifest)

    assert result.report.status == "FAIL"
    assert any(finding.check_id == "semantic_closure.gate" for finding in result.report.findings)
    assert any(finding.check_id == "semantic_closure.evidence" for finding in result.report.findings)


def test_blocked_and_unexecuted_statuses_are_preserved() -> None:
    records = base_records(
        promotion_status="BLOCKED",
        other_status="UNEXECUTED",
        authority_refs=[],
        authority_digests=[],
    )
    manifest = make_manifest(records)

    result = checker.validate_manifest(manifest)

    statuses = {
        finding.check_id: finding.status
        for finding in result.report.findings
        if finding.check_id in {"artifact_build.gate", "promotion_authority.gate"}
    }
    assert statuses["artifact_build.gate"] == "UNEXECUTED"
    assert statuses["promotion_authority.gate"] == "BLOCKED"
    assert result.report.status == "BLOCKED"


def test_cli_writes_deterministic_wrapper(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "output.json"
    manifest_path.write_text(json.dumps(make_manifest(base_records()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    exit_code = checker.main(["--manifest", str(manifest_path), "--output", str(output_path)])

    assert exit_code == 0
    wrapper = json.loads(output_path.read_text(encoding="utf-8"))
    assert wrapper["readiness"]["formal_production_ready"] is True
    assert wrapper["report"]["schema_version"] == model.SCHEMA_VERSION
    assert wrapper["report"]["authoritative"] is False
    assert wrapper["report"]["derived_as"] == "preflight"


def test_direct_script_help_works() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0
    assert "Validate formal release evidence manifests." in proc.stdout
