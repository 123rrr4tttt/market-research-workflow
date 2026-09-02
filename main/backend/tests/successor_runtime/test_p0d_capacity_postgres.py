from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from app.successor_runtime.runtime.capacity import (
    BOUNDED_TWO_NODE_SCOPE,
    CAPACITY_ENVELOPE_SCHEMA_VERSION,
    CAPACITY_FAIR_SHARE_POLICY,
    UNSUPPORTED_CAPACITY,
    fair_share_policy_digest,
)
from app.successor_runtime.substrate.postgres.capacity import (
    CapacityEnvironmentGuard,
    CapacityMeasurementConfig,
    PostgresCapacityObserver,
    UnsafeCapacityEnvironment,
    validate_capacity_database_url,
)
from scripts.generate_successor_capacity_envelope import generate_capacity_envelope
from tests.successor_runtime.p0d_capacity_fixture import (
    CAPABILITIES,
    NODE_IDS,
    NODE_PROFILE_DIGEST,
    P0DCapacityDatabase,
    p0d_capacity_database,
)

pytestmark = pytest.mark.integration


def test_capacity_url_guard_rejects_tcp_database_and_role_drift() -> None:
    guard = CapacityEnvironmentGuard(
        expected_database_name="codex_p0d_capacity_test",
        expected_role="mrw_capacity_runner",
    )
    with pytest.raises(UnsafeCapacityEnvironment, match="forbids TCP"):
        validate_capacity_database_url(
            "postgresql+psycopg2://mrw_capacity_runner@localhost/"
            "codex_p0d_capacity_test",
            guard,
        )
    with pytest.raises(UnsafeCapacityEnvironment, match="database URL"):
        validate_capacity_database_url(
            "postgresql+psycopg2://mrw_capacity_runner@/wrong_test",
            guard,
        )
    with pytest.raises(UnsafeCapacityEnvironment, match="URL role"):
        validate_capacity_database_url(
            "postgresql+psycopg2://wrong_role@/codex_p0d_capacity_test",
            guard,
        )


def test_postgres_guard_proves_non_superuser_unix_socket_and_exact_nodes(
    p0d_capacity_database: P0DCapacityDatabase,
) -> None:
    observer = PostgresCapacityObserver(
        p0d_capacity_database.engine,
        p0d_capacity_database.guard,
    )
    environment = observer.verify_environment()
    assert environment.node_ids == NODE_IDS
    assert environment.node_profile_digest == NODE_PROFILE_DIGEST
    assert (
        environment.database_name == p0d_capacity_database.guard.expected_database_name
    )
    assert environment.database_role == p0d_capacity_database.guard.expected_role
    assert environment.postgres_settings["autovacuum"] in {"on", "off"}
    with p0d_capacity_database.engine.connect() as connection:
        identity = connection.execute(
            sa.text(
                "SELECT inet_server_addr(), inet_client_addr(), "
                "(SELECT rolsuper FROM pg_roles WHERE rolname = current_user)"
            )
        ).one()
        assert identity == (None, None, False)


def test_two_node_capacity_baseline_is_measured_without_mutating_work_items(
    p0d_capacity_database: P0DCapacityDatabase,
) -> None:
    observer = PostgresCapacityObserver(
        p0d_capacity_database.engine,
        p0d_capacity_database.guard,
    )
    with p0d_capacity_database.engine.connect() as connection:
        before = connection.execute(
            sa.text(
                "SELECT to_jsonb(w) FROM public.runtime_work_items AS w "
                "ORDER BY work_item_id"
            )
        ).all()
    envelope = observer.collect(
        CapacityMeasurementConfig(
            claim_batch_size=2,
        )
    )
    with p0d_capacity_database.engine.connect() as connection:
        after = connection.execute(
            sa.text(
                "SELECT to_jsonb(w) FROM public.runtime_work_items AS w "
                "ORDER BY work_item_id"
            )
        ).all()

    assert before == after
    assert envelope.schema_version == CAPACITY_ENVELOPE_SCHEMA_VERSION
    assert envelope.measurement_scope == BOUNDED_TWO_NODE_SCOPE
    assert envelope.node_ids == NODE_IDS
    assert envelope.node_profile_digests == (NODE_PROFILE_DIGEST,)
    assert envelope.project_count == 2
    assert envelope.capability_count == 2
    assert envelope.eligible_row_count == 8
    assert envelope.observed_claimed_count == 8
    assert envelope.initial_eligible_ids_digest == envelope.observed_claimed_ids_digest
    assert envelope.observed_project_claim_counts == {
        "p0d-capacity-project-a": 4,
        "p0d-capacity-project-b": 4,
    }
    assert set(envelope.observed_capability_claim_counts) == set(CAPABILITIES)
    assert set(envelope.observed_capability_claim_counts.values()) == {4}
    assert envelope.fair_share_policy_digest == fair_share_policy_digest(
        CAPACITY_FAIR_SHARE_POLICY
    )
    assert envelope.analytical_max_selection_rounds == 2
    assert envelope.measured_max_selection_round <= 2
    assert (
        envelope.measured_max_selection_seconds
        <= envelope.analytical_starvation_bound_seconds
        == envelope.max_starvation_seconds
    )
    assert envelope.violations == 0
    assert envelope.work_item_table_unchanged is True
    assert (
        envelope.work_item_table_before_digest == envelope.work_item_table_after_digest
    )
    assert envelope.terminal_row_count == 4
    assert envelope.claim_batch_size == 2
    assert envelope.concurrency == 2
    assert envelope.claim_latency_ms.sample_count == 4
    assert envelope.commit_latency_ms.sample_count == 2
    assert isinstance(envelope.work_item_rate_per_second, float)
    assert envelope.work_item_rate_per_second > 0
    assert envelope.lock_wait_ms == UNSUPPORTED_CAPACITY
    assert envelope.lock_observation.ungranted_locks == 0
    assert envelope.connection_observation.database_connections >= 1
    assert 0 <= envelope.backlog_age_seconds <= envelope.max_starvation_seconds
    assert envelope.partition_policy == UNSUPPORTED_CAPACITY
    assert envelope.archive_policy == UNSUPPORTED_CAPACITY
    assert envelope.unsupported_capacity == (
        "archive_policy",
        "lock_wait_ms",
        "partition_policy",
    )
    assert envelope.envelope_digest == envelope.compute_digest()
    serialized = json.loads(envelope.canonical_bytes())
    assert serialized["envelope_digest"] == envelope.envelope_digest
    assert serialized["node_count"] == 2
    assert serialized["node_profile_count"] == 1


def test_starvation_bound_is_not_a_caller_assertion() -> None:
    with pytest.raises(TypeError, match="max_starvation_seconds"):
        CapacityMeasurementConfig(max_starvation_seconds=0.001)  # type: ignore[call-arg]


def test_generator_writes_only_after_live_guard_and_digest_readback(
    p0d_capacity_database: P0DCapacityDatabase,
    tmp_path,
) -> None:
    output = tmp_path / "CapacityEnvelope.v1.json"
    envelope = generate_capacity_envelope(
        database_url=p0d_capacity_database.database_url,
        guard=p0d_capacity_database.guard,
        config=CapacityMeasurementConfig(
            claim_batch_size=2,
        ),
        output=output,
    )
    artifact = json.loads(output.read_bytes())
    assert artifact["envelope_digest"] == envelope.envelope_digest
    assert artifact["database_transport"] == "unix_socket"
    assert artifact["node_count"] == 2


__all__ = ["p0d_capacity_database"]
