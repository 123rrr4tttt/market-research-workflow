"""Focused tests for C8 audit/trend evidence-consumption surfaces."""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.c8_report_export_audit_evidence_surface import (
    ExportAuditObservation,
    consume_export_audit_evidence,
    project_export_audit_dashboard_rows,
)
from app.successor_runtime.capabilities.c8_report_export_audit_evidence_surface import (
    authority_ceiling as audit_authority_ceiling,
)
from app.successor_runtime.capabilities.c8_report_quality_trend_evidence_surface import (
    ReportQualityTrendObservation,
    consume_report_quality_trend_evidence,
)
from app.successor_runtime.capabilities.c8_report_quality_trend_evidence_surface import (
    authority_ceiling as trend_authority_ceiling,
)

pytestmark = pytest.mark.unit

DIGEST = "sha256:" + "0" * 64


def _audit_row(
    *, origin: str, trace_id: str = "trace:audit:001"
) -> ExportAuditObservation:
    return ExportAuditObservation(
        trace_id=trace_id,
        report_id="report:001",
        export_outcome="exported",
        origin=origin,
        integrity_digest=DIGEST,
        actor_digest=DIGEST,
        observed_at="2026-09-02T18:00:00+00:00",
    )


def test_export_audit_durable_rows_are_available_but_write_stays_no_call() -> None:
    readback = consume_export_audit_evidence((_audit_row(origin="durable_record"),))
    assert readback.durable_count == 1
    assert readback.digest_available is True
    assert readback.no_call_durable_write is True
    assert readback.authority == audit_authority_ceiling()
    rows = project_export_audit_dashboard_rows(readback)
    assert rows[0]["trace_id"] == "trace:audit:001"
    assert rows[0]["degraded_warning"] is False


def test_export_audit_degraded_or_local_is_never_durable_proof() -> None:
    readback = consume_export_audit_evidence(
        (
            _audit_row(origin="degraded_memory", trace_id="trace:audit:002"),
            _audit_row(
                origin="local_deterministic_observation", trace_id="trace:audit:003"
            ),
        )
    )
    assert readback.degraded_count == 1
    assert readback.local_count == 1
    assert readback.digest_available is False
    assert readback.degraded_is_not_durable_proof is True


def test_export_audit_rejects_credential_like_source_ref() -> None:
    with pytest.raises(ValueError, match="credential"):
        ExportAuditObservation(
            trace_id="trace:audit:004",
            report_id="report:001",
            export_outcome="exported",
            origin="durable_record",
            integrity_digest=DIGEST,
            actor_digest=DIGEST,
            observed_at="2026-09-02T18:00:00+00:00",
            source_ref="apikey file",
        )


def _trend_row(
    *, fallback: bool = False, outcome: str = "passed"
) -> ReportQualityTrendObservation:
    return ReportQualityTrendObservation(
        report_id="report:001",
        trace_id="trace:trend:001",
        outcome=outcome,
        gate_mode="exact",
        fallback_used=fallback,
        coverage_count=3,
        observed_at="2026-09-02T18:00:00+00:00",
    )


def test_trend_evidence_marks_degraded_readback_and_never_aggregates() -> None:
    held = consume_report_quality_trend_evidence(
        (_trend_row(outcome="held", fallback=True),)
    )
    assert held.degraded_readback is True
    assert held.aggregation_writer_called is False
    assert held.no_call_durable_aggregation is True
    assert held.outcome_counts["held"] == 1
    assert held.authority == trend_authority_ceiling()


def test_trend_evidence_all_passed_is_not_degraded() -> None:
    passed = consume_report_quality_trend_evidence(
        (
            _trend_row(outcome="passed"),
            _trend_row(outcome="passed"),
        )
    )
    assert passed.degraded_readback is False
    assert passed.total_count == 2
    assert passed.outcome_counts["passed"] == 2
