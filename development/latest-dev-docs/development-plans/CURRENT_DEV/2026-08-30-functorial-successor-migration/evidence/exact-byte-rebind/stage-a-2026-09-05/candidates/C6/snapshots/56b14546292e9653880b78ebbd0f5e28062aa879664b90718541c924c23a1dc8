"""Opt-in real-PostgreSQL worker test for the P3 C6 evidence line.

The test runs only against a dedicated test/CI database named by
``SUCCESSOR_TEST_DATABASE_URL``, creates the unique disposable schema
``mrw_p3_c6_worker_test``, proves redacted receipts persist with zero raw
sentinel presence and OUTCOME_UNKNOWN receipts keep provider_calls=0, then
drops the schema.  No live model or network effect exists.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities.agent_core_c6_common import (
    ProjectScope,
    freeze_c6_json_object,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.substrate.postgres.agent_core_c6_worker import (
    AgentCoreC6WorkerStore,
    ForbiddenRawValueDetected,
    ReceiptExactConflict,
)
from app.successor_runtime.substrate.postgres.session import create_runtime_engine

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
SCHEMA = "mrw_p3_c6_worker_test"
PROJECT_KEY = "p3-c6-worker-test"
REGISTRY_REVISION = 1
RESOLVED_SCHEMA = SCHEMA
SCOPE_INCARNATION = "c6-worker-incarnation-1"
SCOPE_DIGEST = ProjectScope(
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_INCARNATION,
    "",
).scope_digest
SENTINEL = "mrw-p3-c6-worker-raw-secret::api_key=fixture-key"


def _require_dedicated_database_url() -> str:
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_ENV} is not set")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail(f"{DATABASE_ENV} must use a PostgreSQL driver")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(
            f"{DATABASE_ENV} must name a dedicated test/CI database; "
            f"refusing database {database_name!r}"
        )
    return database_url


def _scope() -> ProjectScope:
    return ProjectScope(
        PROJECT_KEY,
        REGISTRY_REVISION,
        RESOLVED_SCHEMA,
        SCOPE_INCARNATION,
        "",
    )


def _redaction_receipt() -> c6_3.RedactionReceipt:
    classifications = {"provider.request": "REDACT"}
    policy = c6_3.RedactionPolicyRef(
        policy_id="c6-3-worker-policy",
        policy_version="1",
        policy_digest=c6_3.redaction_policy_digest(
            "c6-3-worker-policy", "1", classifications
        ),
    )
    raw = {"provider": {"request": {"body": SENTINEL}}, "notes": "visible"}
    payload = c6_3.RedactionEvidencePayload(
        schema_version=c6_3.AGENT_CORE_C6_3_PAYLOAD_SCHEMA,
        operation_kind=c6_3.AGENT_CORE_C6_3_KIND,
        project_scope=_scope(),
        source_observation_ref="project-value:source:c6-3-worker",
        source_observation_digest=c6_3.source_observation_digest(raw),
        source_kind="agent_core.tool_event",
        trace_id="trace-worker",
        request_id="req-worker",
        call_id="call-worker",
        interpreter_profile_ref="successor.agent_core.c6_3.redaction.v1",
        policy=policy,
        field_classifications=freeze_c6_json_object(classifications),
        max_input_bytes=c6_3.REDACTION_RESOURCE_CEILING.max_input_bytes,
        max_event_batch=c6_3.REDACTION_RESOURCE_CEILING.max_event_batch,
    )
    receipt = c6_3.redact_observation(payload, raw)
    assert isinstance(receipt, c6_3.RedactionReceipt)
    return receipt


def _provider_unknown_receipt() -> c6_2.ProviderAttemptReceipt:
    request = c6_2.AgentModelStepRequest(
        schema_version=c6_2.AGENT_CORE_C6_2_PAYLOAD_SCHEMA,
        operation_kind=c6_2.AGENT_CORE_C6_2_KIND,
        project_scope=_scope(),
        session_id="session-worker",
        turn_id="turn-worker",
        message_ref="project-value:message:worker",
        transcript_ref="project-value:transcript:worker",
        tool_contract_refs=("source_library.resolve_execution_request.v1",),
        max_iterations=3,
        iteration=1,
        max_tool_calls=2,
        remaining_tool_calls=2,
        provider_profile_ref="receipt_only",
        credential_ref="credential:opaque:worker",
    )
    result = c6_2.interpret_model_step(
        request,
        c6_2.ReceiptOnlyProviderPort(),
        attempt_id="attempt:c6-2:worker",
    )
    return result.receipt


@pytest.fixture(scope="module")
def worker_database() -> Iterator[Engine]:
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    with engine.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        store.install()
        connection.execute(
            sa.text(f'TRUNCATE TABLE "{SCHEMA}"."agent_core_c6_evidence"')
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
        engine.dispose()


def test_redacted_receipt_persists_and_sentinel_is_absent(
    worker_database: Engine,
) -> None:
    receipt = _redaction_receipt()
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        receipt_id = content_digest(receipt.to_plain())
        row = store.persist_receipt(
            cell="c6_3",
            receipt_id=receipt_id,
            outcome_code="RedactionSucceeded",
            provider_calls=0,
            redacted_value=dict(receipt.evidence.redacted_value),
            receipt_plain=receipt.to_plain(),
            forbidden_sentinel=SENTINEL,
        )
        assert row["receipt_id"] == receipt_id
        assert row["cell"] == "c6_3"
        assert store.raw_sentinel_present(SENTINEL) is False
        assert store.count_receipts("c6_3") == 1


def test_store_rejects_raw_sentinel_at_persistence_boundary(
    worker_database: Engine,
) -> None:
    receipt = _redaction_receipt()
    raw_plain = receipt.to_plain()
    raw_plain["evidence"]["redacted_value"]["leaked"] = SENTINEL
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        with pytest.raises(ForbiddenRawValueDetected):
            store.persist_receipt(
                cell="c6_3",
                receipt_id=content_digest(raw_plain),
                outcome_code="RedactionSucceeded",
                provider_calls=0,
                redacted_value={"leaked": SENTINEL},
                receipt_plain=raw_plain,
                forbidden_sentinel=SENTINEL,
            )
        assert store.count_receipts("c6_3") == 1


def test_outcome_unknown_attempt_receipt_readback(
    worker_database: Engine,
) -> None:
    receipt = _provider_unknown_receipt()
    assert receipt.outcome_code == "ProviderOutcomeUnknown"
    assert receipt.provider_calls == 0
    assert receipt.readback_status == "NON_START_PROOF"
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        receipt_id = content_digest(receipt.to_plain())
        row = store.persist_receipt(
            cell="c6_2",
            receipt_id=receipt_id,
            outcome_code=receipt.outcome_code,
            provider_calls=receipt.provider_calls,
            redacted_value={},
            receipt_plain=receipt.to_plain(),
            forbidden_sentinel=SENTINEL,
        )
        assert row["outcome_code"] == "ProviderOutcomeUnknown"
        assert int(row["provider_calls"]) == 0
        assert store.count_receipts("c6_2") == 1


def test_same_id_same_content_is_idempotent(worker_database: Engine) -> None:
    receipt = _redaction_receipt()
    receipt_id = content_digest(receipt.to_plain())
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        first = store.persist_receipt(
            cell="c6_3",
            receipt_id=receipt_id,
            outcome_code="RedactionSucceeded",
            provider_calls=0,
            redacted_value=dict(receipt.evidence.redacted_value),
            receipt_plain=receipt.to_plain(),
            forbidden_sentinel=SENTINEL,
        )
        second = store.persist_receipt(
            cell="c6_3",
            receipt_id=receipt_id,
            outcome_code="RedactionSucceeded",
            provider_calls=0,
            redacted_value=dict(receipt.evidence.redacted_value),
            receipt_plain=receipt.to_plain(),
            forbidden_sentinel=SENTINEL,
        )
        assert dict(first) == dict(second)
        assert store.count_receipts("c6_3") == 1


def test_same_id_divergent_columns_exact_conflict(worker_database: Engine) -> None:
    receipt = _redaction_receipt()
    receipt_id = content_digest(receipt.to_plain())
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        store.persist_receipt(
            cell="c6_3",
            receipt_id=receipt_id,
            outcome_code="RedactionSucceeded",
            provider_calls=0,
            redacted_value=dict(receipt.evidence.redacted_value),
            receipt_plain=receipt.to_plain(),
            forbidden_sentinel=SENTINEL,
        )
        with pytest.raises(ReceiptExactConflict):
            store.persist_receipt(
                cell="c6_3",
                receipt_id=receipt_id,
                outcome_code="RedactionSucceeded",
                provider_calls=7,
                redacted_value=dict(receipt.evidence.redacted_value),
                receipt_plain=receipt.to_plain(),
                forbidden_sentinel=SENTINEL,
            )
        with pytest.raises(ReceiptExactConflict):
            store.persist_receipt(
                cell="c6_2",
                receipt_id=receipt_id,
                outcome_code="RedactionSucceeded",
                provider_calls=0,
                redacted_value=dict(receipt.evidence.redacted_value),
                receipt_plain=receipt.to_plain(),
                forbidden_sentinel=SENTINEL,
            )


def test_receipt_digest_mutation_and_mandatory_sentinel_fail_closed(
    worker_database: Engine,
) -> None:
    receipt = _redaction_receipt()
    mutated = receipt.to_plain()
    mutated["receipt_digest"] = "0" * 64
    with worker_database.begin() as connection:
        store = AgentCoreC6WorkerStore(connection, SCHEMA)
        with pytest.raises(ValueError, match="receipt_digest"):
            store.persist_receipt(
                cell="c6_3",
                receipt_id=content_digest(mutated),
                outcome_code="RedactionSucceeded",
                provider_calls=0,
                redacted_value=dict(receipt.evidence.redacted_value),
                receipt_plain=mutated,
                forbidden_sentinel=SENTINEL,
            )
        with pytest.raises(ValueError, match="forbidden_sentinel"):
            store.persist_receipt(
                cell="c6_3",
                receipt_id=content_digest(receipt.to_plain()),
                outcome_code="RedactionSucceeded",
                provider_calls=0,
                redacted_value=dict(receipt.evidence.redacted_value),
                receipt_plain=receipt.to_plain(),
                forbidden_sentinel="",
            )
