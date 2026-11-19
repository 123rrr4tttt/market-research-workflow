from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.successor_runtime.runtime.capacity import (
    BOUNDED_TWO_NODE_SCOPE,
    CAPACITY_ENVELOPE_SCHEMA_VERSION,
    CAPACITY_FAIR_SHARE_POLICY,
    UNSUPPORTED_CAPACITY,
    CapacityContractError,
    ConnectionObservation,
    LatencyPercentiles,
    LockObservation,
    build_capacity_envelope,
    capacity_envelope_json_schema,
    fair_share_policy_digest,
    fair_share_policy_payload,
    nearest_rank,
)
from app.successor_runtime.runtime.resources import starvation_bound_seconds
from scripts.generate_successor_capacity_envelope import (
    assert_capacity_envelope,
    write_capacity_envelope_atomic,
)

pytestmark = pytest.mark.contract


def _envelope():
    analytical_seconds = float(
        starvation_bound_seconds(
            CAPACITY_FAIR_SHARE_POLICY,
            eligible_item_count=8,
            project_count=2,
            capability_count=2,
            claim_batch=4,
        )
    )
    return build_capacity_envelope(
        observed_at=datetime(2030, 8, 31, tzinfo=timezone.utc),
        database_name="mrw_capacity_test",
        database_role="mrw_capacity_runner",
        postgres_version="16.4",
        postgres_settings={"max_connections": "100", "autovacuum": "on"},
        node_ids=("node-a", "node-b"),
        node_profile_digests=("a" * 64,),
        fair_share_policy_digest=fair_share_policy_digest(CAPACITY_FAIR_SHARE_POLICY),
        fair_share_policy_parameters=fair_share_policy_payload(
            CAPACITY_FAIR_SHARE_POLICY
        ),
        project_count=2,
        capability_count=2,
        eligible_row_count=8,
        initial_eligible_ids_digest="b" * 64,
        observed_claimed_ids_digest="b" * 64,
        observed_claimed_count=8,
        observed_project_claim_counts={"project-a": 4, "project-b": 4},
        observed_capability_claim_counts={
            "compile": 4,
            "verify": 4,
        },
        analytical_max_selection_rounds=2,
        analytical_starvation_bound_seconds=analytical_seconds,
        measured_max_selection_round=2,
        measured_max_selection_seconds=0.25,
        violations=0,
        work_item_table_before_digest="c" * 64,
        work_item_table_after_digest="c" * 64,
        work_item_table_unchanged=True,
        terminal_row_count=4,
        claim_batch_size=2,
        work_item_rate_per_second=42.0,
        claim_latency_samples_ms=(4.0, 1.0, 3.0, 2.0),
        commit_latency_samples_ms=(0.4, 0.1, 0.3, 0.2),
        lock_wait_ms=UNSUPPORTED_CAPACITY,
        lock_observation=LockObservation(3, 0, 0),
        connection_observation=ConnectionObservation(3, 1, 0, 100),
        backlog_age_seconds=25.0,
        max_starvation_seconds=analytical_seconds,
        vacuum_policy="autovacuum=on",
        partition_policy=UNSUPPORTED_CAPACITY,
        archive_policy=UNSUPPORTED_CAPACITY,
        measurement_notes=("bounded local fixture",),
    )


def test_nearest_rank_is_explicit_and_does_not_interpolate() -> None:
    samples = (1.0, 2.0, 3.0, 4.0)
    assert nearest_rank(samples, 0) == 1.0
    assert nearest_rank(samples, 50) == 2.0
    assert nearest_rank(samples, 95) == 4.0
    assert nearest_rank(samples, 99) == 4.0
    assert nearest_rank(samples, 100) == 4.0


@pytest.mark.parametrize("samples", [(), (-1.0,), (float("inf"),)])
def test_nearest_rank_rejects_missing_or_invalid_samples(samples) -> None:
    with pytest.raises(CapacityContractError):
        nearest_rank(samples, 50)


