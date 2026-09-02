"""P4 C8.3 report staging and admission/delivery interface contract tests."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.c8_report import (
    REPORT_ADMISSION_CONTRACT,
    REPORT_DELIVERY_CONTRACT,
    REPORT_STAGE_SEQUENCE,
    ReportAdmissionContract,
    ReportDeliveryContract,
    build_report_admission_intent,
    build_report_artifact,
    build_report_delivery_intent,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import (
    UnavailableProjection,
    demand_read,
)

from .p4_c8_fixture import PROJECT_KEY, TOPIC, captured_item, new_registry


def _reads(*, with_evidence: bool) -> tuple:
    item = captured_item()
    fields = (
        ("canonical_statement", "evidence_refs")
        if with_evidence
        else ("canonical_statement",)
    )
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=fields,
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    return (read,)


def test_report_does_not_manufacture_missing_evidence() -> None:
    artifact = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_reads(with_evidence=False),
    )
    assert artifact.rows[0].status == "unavailable"
    assert artifact.rows[0].evidence is None


def test_report_ready_rows_use_demand_read_statement_only() -> None:
    artifact = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_reads(with_evidence=True),
    )
    assert artifact.rows[0].status == "ready"
    assert artifact.rows[0].evidence == "机器人产品市场证据"
    assert artifact.rows[0].handle.handle_id
    assert artifact.artifact_digest
    assert artifact.staging_sequence == REPORT_STAGE_SEQUENCE
    assert artifact.source_identities == (
        f"knowledge:{PROJECT_KEY}:{artifact.rows[0].source_key}",
    )
    assert "export_body" in artifact.declared_loss
    assert "admission_receipt" in artifact.declared_loss
    assert "delivery_receipt" in artifact.declared_loss


def test_admission_and_delivery_are_interface_contracts_only() -> None:
    artifact = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_reads(with_evidence=True),
    )
    admission = build_report_admission_intent(artifact)
    delivery = build_report_delivery_intent(artifact)

    assert admission.contract_version == REPORT_ADMISSION_CONTRACT
    assert admission.admitted is False
    assert "not called" in admission.reason
    assert delivery.contract_version == REPORT_DELIVERY_CONTRACT
    assert delivery.delivered is False
    assert "not called" in delivery.reason
    assert ReportAdmissionContract is not None
    assert ReportDeliveryContract is not None


def test_report_artifact_digest_is_deterministic() -> None:
    first = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_reads(with_evidence=True),
    )
    second = build_report_artifact(
        report_id="report-1",
        project_key=PROJECT_KEY,
        topic=TOPIC,
        source_reads=_reads(with_evidence=True),
    )
    assert first.artifact_digest == second.artifact_digest


def test_report_rejects_cross_project_source_handles() -> None:
    item_a = captured_item(key="ki:a", project_key="project-a")
    item_b = captured_item(key="ki:b", project_key="project-b")
    read_a = demand_read(
        (item_a,),
        item_key=item_a.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key="project-a",
        registry=new_registry(),
    )
    read_b = demand_read(
        (item_b,),
        item_key=item_b.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key="project-b",
        registry=new_registry(),
    )
    with pytest.raises(UnavailableProjection, match="report project"):
        build_report_artifact(
            report_id="report-cross",
            project_key="project-a",
            topic=TOPIC,
            source_reads=(read_a, read_b),
        )
