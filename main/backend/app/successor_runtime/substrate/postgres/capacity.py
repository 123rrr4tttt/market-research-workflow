"""Read-only PostgreSQL interpreter for ``CapacityEnvelope.v1``.

The observer is intentionally narrow: a dedicated local Unix-socket database,
one explicitly named non-superuser role, exactly two homologous RuntimeNodes,
and fixture-owned project identities.  Claim observations acquire row locks but
always roll back; they never create attempts, effects, admissions, or canonical
research writes.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url

from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.capacity import (
    CAPACITY_FAIR_SHARE_POLICY,
    UNSUPPORTED_CAPACITY,
    CapacityContractError,
    CapacityEnvelope,
    ConnectionObservation,
    LockObservation,
    build_capacity_envelope,
    fair_share_policy_digest,
    fair_share_policy_payload,
)
from app.successor_runtime.runtime.resources import starvation_bound_seconds

from .models import PUBLIC_TABLES
from .work_items import NodeClaimContext, due_claim_statement

_TEST_DATABASE_PATTERN: Final = re.compile(r"(?:test|testing|ci)", re.IGNORECASE)
_SYSTEM_SCHEMAS: Final = frozenset(
    {"public", "information_schema", "pg_catalog", "pg_toast"}
)
_SETTINGS: Final = (
    "server_version_num",
    "max_connections",
    "shared_buffers",
    "work_mem",
    "effective_cache_size",
    "max_locks_per_transaction",
    "autovacuum",
    "autovacuum_naptime",
    "autovacuum_vacuum_scale_factor",
)
_ELIGIBLE_STATES: Final = ("READY", "WAITING")
_TERMINAL_STATES: Final = (
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "SUPERSEDED",
)


def _observation_digest(value: Any) -> str:
    """Digest one canonical observation value without lossy coercion."""

    return sha256_hex(value)


class UnsafeCapacityEnvironment(CapacityContractError):
    """Raised before measurement when a local safety invariant is false."""


@dataclass(frozen=True, slots=True)
class CapacityEnvironmentGuard:
    """Exact authority ceiling for a bounded local measurement."""

    expected_database_name: str
    expected_role: str
    allowed_project_prefix: str = "p0d-capacity-"
    allowed_schema_prefix: str = "mrw_p0d_capacity_"
    allowed_node_prefix: str = "p0d-capacity-node-"
    allowed_catalog_ref_prefix: str = "p0d-capacity://"

    def __post_init__(self) -> None:
        for name in (
            "expected_database_name",
            "expected_role",
            "allowed_project_prefix",
            "allowed_schema_prefix",
            "allowed_node_prefix",
            "allowed_catalog_ref_prefix",
        ):
            value = getattr(self, name)
            if not value or value != value.strip():
                raise UnsafeCapacityEnvironment(f"{name} must be exact and non-empty")
        if not _TEST_DATABASE_PATTERN.search(self.expected_database_name):
            raise UnsafeCapacityEnvironment(
                "capacity database name must visibly identify a test/CI database"
            )
        if self.expected_database_name in {"postgres", "template0", "template1"}:
            raise UnsafeCapacityEnvironment("refusing PostgreSQL maintenance database")


@dataclass(frozen=True, slots=True)
class CapacityMeasurementConfig:
    """Bounded workload used by the read-only two-node observer."""

    claim_batch_size: int = 2
    statement_timeout_ms: int = 2_000

    def __post_init__(self) -> None:
        if self.claim_batch_size <= 0:
            raise CapacityContractError("capacity claim batch must be positive")
        if self.statement_timeout_ms <= 0:
            raise CapacityContractError("statement_timeout_ms must be positive")


@dataclass(frozen=True, slots=True)
class VerifiedCapacityEnvironment:
    database_name: str
    database_role: str
    postgres_version: str
    postgres_settings: dict[str, str]
    node_ids: tuple[str, str]
    node_profile_digest: str
    deployment_catalog_digest: str
    runtime_protocol_version: str


def validate_capacity_database_url(
    database_url: str,
    guard: CapacityEnvironmentGuard,
) -> None:
    """Reject non-PostgreSQL, TCP, ambiguous-database, or role-mismatched URLs."""

    try:
        url = make_url(database_url)
    except sa.exc.ArgumentError as exc:
        raise UnsafeCapacityEnvironment("invalid capacity database URL") from exc
    if not url.drivername.startswith("postgresql"):
        raise UnsafeCapacityEnvironment("capacity measurement requires PostgreSQL")
    if url.database != guard.expected_database_name:
        raise UnsafeCapacityEnvironment(
            "capacity database URL does not match expected exact database name"
        )
    if url.host not in (None, ""):
        raise UnsafeCapacityEnvironment(
            "capacity measurement forbids TCP; use a PostgreSQL Unix socket URL"
        )
    if url.username is not None and url.username != guard.expected_role:
        raise UnsafeCapacityEnvironment(
            "capacity database URL role does not match expected exact role"
        )


class PostgresCapacityObserver:
    """Collect one bounded, digest-bound capacity observation."""

    def __init__(
        self,
        engine: Engine,
        guard: CapacityEnvironmentGuard,
    ) -> None:
        self._engine = engine
        self._guard = guard
        validate_capacity_database_url(
            engine.url.render_as_string(hide_password=False), guard
        )

    def verify_environment(self) -> VerifiedCapacityEnvironment:
        """Fail closed before any row-lock observation is attempted."""

        inspector = sa.inspect(self._engine)
        public_tables = set(inspector.get_table_names(schema="public"))
        required = {"runtime_nodes", "runtime_work_items", "project_scope_registry"}
        missing = required - public_tables
        if missing:
            raise UnsafeCapacityEnvironment(
                f"successor capacity tables are missing: {sorted(missing)}"
            )
        unknown_public = public_tables - set(PUBLIC_TABLES)
        if unknown_public:
            raise UnsafeCapacityEnvironment(
                "dedicated capacity database contains non-successor public tables: "
                f"{sorted(unknown_public)}"
            )
        user_schemas = {
            schema
            for schema in inspector.get_schema_names()
            if schema not in _SYSTEM_SCHEMAS and not schema.startswith("pg_temp_")
        }
        unexpected_schemas = {
            schema
            for schema in user_schemas
            if not schema.startswith(self._guard.allowed_schema_prefix)
        }
        if unexpected_schemas:
            raise UnsafeCapacityEnvironment(
                "dedicated capacity database contains non-fixture schemas: "
                f"{sorted(unexpected_schemas)}"
            )

        with self._engine.connect() as connection:
            identity = (
                connection.execute(
                    sa.text(
                        "SELECT current_database() AS database_name, "
                        "current_user AS database_role, session_user AS session_role, "
                        "inet_server_addr() AS server_addr, "
                        "inet_client_addr() AS client_addr, "
                        "current_setting('server_version') AS postgres_version, "
                        "COALESCE((SELECT rolsuper FROM pg_roles "
                        "WHERE rolname = current_user), true) AS is_superuser"
                    )
                )
                .mappings()
                .one()
            )
            if identity["database_name"] != self._guard.expected_database_name:
                raise UnsafeCapacityEnvironment("connected database identity drifted")
            if (
                identity["database_role"] != self._guard.expected_role
                or identity["session_role"] != self._guard.expected_role
            ):
                raise UnsafeCapacityEnvironment("connected role identity drifted")
            if identity["is_superuser"]:
                raise UnsafeCapacityEnvironment(
                    "capacity measurement refuses a PostgreSQL superuser"
                )
            if (
                identity["server_addr"] is not None
                or identity["client_addr"] is not None
            ):
                raise UnsafeCapacityEnvironment(
                    "capacity measurement requires an observed Unix-socket connection"
                )

            settings = {
                name: str(
                    connection.execute(
                        sa.text("SELECT current_setting(:name)"), {"name": name}
                    ).scalar_one()
                )
                for name in _SETTINGS
            }
            self._verify_no_production_rows(connection)
            node_rows = (
                connection.execute(
                    sa.text(
                        "SELECT node_id, node_profile_digest, deployment_catalog_digest, "
                        "runtime_protocol_version, state "
                        "FROM public.runtime_nodes ORDER BY node_id"
                    )
                )
                .mappings()
                .all()
            )
            if len(node_rows) != 2:
                raise UnsafeCapacityEnvironment(
                    "bounded baseline requires exactly two persisted RuntimeNodes"
                )
            if any(row["state"] != "ACTIVE" for row in node_rows):
                raise UnsafeCapacityEnvironment(
                    "both bounded RuntimeNodes must be ACTIVE"
                )
            exact_profiles = {row["node_profile_digest"] for row in node_rows}
            exact_catalogs = {row["deployment_catalog_digest"] for row in node_rows}
            exact_protocols = {row["runtime_protocol_version"] for row in node_rows}
            if (
                len(exact_profiles) != 1
                or len(exact_catalogs) != 1
                or len(exact_protocols) != 1
            ):
                raise UnsafeCapacityEnvironment(
                    "two RuntimeNodes must be homologous and exact-catalog bound"
                )
            node_ids = tuple(str(row["node_id"]) for row in node_rows)
            if any(
                not node_id.startswith(self._guard.allowed_node_prefix)
                for node_id in node_ids
            ):
                raise UnsafeCapacityEnvironment(
                    "RuntimeNode identity is not fixture-owned"
                )

        return VerifiedCapacityEnvironment(
            database_name=str(identity["database_name"]),
            database_role=str(identity["database_role"]),
            postgres_version=str(identity["postgres_version"]),
            postgres_settings=settings,
            node_ids=(node_ids[0], node_ids[1]),
            node_profile_digest=str(next(iter(exact_profiles))),
            deployment_catalog_digest=str(next(iter(exact_catalogs))),
            runtime_protocol_version=str(next(iter(exact_protocols))),
        )

    def collect(
        self,
        config: CapacityMeasurementConfig | None = None,
    ) -> CapacityEnvelope:
        """Observe live fair selection with two rollback-only node transactions."""

        if config is None:
            config = CapacityMeasurementConfig()
        environment = self.verify_environment()
        policy = CAPACITY_FAIR_SHARE_POLICY
        selection_now = datetime.now(timezone.utc)
        base_cursor = int(selection_now.timestamp()) // policy.claim_cycle_seconds
        contexts = tuple(
            NodeClaimContext(
                node_id=node_id,
                node_profile_digest=environment.node_profile_digest,
                deployment_catalog_digest=environment.deployment_catalog_digest,
                runtime_protocol_version=environment.runtime_protocol_version,
                authority_snapshot_digest=fair_share_policy_digest(policy),
            )
            for node_id in environment.node_ids
        )
        with self._engine.connect() as connection:
            table_before_digest = self._work_item_table_digest(connection)
            terminal_row_count = self._terminal_row_count(connection)
            total_row_count = int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(
                        PUBLIC_TABLES["runtime_work_items"]
                    )
                ).scalar_one()
            )

        initial_connection = self._engine.connect()
        initial_transaction = initial_connection.begin()
        try:
            initial_rows = (
                initial_connection.execute(
                    due_claim_statement(
                        contexts[0],
                        now=selection_now,
                        limit=max(1, total_row_count),
                        fairness=policy,
                        cursor=base_cursor,
                    )
                )
                .mappings()
                .all()
            )
        finally:
            initial_transaction.rollback()
            initial_connection.close()

        initial_ids = tuple(sorted(str(row["work_item_id"]) for row in initial_rows))
        if not initial_ids:
            raise CapacityContractError(
                "capacity fairness observation requires live eligible work"
            )
        if len(initial_ids) != len(set(initial_ids)):
            raise CapacityContractError(
                "live due claim statement returned duplicate IDs"
            )
        initial_projects = {str(row["project_key"]) for row in initial_rows}
        initial_capabilities = {str(row["capability_id"]) for row in initial_rows}
        initial_project_counts = Counter(
            str(row["project_key"]) for row in initial_rows
        )
        initial_capability_counts = Counter(
            str(row["capability_id"]) for row in initial_rows
        )
        if max(initial_project_counts.values()) > policy.max_project_active:
            raise CapacityContractError(
                "bounded workload exceeds frozen per-project active capacity"
            )
        if max(initial_capability_counts.values()) > policy.max_capability_active:
            raise CapacityContractError(
                "bounded workload exceeds frozen per-capability active capacity"
            )
        analytical_rounds = math.ceil(
            len(initial_ids) / (len(environment.node_ids) * config.claim_batch_size)
        )
        analytical_seconds = float(
            starvation_bound_seconds(
                policy,
                eligible_item_count=len(initial_ids),
                project_count=len(initial_projects),
                capability_count=len(initial_capabilities),
                claim_batch=len(environment.node_ids) * config.claim_batch_size,
            )
        )
        backlog_age = max(
            0.0,
            max(
                (selection_now - row["enqueued_at"]).total_seconds()
                for row in initial_rows
            ),
        )

        claim_samples: list[float] = []
        commit_samples: list[float] = []
        observed_rows: dict[str, dict[str, Any]] = {}
        duplicate_claims = 0
        claim_elapsed_seconds = 0.0
        measured_max_round = 0
        measured_max_seconds = 0.0
        workload_started = time.perf_counter()
        connections = (self._engine.connect(), self._engine.connect())
        transactions = tuple(connection.begin() for connection in connections)
        work = PUBLIC_TABLES["runtime_work_items"]
        try:
            for connection, node_id in zip(
                connections, environment.node_ids, strict=True
            ):
                connection.execute(
                    sa.text(
                        "SELECT set_config('application_name', :name, true), "
                        "set_config('statement_timeout', :timeout, true)"
                    ),
                    {
                        "name": f"mrw-capacity:{node_id}",
                        "timeout": str(config.statement_timeout_ms),
                    },
                )
            for round_number in range(1, analytical_rounds + 1):
                for connection, context in zip(connections, contexts, strict=True):
                    started_ns = time.perf_counter_ns()
                    rows = (
                        connection.execute(
                            due_claim_statement(
                                context,
                                now=selection_now,
                                limit=config.claim_batch_size,
                                fairness=policy,
                                cursor=base_cursor + round_number - 1,
                            )
                        )
                        .mappings()
                        .all()
                    )
                    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
                    claim_samples.append(elapsed_ms)
                    claim_elapsed_seconds += elapsed_ms / 1_000
                    selected_ids = tuple(str(row["work_item_id"]) for row in rows)
                    for row in rows:
                        work_item_id = str(row["work_item_id"])
                        if work_item_id in observed_rows:
                            duplicate_claims += 1
                        observed_rows[work_item_id] = dict(row)
                        measured_max_round = max(measured_max_round, round_number)
                        measured_max_seconds = max(
                            measured_max_seconds,
                            time.perf_counter() - workload_started,
                        )
                    if selected_ids:
                        # Make this transaction's locked rows non-due so its next
                        # live selector call advances.  The other node sees those
                        # rows locked and uses SKIP LOCKED.  Both transactions are
                        # rolled back below, so this never becomes runtime state.
                        connection.execute(
                            sa.update(work)
                            .where(work.c.work_item_id.in_(selected_ids))
                            .values(state="COMPLETED", wait_reason=None)
                        )
                if set(observed_rows) == set(initial_ids):
                    break
        finally:
            for transaction in reversed(transactions):
                if transaction.is_active:
                    transaction.rollback()
            for connection in reversed(connections):
                connection.close()

        observed_ids = tuple(sorted(observed_rows))
        missing_ids = set(initial_ids) - set(observed_ids)
        unexpected_ids = set(observed_ids) - set(initial_ids)
        violations = (
            len(missing_ids)
            + len(unexpected_ids)
            + duplicate_claims
            + int(measured_max_round > analytical_rounds)
            + int(measured_max_seconds > analytical_seconds)
        )
        if violations:
            raise CapacityContractError(
                "live fair selector did not cover the initial eligible set within "
                "the derived starvation bound"
            )

        for _node_id in environment.node_ids:
            connection = self._engine.connect()
            transaction = connection.begin()
            try:
                started = time.perf_counter_ns()
                connection.execute(sa.text("SELECT 1"))
                transaction.commit()
                commit_samples.append((time.perf_counter_ns() - started) / 1_000_000)
            finally:
                if transaction.is_active:
                    transaction.rollback()
                connection.close()

        with self._engine.connect() as connection:
            table_after_digest = self._work_item_table_digest(connection)
            if table_after_digest != table_before_digest:
                raise CapacityContractError(
                    "rollback-only workload changed runtime_work_items"
                )
            lock_observation = self._lock_observation(connection)
            connection_observation = self._connection_observation(
                connection,
                environment.postgres_settings,
            )
            partition_count = int(
                connection.execute(
                    sa.text(
                        "SELECT count(*) FROM pg_partitioned_table p "
                        "JOIN pg_class c ON c.oid = p.partrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' "
                        "AND c.relname = 'runtime_work_items'"
                    )
                ).scalar_one()
            )

        if backlog_age > analytical_seconds:
            raise CapacityContractError(
                "observed eligible backlog exceeds the analytical starvation bound"
            )
        rate: float | str
        if not observed_rows or claim_elapsed_seconds <= 0:
            rate = UNSUPPORTED_CAPACITY
        else:
            rate = len(observed_rows) / claim_elapsed_seconds
        partition_policy = (
            "runtime_work_items:postgres-partitioned"
            if partition_count > 0
            else UNSUPPORTED_CAPACITY
        )
        vacuum_policy = ";".join(
            f"{name}={environment.postgres_settings[name]}"
            for name in (
                "autovacuum",
                "autovacuum_naptime",
                "autovacuum_vacuum_scale_factor",
            )
        )
        return build_capacity_envelope(
            observed_at=datetime.now(timezone.utc),
            database_name=environment.database_name,
            database_role=environment.database_role,
            postgres_version=environment.postgres_version,
            postgres_settings=environment.postgres_settings,
            node_ids=environment.node_ids,
            node_profile_digests=(environment.node_profile_digest,),
            fair_share_policy_digest=fair_share_policy_digest(policy),
            fair_share_policy_parameters=fair_share_policy_payload(policy),
            project_count=len(initial_projects),
            capability_count=len(initial_capabilities),
            eligible_row_count=len(initial_ids),
            initial_eligible_ids_digest=_observation_digest(initial_ids),
            observed_claimed_ids_digest=_observation_digest(observed_ids),
            observed_claimed_count=len(observed_ids),
            observed_project_claim_counts=dict(
                Counter(str(row["project_key"]) for row in observed_rows.values())
            ),
            observed_capability_claim_counts=dict(
                Counter(str(row["capability_id"]) for row in observed_rows.values())
            ),
            analytical_max_selection_rounds=analytical_rounds,
            analytical_starvation_bound_seconds=analytical_seconds,
            measured_max_selection_round=measured_max_round,
            measured_max_selection_seconds=measured_max_seconds,
            violations=violations,
            work_item_table_before_digest=table_before_digest,
            work_item_table_after_digest=table_after_digest,
            work_item_table_unchanged=table_before_digest == table_after_digest,
            terminal_row_count=terminal_row_count,
            claim_batch_size=config.claim_batch_size,
            work_item_rate_per_second=rate,
            claim_latency_samples_ms=claim_samples,
            commit_latency_samples_ms=commit_samples,
            lock_wait_ms=UNSUPPORTED_CAPACITY,
            lock_observation=lock_observation,
            connection_observation=connection_observation,
            backlog_age_seconds=backlog_age,
            max_starvation_seconds=analytical_seconds,
            vacuum_policy=vacuum_policy,
            partition_policy=partition_policy,
            archive_policy=UNSUPPORTED_CAPACITY,
            measurement_notes=(
                "Measured only a dedicated local Unix-socket PostgreSQL fixture.",
                (
                    "Claim rate is a rolled-back SKIP-LOCKED row-selection rate; "
                    "it does not claim production throughput."
                ),
                (
                    "Fairness coverage used the live due_claim_statement and the "
                    "frozen FairSharePolicy; selected rows were temporarily marked "
                    "COMPLETED inside two long transactions and fully rolled back."
                ),
                (
                    "No live provider, external delivery, production store, or "
                    "canonical research write was invoked."
                ),
            ),
        )

    def _verify_no_production_rows(self, connection: sa.Connection) -> None:
        registry = PUBLIC_TABLES["project_scope_registry"]
        scope_rows = (
            connection.execute(
                sa.select(
                    registry.c.project_key,
                    registry.c.resolved_schema,
                )
            )
            .mappings()
            .all()
        )
        if not scope_rows:
            raise UnsafeCapacityEnvironment(
                "capacity baseline requires fixture-owned project rows"
            )
        for row in scope_rows:
            if not str(row["project_key"]).startswith(
                self._guard.allowed_project_prefix
            ) or not str(row["resolved_schema"]).startswith(
                self._guard.allowed_schema_prefix
            ):
                raise UnsafeCapacityEnvironment(
                    "project scope registry contains non-fixture identity"
                )
        for table in PUBLIC_TABLES.values():
            if "project_key" not in table.c:
                continue
            forbidden = connection.execute(
                sa.select(sa.func.count())
                .select_from(table)
                .where(
                    sa.not_(
                        table.c.project_key.startswith(
                            self._guard.allowed_project_prefix
                        )
                    )
                )
            ).scalar_one()
            if int(forbidden):
                raise UnsafeCapacityEnvironment(
                    f"{table.fullname} contains non-fixture project data"
                )
        catalogs = PUBLIC_TABLES["runtime_deployment_catalogs"]
        forbidden_catalogs = connection.execute(
            sa.select(sa.func.count())
            .select_from(catalogs)
            .where(
                sa.not_(
                    catalogs.c.catalog_ref.startswith(
                        self._guard.allowed_catalog_ref_prefix
                    )
                )
            )
        ).scalar_one()
        if int(forbidden_catalogs):
            raise UnsafeCapacityEnvironment(
                "deployment catalog contains non-fixture identity"
            )

    @staticmethod
    def _terminal_row_count(connection: sa.Connection) -> int:
        work = PUBLIC_TABLES["runtime_work_items"]
        return int(
            connection.execute(
                sa.select(sa.func.count())
                .select_from(work)
                .where(work.c.state.in_(_TERMINAL_STATES))
            ).scalar_one()
        )

    @staticmethod
    def _work_item_table_digest(connection: sa.Connection) -> str:
        snapshot = connection.execute(
            sa.text(
                "SELECT COALESCE(jsonb_agg(to_jsonb(w) ORDER BY work_item_id), "
                "'[]'::jsonb)::text FROM public.runtime_work_items AS w"
            )
        ).scalar_one()
        return _observation_digest(json.loads(str(snapshot)))

    @staticmethod
    def _lock_observation(connection: sa.Connection) -> LockObservation:
        row = (
            connection.execute(
                sa.text(
                    "SELECT count(*) AS total_locks, "
                    "count(*) FILTER (WHERE NOT granted) AS ungranted_locks "
                    "FROM pg_locks WHERE database = "
                    "(SELECT oid FROM pg_database WHERE datname = current_database())"
                )
            )
            .mappings()
            .one()
        )
        waiting = connection.execute(
            sa.text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() "
                "AND wait_event_type = 'Lock'"
            )
        ).scalar_one()
        return LockObservation(
            total_locks=int(row["total_locks"]),
            ungranted_locks=int(row["ungranted_locks"]),
            lock_waiting_connections=int(waiting),
        )

    @staticmethod
    def _connection_observation(
        connection: sa.Connection,
        settings: dict[str, str],
    ) -> ConnectionObservation:
        row = (
            connection.execute(
                sa.text(
                    "SELECT count(*) AS database_connections, "
                    "count(*) FILTER (WHERE state = 'active') AS active_connections, "
                    "count(*) FILTER (WHERE state = 'idle in transaction') "
                    "AS idle_in_transaction_connections "
                    "FROM pg_stat_activity WHERE datname = current_database()"
                )
            )
            .mappings()
            .one()
        )
        return ConnectionObservation(
            database_connections=int(row["database_connections"]),
            active_connections=int(row["active_connections"]),
            idle_in_transaction_connections=int(row["idle_in_transaction_connections"]),
            max_connections_setting=int(settings["max_connections"]),
        )


__all__ = [
    "CapacityEnvironmentGuard",
    "CapacityMeasurementConfig",
    "PostgresCapacityObserver",
    "UnsafeCapacityEnvironment",
    "VerifiedCapacityEnvironment",
    "validate_capacity_database_url",
]