def test_latency_summary_uses_nearest_rank_and_is_monotone() -> None:
    summary = LatencyPercentiles.from_samples((4.0, 1.0, 3.0, 2.0))
    assert summary.sample_count == 4
    assert summary.minimum_ms == 1.0
    assert summary.p50_ms == 2.0
    assert summary.p95_ms == 4.0
    assert summary.p99_ms == 4.0
    assert summary.maximum_ms == 4.0


def test_capacity_envelope_is_schema_and_digest_bound() -> None:
    envelope = _envelope()
    assert envelope.schema_version == CAPACITY_ENVELOPE_SCHEMA_VERSION
    assert envelope.measurement_scope == BOUNDED_TWO_NODE_SCOPE
    assert envelope.node_count == 2
    assert envelope.node_profile_count == 1
    assert envelope.envelope_digest == envelope.compute_digest()
    assert envelope.envelope_ref == (
        f"capacity-envelope:sha256:{envelope.envelope_digest}"
    )
    assert envelope.canonical_bytes() == envelope.canonical_bytes()
    assert envelope.as_payload()["observed_at"] == datetime(
        2030, 8, 31, tzinfo=timezone.utc
    )


def test_capacity_digest_ignores_mapping_insertion_order_but_binds_values() -> None:
    first = _envelope()
    second = replace(
        first,
        postgres_settings={"autovacuum": "on", "max_connections": "100"},
        envelope_digest=None,
    )
    changed = replace(
        first,
        terminal_row_count=5,
        envelope_digest=None,
    )
    assert first.envelope_digest == second.envelope_digest
    assert first.envelope_digest != changed.envelope_digest
    with pytest.raises(CapacityContractError, match="envelope_digest mismatch"):
        replace(first, terminal_row_count=5)


def test_fairness_coverage_and_rollback_are_required_contract_evidence() -> None:
    envelope = _envelope()
    with pytest.raises(CapacityContractError, match="exactly equal"):
        replace(
            envelope,
            observed_claimed_ids_digest="d" * 64,
            envelope_digest=None,
        )
    with pytest.raises(CapacityContractError, match="unchanged"):
        replace(
            envelope,
            work_item_table_unchanged=False,
            envelope_digest=None,
        )
    with pytest.raises(CapacityContractError, match="derived"):
        replace(envelope, max_starvation_seconds=1.0, envelope_digest=None)


def test_unsupported_capacity_exactly_names_unmeasured_required_fields() -> None:
    envelope = _envelope()
    assert envelope.unsupported_capacity == (
        "archive_policy",
        "lock_wait_ms",
        "partition_policy",
    )
    with pytest.raises(CapacityContractError, match="unsupported_capacity"):
        replace(envelope, unsupported_capacity=(), envelope_digest=None)


def test_two_node_baseline_rejects_nonhomologous_or_wrong_concurrency() -> None:
    envelope = _envelope()
    with pytest.raises(CapacityContractError, match="one exact homologous"):
        replace(
            envelope,
            node_profile_digests=("a" * 64, "b" * 64),
            envelope_digest=None,
        )
    with pytest.raises(CapacityContractError, match="concurrency=2"):
        replace(envelope, concurrency=3, envelope_digest=None)


def test_capacity_schema_is_closed_and_requires_every_serialized_field() -> None:
    schema = capacity_envelope_json_schema()
    envelope = _envelope()
    assert schema["$id"] == "urn:mrw:successor:CapacityEnvelope.v1"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(envelope.as_payload())
    assert schema["properties"]["node_count"] == {"const": 2}
    assert schema["properties"]["database_transport"] == {"const": "unix_socket"}


def test_generator_validates_then_atomically_writes_exact_bytes(tmp_path) -> None:
    envelope = _envelope()
    exact = assert_capacity_envelope(envelope)
    output = tmp_path / "nested" / "CapacityEnvelope.v1.json"
    write_capacity_envelope_atomic(output, exact)
    assert output.read_bytes() == exact
    assert not tuple(output.parent.glob("*.tmp"))
