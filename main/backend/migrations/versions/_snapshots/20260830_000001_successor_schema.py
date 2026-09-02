"""Immutable schema snapshot owned by Alembic revision ``20260830_000001``.

Keep this module version-locked.  It deliberately duplicates the frozen P0-B
SQLAlchemy Core declarations so the historical revision never imports mutable
application runtime code.  Future application schema changes require a new
revision and a new snapshot; this file must not be edited in place.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

PUBLIC_SCHEMA: Final = "public"
DIGEST = sa.CHAR(64)
PROJECT_KEY = sa.String(128)
IDENTITY = sa.String(128)
REF = sa.Text
TS = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _created() -> sa.Column:
    return sa.Column("created_at", TS, nullable=False, server_default=sa.func.now())


def _updated() -> sa.Column:
    return sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())


def _enum_check(column: str, values: tuple[str, ...], name: str) -> sa.CheckConstraint:
    quoted = ", ".join(repr(value) for value in values)
    return sa.CheckConstraint(f"{column} IN ({quoted})", name=name)


PUBLIC_METADATA = sa.MetaData(schema=PUBLIC_SCHEMA)


runtime_deployment_catalogs = sa.Table(
    "runtime_deployment_catalogs",
    PUBLIC_METADATA,
    sa.Column("catalog_digest", DIGEST, primary_key=True),
    sa.Column("catalog_version", sa.String(64), nullable=False),
    sa.Column("catalog_ref", REF, nullable=False),
    sa.Column("node_profile_digest", DIGEST, nullable=False),
    sa.Column("security_profile_digest", DIGEST, nullable=False),
    sa.Column("resource_profile_digest", DIGEST, nullable=False),
    _created(),
)

runtime_nodes = sa.Table(
    "runtime_nodes",
    PUBLIC_METADATA,
    sa.Column("node_id", IDENTITY, primary_key=True),
    sa.Column("node_profile_digest", DIGEST, nullable=False),
    sa.Column(
        "deployment_catalog_digest",
        DIGEST,
        sa.ForeignKey("public.runtime_deployment_catalogs.catalog_digest", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("runtime_protocol_version", sa.String(64), nullable=False),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("heartbeat_at", TS, nullable=False),
    sa.Column("started_at", TS, nullable=False),
    sa.Column("drain_requested_at", TS),
    sa.Column("current_claim_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    _enum_check("state", ("ACTIVE", "DRAINING", "OFFLINE"), "ck_rt_nodes_state"),
    sa.CheckConstraint("current_claim_count >= 0 AND revision >= 0", name="ck_rt_nodes_claim_count"),
    sa.Index("ix_rt_nodes_state_heartbeat", "state", "heartbeat_at"),
)

project_scope_registry = sa.Table(
    "project_scope_registry",
    PUBLIC_METADATA,
    sa.Column("project_key", PROJECT_KEY, primary_key=True),
    sa.Column("registry_revision", sa.BigInteger, primary_key=True),
    sa.Column("resolved_schema", sa.String(128), nullable=False),
    sa.Column("scope_digest", DIGEST, nullable=False),
    sa.Column("incarnation", IDENTITY, nullable=False),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("updated_by", IDENTITY, nullable=False),
    sa.Column("approval_ref", REF),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "scope_digest", name="uq_scope_project_digest"),
    sa.UniqueConstraint("resolved_schema", "incarnation", name="uq_scope_schema_incarnation"),
    sa.CheckConstraint("registry_revision >= 0", name="ck_scope_revision"),
    _enum_check("state", ("ACTIVE", "MIGRATING", "RETIRED"), "ck_scope_state"),
    sa.Index(
        "uq_scope_one_active_per_project",
        "project_key",
        unique=True,
        postgresql_where=sa.text("state = 'ACTIVE'"),
    ),
    sa.Index("ix_scope_project_state", "project_key", "state"),
)

runtime_program_refs = sa.Table(
    "runtime_program_refs",
    PUBLIC_METADATA,
    sa.Column("program_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("program_digest", DIGEST, nullable=False),
    sa.Column("project_storage_ref", REF, nullable=False),
    sa.Column("contract_version", sa.String(64), nullable=False),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "program_id", name="uq_program_ref_scope_id"),
    sa.UniqueConstraint("project_key", "program_digest", name="uq_program_ref_scope_digest"),
    sa.Index("ix_program_ref_project_created", "project_key", "created_at"),
)

runtime_plan_refs = sa.Table(
    "runtime_plan_refs",
    PUBLIC_METADATA,
    sa.Column("plan_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("plan_digest", DIGEST, nullable=False),
    sa.Column("program_id", IDENTITY, nullable=False),
    sa.Column("program_digest", DIGEST, nullable=False),
    sa.Column("project_storage_ref", REF, nullable=False),
    sa.Column("compiler_id", IDENTITY, nullable=False),
    sa.Column("compiler_version", sa.String(64), nullable=False),
    sa.Column("operation_catalog_id", IDENTITY, nullable=False),
    sa.Column("catalog_version", sa.String(64), nullable=False),
    sa.Column("catalog_digest", DIGEST, nullable=False),
    sa.Column("effect_closure_digest", DIGEST, nullable=False),
    sa.Column("authority_closure_digest", DIGEST, nullable=False),
    sa.Column("resource_closure_digest", DIGEST, nullable=False),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "plan_id", name="uq_plan_ref_scope_id"),
    sa.UniqueConstraint("project_key", "plan_digest", name="uq_plan_ref_scope_digest"),
    sa.ForeignKeyConstraint(
        ("project_key", "program_id"),
        ("public.runtime_program_refs.project_key", "public.runtime_program_refs.program_id"),
        name="fk_plan_ref_program_scope",
        ondelete="RESTRICT",
    ),
    sa.Index("ix_plan_ref_project_created", "project_key", "created_at"),
)

runtime_runs = sa.Table(
    "runtime_runs",
    PUBLIC_METADATA,
    sa.Column("run_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("project_registry_revision", sa.BigInteger, nullable=False),
    sa.Column("project_scope_digest", DIGEST, nullable=False),
    sa.Column("resolved_schema", sa.String(128), nullable=False),
    sa.Column("program_id", IDENTITY, nullable=False),
    sa.Column("program_digest", DIGEST, nullable=False),
    sa.Column("plan_id", IDENTITY),
    sa.Column("plan_digest", DIGEST),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("next_event_seq", sa.BigInteger, nullable=False, server_default="1"),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("incarnation", IDENTITY, nullable=False),
    sa.Column("submission_authority_digest", DIGEST, nullable=False),
    sa.Column("qualification_digest", DIGEST),
    sa.Column("cancellation_requested", sa.Boolean, nullable=False, server_default=sa.false()),
    _created(),
    _updated(),
    sa.Column("finished_at", TS),
    sa.UniqueConstraint("project_key", "run_id", name="uq_run_scope_id"),
    sa.ForeignKeyConstraint(
        ("project_key", "project_registry_revision"),
        ("public.project_scope_registry.project_key", "public.project_scope_registry.registry_revision"),
        name="fk_run_project_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ("project_key", "program_id"),
        ("public.runtime_program_refs.project_key", "public.runtime_program_refs.program_id"),
        name="fk_run_program_scope",
        ondelete="RESTRICT",
    ),
    sa.ForeignKeyConstraint(
        ("project_key", "plan_id"),
        ("public.runtime_plan_refs.project_key", "public.runtime_plan_refs.plan_id"),
        name="fk_run_plan_scope",
        ondelete="RESTRICT",
    ),
    sa.CheckConstraint("revision >= 0 AND execution_epoch >= 0 AND next_event_seq >= 1", name="ck_run_counters"),
    sa.CheckConstraint(
        "(state = 'SUBMITTED' AND plan_id IS NULL AND plan_digest IS NULL AND qualification_digest IS NULL) "
        "OR (state = 'COMPILING' AND qualification_digest IS NULL AND "
        "((plan_id IS NULL AND plan_digest IS NULL) OR (plan_id IS NOT NULL AND plan_digest IS NOT NULL))) "
        "OR (state NOT IN ('SUBMITTED','COMPILING') AND plan_id IS NOT NULL AND plan_digest IS NOT NULL AND qualification_digest IS NOT NULL)",
        name="ck_run_state_plan_required",
    ),
    _enum_check(
        "state",
        ("SUBMITTED", "COMPILING", "AWAITING_APPROVAL", "READY", "RUNNING", "WAITING", "RECONCILING", "CANCELLING", "COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED"),
        "ck_run_state",
    ),
    sa.Index("ix_run_project_state", "project_key", "state"),
    sa.Index("ix_run_project_updated", "project_key", "updated_at"),
)

runtime_steps = sa.Table(
    "runtime_steps",
    PUBLIC_METADATA,
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, primary_key=True),
    sa.Column("step_id", IDENTITY, primary_key=True),
    sa.Column("operation_id", IDENTITY, nullable=False),
    sa.Column("operation_kind", sa.String(128), nullable=False),
    sa.Column("operation_version", sa.String(64), nullable=False),
    sa.Column("state", sa.String(32), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("input_digest", DIGEST),
    sa.Column("output_digest", DIGEST),
    sa.Column("failure_digest", DIGEST),
    sa.Column("effect_class", sa.String(64), nullable=False),
    sa.Column("resource_class", sa.String(64), nullable=False),
    sa.Column("concurrency_key", sa.String(256)),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("claim_owner", sa.String(16), nullable=False),
    sa.Column("claim_authority_epoch", sa.BigInteger, nullable=False),
    sa.Column("claim_policy_digest", DIGEST, nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("max_attempts", sa.Integer, nullable=False, server_default="1"),
    sa.Column("next_retry_at", TS),
    sa.Column("lease_token", IDENTITY),
    sa.Column("lease_owner", IDENTITY),
    sa.Column("lease_expires_at", TS),
    sa.Column("heartbeat_at", TS),
    sa.Column("started_at", TS),
    sa.Column("finished_at", TS),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "run_id", "step_id", name="uq_step_scope_id"),
    sa.ForeignKeyConstraint(
        ("project_key", "run_id"),
        ("public.runtime_runs.project_key", "public.runtime_runs.run_id"),
        name="fk_step_run_scope",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("revision >= 0 AND execution_epoch >= 0 AND attempt_count >= 0 AND max_attempts >= 1", name="ck_step_counters"),
    _enum_check("claim_owner", ("legacy", "successor"), "ck_step_claim_owner"),
    _enum_check(
        "state",
        ("PENDING", "AWAITING_APPROVAL", "READY", "CLAIMED", "RUNNING", "COMMITTING", "WAITING_EXTERNAL", "RETRY_SCHEDULED", "RECONCILING", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED", "SUPERSEDED", "NOT_SELECTED", "SKIPPED_BY_DECISION"),
        "ck_step_state",
    ),
    sa.Index("ix_step_project_run_state", "project_key", "run_id", "state"),
    sa.Index("ix_step_project_lease", "project_key", "lease_expires_at"),
)

runtime_effect_attempts = sa.Table(
    "runtime_effect_attempts",
    PUBLIC_METADATA,
    sa.Column("attempt_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY, nullable=False),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False),
    sa.Column("incarnation", IDENTITY, nullable=False),
    sa.Column("assignment_digest", DIGEST, nullable=False),
    sa.Column("handler_binding_digest", DIGEST, nullable=False),
    sa.Column("handler_realization_digest", DIGEST, nullable=False),
    sa.Column("idempotency_key", REF, nullable=False),
    sa.Column("authorization_digest", DIGEST, nullable=False),
    sa.Column("input_digest", DIGEST, nullable=False),
    sa.Column("claim_binding_json", JSONB, nullable=False),
    sa.Column("claim_binding_digest", DIGEST, nullable=False),
    sa.Column("delivery_intent_ref", REF),
    sa.Column("disposition", sa.String(24), nullable=False),
    sa.Column("external_provider", sa.String(128)),
    sa.Column("external_ref", REF),
    sa.Column("receipt_ref", REF),
    sa.Column("receipt_digest", DIGEST),
    sa.Column("failure_ref", REF),
    sa.Column("failure_digest", DIGEST),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("dispatched_at", TS),
    sa.Column("started_at", TS),
    sa.Column("finished_at", TS),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "attempt_id", name="uq_attempt_scope_id"),
    sa.UniqueConstraint("project_key", "idempotency_key", name="uq_attempt_scope_idem"),
    sa.ForeignKeyConstraint(
        ("project_key", "run_id", "step_id"),
        ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"),
        name="fk_attempt_step_scope",
        ondelete="RESTRICT",
    ),
    _enum_check("disposition", ("NOT_STARTED", "IN_FLIGHT", "SUCCEEDED", "FAILED", "OUTCOME_UNKNOWN"), "ck_attempt_disposition"),
    sa.CheckConstraint("revision >= 0", name="ck_attempt_revision"),
    sa.CheckConstraint(
        "handler_binding_digest = handler_realization_digest",
        name="ck_attempt_exact_handler_realization",
    ),
    sa.Index("ix_attempt_project_step", "project_key", "run_id", "step_id"),
)

runtime_events = sa.Table(
    "runtime_events",
    PUBLIC_METADATA,
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, primary_key=True),
    sa.Column("seq", sa.BigInteger, primary_key=True),
    sa.Column("event_type", sa.String(128), nullable=False),
    sa.Column("schema_version", sa.String(64), nullable=False),
    sa.Column("step_id", IDENTITY),
    sa.Column("attempt_id", IDENTITY),
    sa.Column("event_metadata_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("payload_ref", REF),
    sa.Column("payload_digest", DIGEST),
    sa.Column("authority_digest", DIGEST, nullable=False),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "run_id", "seq", name="uq_event_scope_seq"),
    sa.ForeignKeyConstraint(
        ("project_key", "run_id"),
        ("public.runtime_runs.project_key", "public.runtime_runs.run_id"),
        name="fk_event_run_scope",
        ondelete="CASCADE",
    ),
    sa.CheckConstraint("seq >= 1", name="ck_event_seq"),
    sa.CheckConstraint("(payload_ref IS NULL) = (payload_digest IS NULL)", name="ck_event_payload_ref_digest"),
    sa.Index("ix_event_project_run_created", "project_key", "run_id", "created_at"),
)

runtime_work_items = sa.Table(
    "runtime_work_items",
    PUBLIC_METADATA,
    sa.Column("work_item_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY),
    sa.Column("assignment_kind", sa.String(32), nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("operation_contract_digest", DIGEST),
    sa.Column("assignment_digest", DIGEST, nullable=False),
    sa.Column("assignment_binding_json", JSONB, nullable=False),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False),
    sa.Column("assignment_incarnation", IDENTITY, nullable=False),
    sa.Column("input_closure_digest", DIGEST),
    sa.Column("claim_authority_epoch", sa.BigInteger, nullable=False),
    sa.Column("claim_policy_digest", DIGEST, nullable=False),
    sa.Column("handler_binding_kind", sa.String(32), nullable=False),
    sa.Column("handler_binding_ref", REF, nullable=False),
    sa.Column("handler_binding_digest", DIGEST, nullable=False),
    sa.Column("deployment_catalog_digest", DIGEST, nullable=False),
    sa.Column("runtime_protocol_version", sa.String(64), nullable=False),
    sa.Column("interpreter_profile_digest", DIGEST),
    sa.Column("required_node_profile_selector", REF, nullable=False),
    sa.Column("program_digest", DIGEST),
    sa.Column("plan_digest", DIGEST),
    sa.Column("qualification_digest", DIGEST),
    sa.Column("expected_step_revision", sa.BigInteger),
    sa.Column("reconciliation_attempt_id", DIGEST),
    sa.Column("source_ref", REF),
    sa.Column("source_digest", DIGEST),
    sa.Column("declared_loss_profile_ref", REF),
    sa.Column("predecessor_plan_digest", DIGEST),
    sa.Column("source_value_digest", DIGEST),
    sa.Column("target_domain_contract_snapshot_digest", DIGEST),
    sa.Column("payload_ref", REF),
    sa.Column("payload_digest", DIGEST),
    sa.Column("delivery_intent_ref", REF),
    sa.Column("authority_digest", DIGEST, nullable=False),
    sa.Column("resource_policy_digest", DIGEST, nullable=False),
    sa.Column("resource_policy_epoch", sa.BigInteger),
    sa.Column("queue_eligibility_digest", DIGEST),
    sa.Column("resource_class", sa.String(64)),
    sa.Column("resource_units", sa.Numeric(20, 6)),
    sa.Column("concurrency_key", sa.String(256)),
    sa.Column("provider_key", sa.String(256)),
    sa.Column("recovery_handler_binding_ref", REF),
    sa.Column("recovery_handler_binding_digest", DIGEST),
    sa.Column("recovery_binding_json", JSONB),
    sa.Column("authoritative_readback_profile_ref", REF),
    sa.Column("fairness_key", sa.String(256), nullable=False),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("wait_reason", sa.String(40)),
    sa.Column("declared_priority", sa.Integer, nullable=False, server_default="0"),
    sa.Column("enqueue_seq", sa.BigInteger, sa.Identity(), nullable=False),
    sa.Column("enqueued_at", TS, nullable=False),
    sa.Column("due_at", TS, nullable=False),
    sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("lease_token", IDENTITY),
    sa.Column("lease_owner", IDENTITY),
    sa.Column("lease_expires_at", TS),
    sa.Column("claim_attempt_id", DIGEST),
    sa.Column("claim_binding_json", JSONB),
    sa.Column("claim_binding_digest", DIGEST),
    sa.Column("deadline_at", TS),
    sa.Column("schedule_occurrence_ref", REF),
    sa.Column("last_failure_ref", REF),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "work_item_id", name="uq_work_scope_id"),
    sa.ForeignKeyConstraint(
        ("project_key", "run_id"),
        ("public.runtime_runs.project_key", "public.runtime_runs.run_id"),
        name="fk_work_run_scope",
        ondelete="CASCADE",
    ),
    sa.ForeignKeyConstraint(
        ("project_key", "run_id", "step_id"),
        ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"),
        name="fk_work_step_scope",
        ondelete="CASCADE",
    ),
    _enum_check("assignment_kind", ("COMPILE", "QUALIFY", "INTERPRET", "VERIFY_ADMIT", "PROJECT", "RECONCILE", "MATERIALIZE_SUCCESSOR"), "ck_work_assignment_kind"),
    _enum_check("state", ("PENDING", "READY", "CLAIMED", "WAITING", "COMPLETED", "FAILED", "CANCELLED", "SUPERSEDED"), "ck_work_state"),
    _enum_check("wait_reason", ("RESOURCE_LIMIT", "INTERPRETER_UNAVAILABLE", "AUTHORITY_STALE", "BACKOFF", "SCHEDULE_NOT_DUE"), "ck_work_wait_reason"),
    sa.CheckConstraint("(state = 'WAITING' AND wait_reason IS NOT NULL) OR (state <> 'WAITING' AND wait_reason IS NULL)", name="ck_work_wait_reason_state"),
    sa.CheckConstraint("declared_priority >= 0 AND attempt_count >= 0 AND revision >= 0", name="ck_work_counters"),
    sa.CheckConstraint(
        "expected_step_revision IS NULL OR expected_step_revision >= 0",
        name="ck_work_expected_step_revision",
    ),
    sa.CheckConstraint(
        "execution_epoch >= 0 AND claim_authority_epoch >= 0",
        name="ck_work_assignment_epochs",
    ),
    sa.CheckConstraint(
        "resource_policy_epoch IS NULL OR resource_policy_epoch >= 0",
        name="ck_work_resource_policy_epoch",
    ),
    sa.CheckConstraint(
        "resource_units IS NULL OR resource_units > 0",
        name="ck_work_resource_units",
    ),
    sa.CheckConstraint("(payload_ref IS NULL) = (payload_digest IS NULL)", name="ck_work_payload_ref_digest"),
    sa.CheckConstraint(
        "(state = 'CLAIMED') = "
        "(lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
        name="ck_work_claimed_lease",
    ),
    sa.CheckConstraint(
        "state <> 'CLAIMED' OR "
        "(claim_attempt_id IS NOT NULL AND claim_binding_json IS NOT NULL "
        "AND claim_binding_digest IS NOT NULL)",
        name="ck_work_claim_binding",
    ),
    sa.CheckConstraint(
        "CASE assignment_kind "
        "WHEN 'COMPILE' THEN handler_binding_kind = 'COMPILER' "
        "AND program_digest IS NOT NULL AND step_id IS NULL "
        "WHEN 'QUALIFY' THEN handler_binding_kind = 'QUALIFICATION' "
        "AND plan_digest IS NOT NULL AND resource_policy_epoch IS NOT NULL "
        "WHEN 'INTERPRET' THEN handler_binding_kind = 'INTERPRETER' "
        "AND step_id IS NOT NULL AND operation_contract_digest IS NOT NULL "
        "AND program_digest IS NOT NULL AND plan_digest IS NOT NULL "
        "AND qualification_digest IS NOT NULL "
        "AND expected_step_revision IS NOT NULL "
        "AND interpreter_profile_digest IS NOT NULL "
        "AND queue_eligibility_digest IS NOT NULL "
        "AND resource_policy_epoch IS NOT NULL AND resource_class IS NOT NULL "
        "AND resource_units IS NOT NULL "
        "AND recovery_handler_binding_ref IS NOT NULL "
        "AND recovery_handler_binding_digest IS NOT NULL "
        "AND recovery_binding_json IS NOT NULL "
        "AND authoritative_readback_profile_ref IS NOT NULL "
        "WHEN 'VERIFY_ADMIT' THEN handler_binding_kind = 'INTERPRETER' "
        "AND step_id IS NOT NULL AND operation_contract_digest IS NOT NULL "
        "AND program_digest IS NOT NULL AND plan_digest IS NOT NULL "
        "AND qualification_digest IS NOT NULL "
        "AND expected_step_revision IS NOT NULL "
        "AND interpreter_profile_digest IS NOT NULL "
        "AND queue_eligibility_digest IS NOT NULL "
        "AND resource_policy_epoch IS NOT NULL AND resource_class IS NOT NULL "
        "AND resource_units IS NOT NULL "
        "AND recovery_handler_binding_ref IS NOT NULL "
        "AND recovery_handler_binding_digest IS NOT NULL "
        "AND recovery_binding_json IS NOT NULL "
        "AND authoritative_readback_profile_ref IS NOT NULL "
        "WHEN 'PROJECT' THEN handler_binding_kind = 'PROJECTOR' "
        "AND source_ref IS NOT NULL AND source_digest IS NOT NULL "
        "AND declared_loss_profile_ref IS NOT NULL "
        "WHEN 'RECONCILE' THEN handler_binding_kind = 'RECOVERY' "
        "AND step_id IS NOT NULL AND operation_contract_digest IS NOT NULL "
        "AND program_digest IS NOT NULL AND plan_digest IS NOT NULL "
        "AND qualification_digest IS NOT NULL "
        "AND expected_step_revision IS NOT NULL "
        "AND interpreter_profile_digest IS NOT NULL "
        "AND reconciliation_attempt_id IS NOT NULL "
        "AND authoritative_readback_profile_ref IS NOT NULL "
        "WHEN 'MATERIALIZE_SUCCESSOR' THEN handler_binding_kind = 'MATERIALIZER' "
        "AND predecessor_plan_digest IS NOT NULL AND source_value_digest IS NOT NULL "
        "AND target_domain_contract_snapshot_digest IS NOT NULL "
        "ELSE FALSE END",
        name="ck_work_assignment_binding",
    ),
    sa.Index("ix_work_due_claim", "state", "due_at", sa.desc("declared_priority"), "enqueue_seq", "project_key"),
    sa.Index("ix_work_project_run_state", "project_key", "run_id", "state"),
    sa.Index("ix_work_project_lease", "project_key", "lease_expires_at"),
)

runtime_values = sa.Table(
    "runtime_values",
    PUBLIC_METADATA,
    sa.Column("value_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("object_type", sa.String(128), nullable=False),
    sa.Column("codec_id", IDENTITY, nullable=False),
    sa.Column("content_digest", DIGEST, nullable=False),
    sa.Column("byte_size", sa.BigInteger, nullable=False),
    sa.Column("project_value_ref", REF),
    sa.Column("runtime_blob_ref", REF),
    sa.Column("canonical_ref", REF),
    sa.Column("storage_digest", DIGEST, nullable=False),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("temporary_storage_ref", REF),
    sa.Column("final_storage_ref", REF),
    sa.Column("write_intent_digest", DIGEST),
    sa.Column("write_receipt_digest", DIGEST),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "value_id", name="uq_value_scope_id"),
    sa.UniqueConstraint("project_key", "content_digest", "codec_id", name="uq_value_scope_content"),
    sa.CheckConstraint("byte_size >= 0 AND revision >= 0", name="ck_value_counters"),
    sa.CheckConstraint("num_nonnulls(project_value_ref, runtime_blob_ref, canonical_ref) = 1", name="ck_value_one_opaque_ref"),
    _enum_check("state", ("PREPARED", "AVAILABLE", "FAILED", "ORPHANED"), "ck_value_state"),
    sa.Index("ix_value_project_state", "project_key", "state"),
)

runtime_staged_artifacts = sa.Table(
    "runtime_staged_artifacts",
    PUBLIC_METADATA,
    sa.Column("artifact_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY, nullable=False),
    sa.Column("attempt_id", IDENTITY),
    sa.Column("value_id", IDENTITY, nullable=False),
    sa.Column("receipt_ref", REF),
    sa.Column("qualifier_ref", REF, nullable=False),
    sa.Column("loss_profile_ref", REF),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "artifact_id", name="uq_staged_scope_id"),
    sa.ForeignKeyConstraint(("project_key", "run_id", "step_id"), ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"), name="fk_staged_step_scope", ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(("project_key", "value_id"), ("public.runtime_values.project_key", "public.runtime_values.value_id"), name="fk_staged_value_scope", ondelete="RESTRICT"),
    _enum_check("state", ("STAGED", "VERIFIED", "ADMITTED", "REJECTED", "ORPHANED"), "ck_staged_state"),
    sa.Index("ix_staged_project_run_state", "project_key", "run_id", "state"),
)

runtime_approvals = sa.Table(
    "runtime_approvals",
    PUBLIC_METADATA,
    sa.Column("approval_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("actor_id", IDENTITY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY),
    sa.Column("payload_digest", DIGEST, nullable=False),
    sa.Column("decision", sa.String(24), nullable=False),
    sa.Column("expires_at", TS),
    sa.Column("authority_digest", DIGEST, nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "approval_id", name="uq_approval_scope_id"),
    sa.ForeignKeyConstraint(("project_key", "run_id"), ("public.runtime_runs.project_key", "public.runtime_runs.run_id"), name="fk_approval_run_scope", ondelete="CASCADE"),
    sa.CheckConstraint("revision >= 0", name="ck_approval_revision"),
    _enum_check("decision", ("APPROVED", "REJECTED", "REVOKED"), "ck_approval_decision"),
    sa.Index("ix_approval_project_run", "project_key", "run_id", "created_at"),
)

runtime_qualifications = sa.Table(
    "runtime_qualifications",
    PUBLIC_METADATA,
    sa.Column("qualification_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("plan_id", IDENTITY, nullable=False),
    sa.Column("plan_digest", DIGEST, nullable=False),
    sa.Column("authority_context_digest", DIGEST, nullable=False),
    sa.Column("decision", sa.String(24), nullable=False),
    sa.Column("qualification_digest", DIGEST, nullable=False),
    sa.Column("qualification_binding_digest", DIGEST, nullable=False),
    sa.Column("qualified_plan_json", JSONB, nullable=False),
    sa.Column("qualification_binding_json", JSONB, nullable=False),
    sa.Column("queue_eligibility_digest", DIGEST),
    sa.Column("resource_policy_epoch", sa.BigInteger),
    sa.Column("approval_ref", IDENTITY),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "qualification_id", name="uq_qualification_scope_id"),
    sa.ForeignKeyConstraint(("project_key", "run_id"), ("public.runtime_runs.project_key", "public.runtime_runs.run_id"), name="fk_qualification_run_scope", ondelete="CASCADE"),
    _enum_check("decision", ("QUALIFIED", "REJECTED", "AWAITING_APPROVAL"), "ck_qualification_decision"),
    sa.Index("ix_qualification_project_run", "project_key", "run_id"),
)

runtime_step_authorizations = sa.Table(
    "runtime_step_authorizations",
    PUBLIC_METADATA,
    sa.Column("authorization_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY, nullable=False),
    sa.Column("operation_kind", sa.String(128), nullable=False),
    sa.Column("operation_contract_digest", DIGEST, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("claim_owner", sa.String(16), nullable=False),
    sa.Column("claim_authority_epoch", sa.BigInteger, nullable=False),
    sa.Column("claim_policy_digest", DIGEST, nullable=False),
    sa.Column("payload_digest", DIGEST, nullable=False),
    sa.Column("actor_id", IDENTITY, nullable=False),
    sa.Column("project_registry_revision", sa.BigInteger, nullable=False),
    sa.Column("project_scope_digest", DIGEST, nullable=False),
    sa.Column("grant_epoch", sa.BigInteger, nullable=False),
    sa.Column("expires_at", TS),
    sa.Column("approval_ref", IDENTITY),
    sa.Column("authorization_digest", DIGEST, nullable=False),
    sa.Column("interpreter_binding_digest", DIGEST, nullable=False),
    sa.Column("deployment_catalog_digest", DIGEST, nullable=False),
    sa.Column("authority_source_bindings_json", JSONB, nullable=False),
    sa.Column("grants_digest", DIGEST, nullable=False),
    sa.Column("approval_refs_json", JSONB, nullable=False),
    sa.Column("resource_ceiling_digest", DIGEST, nullable=False),
    sa.Column("resource_policy_epoch", sa.BigInteger, nullable=False),
    sa.Column("queue_eligibility_digest", DIGEST, nullable=False),
    sa.Column("canonical_base_revision", sa.BigInteger, nullable=False),
    sa.Column("canonical_incarnation", IDENTITY, nullable=False),
    sa.Column("authorization_binding_json", JSONB, nullable=False),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "authorization_id", name="uq_step_auth_scope_id"),
    sa.UniqueConstraint("project_key", "run_id", "step_id", "claim_authority_epoch", name="uq_step_auth_epoch"),
    sa.ForeignKeyConstraint(("project_key", "run_id", "step_id"), ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"), name="fk_step_auth_step_scope", ondelete="CASCADE"),
    _enum_check("claim_owner", ("legacy", "successor"), "ck_step_auth_claim_owner"),
    sa.CheckConstraint(
        "resource_policy_epoch >= 0 AND canonical_base_revision >= 0",
        name="ck_step_auth_epochs",
    ),
    sa.Index("ix_step_auth_project_run", "project_key", "run_id", "step_id"),
)

runtime_idempotency = sa.Table(
    "runtime_idempotency",
    PUBLIC_METADATA,
    sa.Column("idempotency_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("logical_request_id", REF, nullable=False),
    sa.Column("operation_kind", sa.String(128), nullable=False),
    sa.Column("request_digest", DIGEST, nullable=False),
    sa.Column("run_id", IDENTITY),
    sa.Column("terminal_observation_ref", REF),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "idempotency_id", name="uq_idem_scope_id"),
    sa.UniqueConstraint("project_key", "capability_id", "logical_request_id", name="uq_idem_scope_cap_request"),
    sa.CheckConstraint("revision >= 0", name="ck_idem_revision"),
    _enum_check("state", ("STARTED", "TERMINAL", "SUPERSEDED"), "ck_idem_state"),
    sa.Index("ix_idem_project_run", "project_key", "run_id"),
)

runtime_projection_offsets = sa.Table(
    "runtime_projection_offsets",
    PUBLIC_METADATA,
    sa.Column("projection_offset_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("projector_id", IDENTITY, nullable=False),
    sa.Column("projector_version", sa.String(64), nullable=False),
    sa.Column("source_revision", sa.BigInteger, nullable=False),
    sa.Column("source_digest", DIGEST, nullable=False),
    sa.Column("offset_ref", REF, nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "projection_offset_id", name="uq_projection_scope_id"),
    sa.UniqueConstraint("project_key", "projector_id", "projector_version", name="uq_projection_owner_version"),
    sa.CheckConstraint("source_revision >= 0 AND revision >= 0", name="ck_projection_revisions"),
    sa.Index("ix_projection_projector", "project_key", "projector_id"),
)

runtime_authority_grants = sa.Table(
    "runtime_authority_grants",
    PUBLIC_METADATA,
    sa.Column("grant_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("actor_id", IDENTITY, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("operation_scope_json", JSONB, nullable=False),
    sa.Column("resource_ceiling_json", JSONB, nullable=False),
    sa.Column("credential_ref", REF),
    sa.Column("grant_epoch", sa.BigInteger, nullable=False),
    sa.Column("expires_at", TS),
    sa.Column("revoked_at", TS),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "grant_id", name="uq_grant_scope_id"),
    sa.UniqueConstraint("project_key", "actor_id", "capability_id", "grant_epoch", name="uq_grant_actor_cap_epoch"),
    sa.CheckConstraint("grant_epoch >= 0 AND revision >= 0", name="ck_grant_revisions"),
    sa.Index("ix_grant_project_actor_cap", "project_key", "actor_id", "capability_id"),
)

runtime_capability_authority = sa.Table(
    "runtime_capability_authority",
    PUBLIC_METADATA,
    sa.Column("project_key", PROJECT_KEY, primary_key=True),
    sa.Column("capability_id", IDENTITY, primary_key=True),
    sa.Column("mode", sa.String(16), nullable=False),
    sa.Column("authority_epoch", sa.BigInteger, nullable=False),
    sa.Column("successor_claim_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("legacy_claim_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("allowlist_digest", DIGEST, nullable=False),
    sa.Column("config_digest", DIGEST, nullable=False),
    sa.Column("effective_at", TS, nullable=False),
    sa.Column("updated_by", IDENTITY, nullable=False),
    sa.Column("approval_ref", REF, nullable=False),
    sa.Column("rollback_target_ref", REF, nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    _enum_check("mode", ("off", "shadow", "canary", "on"), "ck_cap_auth_mode"),
    sa.CheckConstraint("NOT (successor_claim_enabled AND legacy_claim_enabled)", name="ck_cap_auth_single_claim_owner"),
    sa.CheckConstraint("authority_epoch >= 0 AND revision >= 0", name="ck_cap_auth_revisions"),
    sa.Index("ix_cap_auth_project_mode", "project_key", "mode"),
)

runtime_resource_policies = sa.Table(
    "runtime_resource_policies",
    PUBLIC_METADATA,
    sa.Column("resource_policy_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("resource_class", sa.String(64), nullable=False),
    sa.Column("concurrency_limit", sa.Integer, nullable=False),
    sa.Column("max_project_active", sa.Integer, nullable=False),
    sa.Column("max_capability_active", sa.Integer, nullable=False),
    sa.Column("max_resource_active", sa.Integer, nullable=False),
    sa.Column("units_ceiling", sa.Numeric(20, 6), nullable=False),
    sa.Column("budget_ceiling", sa.Numeric(20, 6)),
    sa.Column("provider_limit", sa.Integer),
    sa.Column("policy_epoch", sa.BigInteger, nullable=False),
    sa.Column("policy_digest", DIGEST, nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "resource_policy_id", name="uq_resource_policy_scope_id"),
    sa.UniqueConstraint("project_key", "capability_id", "resource_class", "policy_epoch", name="uq_resource_policy_epoch"),
    sa.CheckConstraint(
        "concurrency_limit > 0 AND max_project_active > 0 "
        "AND max_capability_active > 0 AND max_resource_active > 0 "
        "AND units_ceiling > 0 AND policy_epoch >= 0 AND revision >= 0",
        name="ck_resource_policy_limits",
    ),
    sa.Index("ix_resource_policy_project_cap", "project_key", "capability_id", "resource_class"),
)

runtime_resource_reservations = sa.Table(
    "runtime_resource_reservations",
    PUBLIC_METADATA,
    sa.Column("reservation_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("work_item_id", IDENTITY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY, nullable=False),
    sa.Column("attempt_id", IDENTITY, nullable=False),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False),
    sa.Column("resource_policy_id", IDENTITY, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("policy_epoch", sa.BigInteger, nullable=False),
    sa.Column("policy_digest", DIGEST, nullable=False),
    sa.Column("resource_class", sa.String(64), nullable=False),
    sa.Column("concurrency_key", sa.String(256), nullable=False),
    sa.Column("provider_key", sa.String(256)),
    sa.Column("units", sa.Numeric(20, 6), nullable=False),
    sa.Column("node_id", IDENTITY, nullable=False),
    sa.Column("lease_token", IDENTITY, nullable=False),
    sa.Column("lease_expires_at", TS, nullable=False),
    sa.Column("released_at", TS),
    sa.Column("release_reason", sa.String(64)),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("reservation_digest", DIGEST, nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "reservation_id", name="uq_reservation_scope_id"),
    sa.UniqueConstraint("project_key", "run_id", "step_id", "execution_epoch", name="uq_reservation_step_epoch"),
    sa.ForeignKeyConstraint(("project_key", "run_id", "step_id"), ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"), name="fk_reservation_step_scope", ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(("project_key", "resource_policy_id"), ("public.runtime_resource_policies.project_key", "public.runtime_resource_policies.resource_policy_id"), name="fk_reservation_policy_scope", ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(("project_key", "work_item_id"), ("public.runtime_work_items.project_key", "public.runtime_work_items.work_item_id"), name="fk_reservation_work_scope", ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(("project_key", "attempt_id"), ("public.runtime_effect_attempts.project_key", "public.runtime_effect_attempts.attempt_id"), name="fk_reservation_attempt_scope", ondelete="RESTRICT"),
    sa.ForeignKeyConstraint(("node_id",), ("public.runtime_nodes.node_id",), name="fk_reservation_node", ondelete="RESTRICT"),
    sa.CheckConstraint("execution_epoch >= 0 AND policy_epoch >= 0 AND units > 0 AND revision >= 0", name="ck_reservation_units_epoch"),
    _enum_check("state", ("ACTIVE", "RELEASED", "EXPIRED"), "ck_reservation_state"),
    sa.Index("ix_reservation_project_active", "project_key", "state", "lease_expires_at"),
)

runtime_commit_intents = sa.Table(
    "runtime_commit_intents",
    PUBLIC_METADATA,
    sa.Column("commit_intent_id", IDENTITY, primary_key=True),
    sa.Column("project_key", PROJECT_KEY, nullable=False),
    sa.Column("run_id", IDENTITY, nullable=False),
    sa.Column("step_id", IDENTITY, nullable=False),
    sa.Column("capability_id", IDENTITY, nullable=False),
    sa.Column("canonical_owner_ref", REF, nullable=False),
    sa.Column("object_identity_ref", REF, nullable=False),
    sa.Column("expected_base_revision", sa.BigInteger),
    sa.Column("expected_base_incarnation", IDENTITY),
    sa.Column("content_digest", DIGEST, nullable=False),
    sa.Column("event_digest", DIGEST, nullable=False),
    sa.Column("verification_digest", DIGEST, nullable=False),
    sa.Column("authority_digest", DIGEST, nullable=False),
    sa.Column("idempotency_key", REF, nullable=False),
    sa.Column("state", sa.String(24), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
    sa.Column("canonical_commit_ref", REF),
    sa.Column("receipt_digest", DIGEST),
    _created(),
    _updated(),
    sa.UniqueConstraint("project_key", "commit_intent_id", name="uq_commit_scope_id"),
    sa.UniqueConstraint("project_key", "capability_id", "idempotency_key", name="uq_commit_cap_idem"),
    sa.ForeignKeyConstraint(("project_key", "run_id", "step_id"), ("public.runtime_steps.project_key", "public.runtime_steps.run_id", "public.runtime_steps.step_id"), name="fk_commit_step_scope", ondelete="RESTRICT"),
    sa.CheckConstraint("revision >= 0", name="ck_commit_revision"),
    _enum_check("state", ("PREPARED", "COMMITTED", "REJECTED", "OUTCOME_UNKNOWN"), "ck_commit_state"),
    sa.Index("ix_commit_project_state", "project_key", "state", "updated_at"),
)


PUBLIC_TABLES: Final[dict[str, sa.Table]] = {
    table.name: table
    for table in (
        runtime_deployment_catalogs,
        runtime_nodes,
        project_scope_registry,
        runtime_program_refs,
        runtime_plan_refs,
        runtime_runs,
        runtime_steps,
        runtime_effect_attempts,
        runtime_events,
        runtime_work_items,
        runtime_values,
        runtime_staged_artifacts,
        runtime_approvals,
        runtime_qualifications,
        runtime_step_authorizations,
        runtime_idempotency,
        runtime_projection_offsets,
        runtime_authority_grants,
        runtime_capability_authority,
        runtime_resource_policies,
        runtime_resource_reservations,
        runtime_commit_intents,
    )
}


@dataclass(frozen=True, slots=True)
class ProjectTables:
    research_objects: sa.Table
    research_relations: sa.Table
    research_owner_bindings: sa.Table
    research_program_specs: sa.Table
    research_execution_plans: sa.Table
    successor_values: sa.Table
    successor_receipts: sa.Table

    def as_dict(self) -> dict[str, sa.Table]:
        return {field.name: getattr(self, field.name) for field in fields(self)}


PROJECT_TABLE_NAMES: Final = tuple(field.name for field in fields(ProjectTables))


def project_tables(metadata: sa.MetaData, schema: str) -> ProjectTables:
    """Return the seven P0-B project tables bound to one explicit schema."""

    if not schema or schema in {"pg_catalog", "information_schema"}:
        raise ValueError("project schema must be an explicit non-system schema")

    existing = [metadata.tables.get(f"{schema}.{name}") for name in PROJECT_TABLE_NAMES]
    if all(table is not None for table in existing):
        return ProjectTables(*existing)  # type: ignore[arg-type]
    if any(table is not None for table in existing):
        raise ValueError(f"partial successor project schema already declared: {schema}")

    research_objects = sa.Table(
        "research_objects", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("object_id", IDENTITY, primary_key=True),
        sa.Column("object_type", sa.String(128), nullable=False),
        sa.Column("revision", sa.BigInteger, primary_key=True),
        sa.Column("incarnation", IDENTITY, primary_key=True),
        sa.Column("lifecycle_state", sa.String(32), nullable=False),
        sa.Column("owner_binding_ref", REF, nullable=False),
        sa.Column("content_ref", REF, nullable=False),
        sa.Column("content_digest", DIGEST, nullable=False),
        sa.Column("provenance_closure_digest", DIGEST, nullable=False),
        sa.Column("valid_from", TS),
        sa.Column("valid_to", TS),
        _created(), _updated(),
        sa.CheckConstraint("revision >= 1", name="ck_research_object_revision"),
        _enum_check("lifecycle_state", ("DRAFT", "ADMITTED", "SUPERSEDED", "RETRACTED"), "ck_research_object_state"),
        sa.Index("ix_research_object_project_type", "project_key", "object_type", "lifecycle_state"),
        schema=schema,
    )
    research_relations = sa.Table(
        "research_relations", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("relation_id", IDENTITY, primary_key=True),
        sa.Column("relation_type", sa.String(64), nullable=False),
        sa.Column("source_object_ref", REF, nullable=False),
        sa.Column("target_object_ref", REF, nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("scope_ref", REF, nullable=False),
        sa.Column("uncertainty_profile_ref", REF, nullable=False),
        sa.Column("validity_json", JSONB, nullable=False),
        sa.Column("provenance_closure_digest", DIGEST, nullable=False),
        sa.Column("revision", sa.BigInteger, primary_key=True),
        sa.Column("incarnation", IDENTITY, primary_key=True),
        sa.Column("state", sa.String(32), nullable=False),
        _created(), _updated(),
        _enum_check("relation_type", ("derived_from", "supports", "contradicts", "answers", "opens", "cites", "supersedes", "delivered_as"), "ck_research_relation_type"),
        _enum_check("state", ("ACTIVE", "SUPERSEDED", "RETRACTED", "STALE_SOURCE"), "ck_research_relation_state"),
        sa.CheckConstraint("revision >= 1", name="ck_research_relation_revision"),
        sa.Index("ix_research_relation_project_type", "project_key", "relation_type", "state"),
        schema=schema,
    )
    research_owner_bindings = sa.Table(
        "research_owner_bindings", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("object_type", sa.String(128), primary_key=True),
        sa.Column("owner_epoch", sa.BigInteger, primary_key=True),
        sa.Column("owner_mode", sa.String(40), nullable=False),
        sa.Column("owner_id", IDENTITY, nullable=False),
        sa.Column("readback_profile_ref", REF, nullable=False),
        sa.Column("base_incarnation", IDENTITY),
        sa.Column("rollback_evidence_ref", REF),
        sa.Column("effective_at", TS, nullable=False),
        sa.Column("superseded_at", TS),
        sa.Column("approval_ref", REF, nullable=False),
        _created(), _updated(),
        _enum_check("owner_mode", ("CANONICAL_OWNED", "IMMUTABLE_EXTERNAL_REF", "DECLARED_LOSS_PROJECTION", "RUNTIME_INPUT_ARTIFACT", "RUNTIME_FACT"), "ck_research_owner_mode"),
        sa.CheckConstraint("owner_epoch >= 0", name="ck_research_owner_epoch"),
        sa.Index("ix_research_owner_active", "project_key", "object_type", "superseded_at"),
        schema=schema,
    )
    research_program_specs = sa.Table(
        "research_program_specs", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("program_id", IDENTITY, primary_key=True),
        sa.Column("contract_version", sa.String(64), nullable=False),
        sa.Column("program_digest", DIGEST, nullable=False),
        sa.Column("spec_json", JSONB, nullable=False),
        sa.Column("created_by", IDENTITY, nullable=False),
        _created(), _updated(),
        sa.UniqueConstraint("project_key", "program_digest", name="uq_research_program_digest"),
        sa.Index("ix_research_program_project_created", "project_key", "created_at"),
        schema=schema,
    )
    research_execution_plans = sa.Table(
        "research_execution_plans", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("plan_id", IDENTITY, primary_key=True),
        sa.Column("plan_digest", DIGEST, nullable=False),
        sa.Column("program_id", IDENTITY, nullable=False),
        sa.Column("program_digest", DIGEST, nullable=False),
        sa.Column("compiler_id", IDENTITY, nullable=False),
        sa.Column("compiler_version", sa.String(64), nullable=False),
        sa.Column("operation_catalog_id", IDENTITY, nullable=False),
        sa.Column("catalog_version", sa.String(64), nullable=False),
        sa.Column("catalog_digest", DIGEST, nullable=False),
        sa.Column("plan_json", JSONB, nullable=False),
        sa.Column("effect_closure_digest", DIGEST, nullable=False),
        sa.Column("authority_closure_digest", DIGEST, nullable=False),
        sa.Column("resource_closure_digest", DIGEST, nullable=False),
        _created(), _updated(),
        sa.UniqueConstraint("project_key", "plan_digest", name="uq_research_plan_digest"),
        sa.ForeignKeyConstraint(("project_key", "program_id"), (f"{schema}.research_program_specs.project_key", f"{schema}.research_program_specs.program_id"), name="fk_research_plan_program", ondelete="RESTRICT"),
        sa.Index("ix_research_plan_project_created", "project_key", "created_at"),
        schema=schema,
    )
    successor_values = sa.Table(
        "successor_values", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("value_id", IDENTITY, primary_key=True),
        sa.Column("object_type", sa.String(128), nullable=False),
        sa.Column("codec_id", IDENTITY, nullable=False),
        sa.Column("content_digest", DIGEST, nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("content_json", JSONB),
        sa.Column("content_bytes", sa.LargeBinary),
        sa.Column("source_ref", REF),
        sa.Column("provenance_json", JSONB, nullable=False),
        sa.Column("provenance_digest", DIGEST, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("revision", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("incarnation", IDENTITY, nullable=False),
        sa.Column("write_intent_digest", DIGEST, nullable=False),
        sa.Column("write_receipt_digest", DIGEST),
        _created(), _updated(),
        sa.UniqueConstraint("project_key", "content_digest", "codec_id", name="uq_successor_value_content"),
        sa.CheckConstraint("num_nonnulls(content_json, content_bytes) = 1", name="ck_successor_value_one_content"),
        sa.CheckConstraint("byte_size >= 0 AND revision >= 0", name="ck_successor_value_counters"),
        _enum_check("state", ("PREPARED", "AVAILABLE", "FAILED", "ORPHANED"), "ck_successor_value_state"),
        sa.Index("ix_successor_value_project_state", "project_key", "state"),
        schema=schema,
    )
    successor_receipts = sa.Table(
        "successor_receipts", metadata,
        sa.Column("project_key", PROJECT_KEY, primary_key=True),
        sa.Column("receipt_id", IDENTITY, primary_key=True),
        sa.Column("receipt_digest", DIGEST, nullable=False),
        sa.Column("delivery_intent_ref", REF, nullable=False),
        sa.Column("attempt_ref", REF, nullable=False),
        sa.Column("provider_locator", REF, nullable=False),
        sa.Column("receipt_json", JSONB),
        sa.Column("receipt_bytes", sa.LargeBinary),
        sa.Column("outcome_time", TS, nullable=False),
        _created(), _updated(),
        sa.UniqueConstraint("project_key", "receipt_digest", name="uq_successor_receipt_digest"),
        sa.CheckConstraint("num_nonnulls(receipt_json, receipt_bytes) = 1", name="ck_successor_receipt_one_content"),
        sa.Index("ix_successor_receipt_project_intent", "project_key", "delivery_intent_ref"),
        schema=schema,
    )
    return ProjectTables(
        research_objects=research_objects,
        research_relations=research_relations,
        research_owner_bindings=research_owner_bindings,
        research_program_specs=research_program_specs,
        research_execution_plans=research_execution_plans,
        successor_values=successor_values,
        successor_receipts=successor_receipts,
    )


__all__ = [
    "PROJECT_TABLE_NAMES",
    "PUBLIC_METADATA",
    "PUBLIC_TABLES",
    "ProjectTables",
    "project_tables",
]
