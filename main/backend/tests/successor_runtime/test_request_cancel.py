"""PostgreSQL tests for the run-level cancellation command."""

from __future__ import annotations

import secrets
from collections import deque
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.acquisition_url import URL_SINGLE_URL_KIND
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    build_retrieval_candidate_runtime_definition,
)
from app.successor_runtime.capabilities.retrieval_common import Candidate, CandidateBundle
from app.successor_runtime.capabilities.retrieval_material_native import (
    RETRIEVAL_CANDIDATE_REVIEW_KIND,
    RETRIEVAL_MATERIAL_FORMALIZE_KIND,
    RETRIEVAL_MATERIAL_READ_BODY_KIND,
    RETRIEVAL_MATERIAL_REVALIDATE_KIND,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.composition_root import (
    PostgresCancellationAuthorityGuard,
)
from app.successor_runtime.substrate.postgres.node_adapter import runtime_uow_factory
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RuntimeJournalRepository,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    RequestCancel,
    RuntimeLifecycleRepository,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES

from .c1_slice_postgres_fixture import (
    C1Database,
    NOW,
    PreparedC1Slice,
    make_node,
    prepare_runtime,
)
from .test_p0b_postgres_integration import (
    LiveDatabase,
    PROJECT_KEY,
    live_database as live_database,  # noqa: F401
    empty_successor_tables as empty_successor_tables,  # noqa: F401
)
from .test_traversal_persistent_activation import (
    _install_real_task_transport,
    _ready_work_ids,
    _run_real_task,
    _submit_retrieval_root,
)

pytest_plugins = ("tests.successor_runtime.c1_slice_postgres_fixture",)


def _tag() -> str:
    return secrets.token_hex(4)


def _prepare(
    c1_database: C1Database,
    run_suffix: str,
    *,
    project_prefix: str = "c1-cancel",
) -> PreparedC1Slice:
    project_key = f"{project_prefix}-{_tag()}"
    return prepare_runtime(
        c1_database,
        slice_id="B",
        project_key=project_key,
        tag=_tag(),
        run_suffix=run_suffix,
        node_profile_digest=content_digest(
            {"c1_test_node_profile": project_key}
        ),
        deployment_catalog_digest=content_digest(
            {"c1_test_deployment_catalog": project_key}
        ),
    )


@pytest.mark.integration
def test_request_cancel_readies_run_to_cancelled(c1_database: C1Database) -> None:
    prepared = _prepare(c1_database, "cancel")
    with c1_database.engine.begin() as connection:
        journal = RuntimeJournalRepository(connection, prepared.scope)
        run = journal.load_run(prepared.run_id)
        result = RuntimeLifecycleRepository(connection, prepared.scope).request_cancel(
            RequestCancel(
                run_id=prepared.run_id,
                expected_run_revision=int(run["revision"]),
                reason="test-cancel",
            )
        )
        run_after = journal.load_run(prepared.run_id)
        events = journal.load_events(prepared.run_id)
        step_states = tuple(
            connection.execute(
                sa.text(
                    "SELECT state FROM public.runtime_steps "
                    "WHERE project_key=:project_key AND run_id=:run_id ORDER BY step_id"
                ),
                {"project_key": prepared.project_key, "run_id": prepared.run_id},
            ).scalars()
        )

    assert result["state"] == "CANCELLED"
    assert result["cleanup_required"] is False
    assert result["cancelled_step_count"] == len(prepared.steps)
    assert run_after["cancellation_requested"] is True
    assert run_after["state"] == "CANCELLED"
    assert step_states == ("CANCELLED",) * len(prepared.steps)
    assert "CancellationRequested" in {row["event_type"] for row in events}


@pytest.mark.integration
def test_request_cancel_rejects_stale_revision(c1_database: C1Database) -> None:
    prepared = _prepare(c1_database, "stale")
    with c1_database.engine.begin() as connection:
        run = RuntimeJournalRepository(connection, prepared.scope).load_run(
            prepared.run_id
        )
        with pytest.raises(StaleRevisionError):
            RuntimeLifecycleRepository(connection, prepared.scope).request_cancel(
                RequestCancel(
                    run_id=prepared.run_id,
                    expected_run_revision=int(run["revision"]) + 1,
                )
            )


@pytest.mark.integration
def test_request_cancel_rejects_wrong_actor(c1_database: C1Database) -> None:
    prepared = _prepare(c1_database, "actor")
    rival_scope = replace(prepared.scope, actor_id="human:not-the-owner")
    with c1_database.engine.begin() as connection:
        run = RuntimeJournalRepository(connection, prepared.scope).load_run(
            prepared.run_id
        )
        with pytest.raises(ExactBindingConflict):
            RuntimeLifecycleRepository(connection, rival_scope).request_cancel(
                RequestCancel(
                    run_id=prepared.run_id,
                    expected_run_revision=int(run["revision"]),
                )
            )


@pytest.mark.integration
def test_request_cancel_rejects_revoked_grant(c1_database: C1Database) -> None:
    prepared = _prepare(c1_database, "revoke")
    with c1_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.runtime_authority_grants SET revoked_at=now() "
                "WHERE project_key=:project_key"
            ),
            {"project_key": prepared.project_key},
        )
    with c1_database.engine.begin() as connection:
        run = RuntimeJournalRepository(connection, prepared.scope).load_run(
            prepared.run_id
        )
        with pytest.raises(ExactBindingConflict):
            RuntimeLifecycleRepository(connection, prepared.scope).request_cancel(
                RequestCancel(
                    run_id=prepared.run_id,
                    expected_run_revision=int(run["revision"]),
                )
            )


@pytest.mark.integration
def test_request_cancel_rejects_terminal_run(c1_database: C1Database) -> None:
    prepared = _prepare(c1_database, "terminal")
    with c1_database.engine.begin() as connection:
        journal = RuntimeJournalRepository(connection, prepared.scope)
        run = journal.load_run(prepared.run_id)
        lifecycle = RuntimeLifecycleRepository(connection, prepared.scope)
        lifecycle.request_cancel(
            RequestCancel(
                run_id=prepared.run_id,
                expected_run_revision=int(run["revision"]),
            )
        )
        run_after = journal.load_run(prepared.run_id)
        with pytest.raises(ExactBindingConflict):
            lifecycle.request_cancel(
                RequestCancel(
                    run_id=prepared.run_id,
                    expected_run_revision=int(run_after["revision"]),
                )
            )


class _CancelTriggeringGuard:
    def __init__(
        self,
        *,
        engine: object,
        prepared: PreparedC1Slice,
        trigger_on_call: int,
    ) -> None:
        self._engine = engine
        self._prepared = prepared
        self._trigger_on_call = trigger_on_call
        self._production = PostgresCancellationAuthorityGuard(
            runtime_uow_factory(engine)
        )
        self._calls = 0
        self._triggered = False

    def _maybe_trigger(self) -> None:
        self._calls += 1
        if self._calls == self._trigger_on_call and not self._triggered:
            self._triggered = True
            with self._engine.begin() as connection:  # type: ignore[union-attr]
                journal = RuntimeJournalRepository(
                    connection, self._prepared.scope
                )
                run = journal.load_run(self._prepared.run_id, for_update=True)
                RuntimeLifecycleRepository(
                    connection, self._prepared.scope
                ).request_cancel(
                    RequestCancel(
                        run_id=self._prepared.run_id,
                        expected_run_revision=int(run["revision"]),
                        reason="test-guard-cancel",
                    ),
                    observed_at=NOW,
                )

    def require_not_cancelled(self, *, claim: object, observed_at: object) -> None:
        self._maybe_trigger()
        self._production.require_not_cancelled(
            claim=claim, observed_at=observed_at
        )

    def require_current_authority(
        self,
        *,
        claim: object,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: object,
    ) -> None:
        self._production.require_current_authority(
            claim=claim,
            expected_authority_digest=expected_authority_digest,
            expected_authority_epoch=expected_authority_epoch,
            observed_at=observed_at,
        )


@pytest.mark.integration
@pytest.mark.parametrize("guard_call", [1, 2])
def test_two_guard_cancellation_attempt_consistency(
    c1_database: C1Database, guard_call: int
) -> None:
    prepared = _prepare(
        c1_database,
        f"guard-{guard_call}",
        project_prefix=f"c1-guard-{guard_call}",
    )
    node = make_node(
        prepared,
        f"c1-slice-node-guard-{guard_call}",
        cancellation=_CancelTriggeringGuard(
            engine=c1_database.engine,
            prepared=prepared,
            trigger_on_call=guard_call,
        ),
    )

    report = node.run_once()
    results = report.results
    assert results and results[0].committed
    assert results[0].disposition is EffectDisposition.NOT_STARTED
    assert prepared.handler.executions == []

    with c1_database.engine.begin() as connection:
        attempt = connection.execute(
            sa.text(
                "SELECT disposition, finished_at FROM public.runtime_effect_attempts "
                "WHERE project_key=:project_key AND run_id=:run_id ORDER BY attempt_id"
            ),
            {"project_key": prepared.project_key, "run_id": prepared.run_id},
        ).mappings().first()
        step_states = tuple(
            connection.scalars(
                sa.text(
                    "SELECT state FROM public.runtime_steps "
                    "WHERE project_key=:project_key AND run_id=:run_id ORDER BY step_id"
                ),
                {"project_key": prepared.project_key, "run_id": prepared.run_id},
            )
        )
        reservation_states = tuple(
            connection.scalars(
                sa.text(
                    "SELECT state FROM public.runtime_resource_reservations "
                    "WHERE project_key=:project_key AND run_id=:run_id ORDER BY reservation_id"
                ),
                {"project_key": prepared.project_key, "run_id": prepared.run_id},
            )
        )

    assert attempt["disposition"] == "NOT_STARTED"
    assert attempt["finished_at"] is not None
    assert all(state == "CANCELLED" for state in step_states)
    assert all(state == "RELEASED" for state in reservation_states)

    with c1_database.engine.begin() as connection:
        events = RuntimeJournalRepository(
            connection, prepared.scope
        ).load_events(prepared.run_id)
    event_types = {row["event_type"] for row in events}
    assert "CleanupOrReadbackConfirmed" in event_types
    assert "RequiredCleanupAndReadbackSettled" in event_types


def _materialize_one_retrieval_child(
    live_database: LiveDatabase,
    queued: deque[str],
    *,
    parent_run_id: str,
    expected_child_count: int = 1,
) -> tuple[str, list[str]]:
    with live_database.engine.connect() as connection:
        queued.extend(_ready_work_ids(connection, run_id=parent_run_id))
    executed: list[str] = []
    while queued:
        work_id = queued.popleft()
        if work_id in executed:
            continue
        executed.append(work_id)
        report = _run_real_task(work_id)
        assert isinstance(report["claimed"], int)
        with live_database.engine.connect() as connection:
            events = PUBLIC_TABLES["runtime_events"]
            child_ids = tuple(
                str(metadata["child_run_id"])
                for metadata in connection.execute(
                    sa.select(events.c.event_metadata_json).where(
                        events.c.run_id == parent_run_id,
                        events.c.event_type == "ActiveChildMaterialized",
                    )
                ).scalars()
            )
        if child_ids:
            assert len(child_ids) == expected_child_count
            return child_ids[0], executed
    raise AssertionError("retrieval parent did not materialize one active child")


@pytest.mark.integration
def test_request_cancel_keeps_parent_cancelling_with_in_flight_active_child(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.ingest import url_pool
    from app.services.project_retrieval import execution as retrieval_execution
    from app.services.search import candidate_search

    tag = _tag()
    parent_run_id = f"retrieval-cancel-active-child-{tag}"
    candidate_url = f"https://example.invalid/cancel-{tag}"
    candidate_topics: list[str] = []
    acquired_urls: list[str] = []
    cancellation_results: list[dict[str, object]] = []

    def discover(request: Any) -> CandidateBundle:
        candidate_topics.append(request.topic)
        return CandidateBundle(
            request=request,
            candidates=(
                Candidate(
                    resource_uri=candidate_url,
                    title="Cancellation witness",
                    snippet="active child",
                    source="controlled-provider",
                    keyword="cancellation",
                    original_rank=1,
                    result_rank=1,
                    relevance_score=1.0,
                ),
            ),
            occurrences=(),
            observations=(),
            stop_reason="candidates_observed",
        )

    def cancel_during_acquire(request: Any) -> None:
        acquired_urls.append(request.url)
        with live_database.engine.begin() as connection:
            journal = RuntimeJournalRepository(connection, live_database.runtime_scope)
            parent = journal.load_run(parent_run_id, for_update=True)
            result = RuntimeLifecycleRepository(
                connection, live_database.runtime_scope
            ).request_cancel(
                RequestCancel(
                    run_id=parent_run_id,
                    expected_run_revision=int(parent["revision"]),
                    reason="active-child-in-flight-witness",
                )
            )
            cancellation_results.append(dict(result))
        raise ConnectionError("URL acknowledgement intentionally unavailable")

    monkeypatch.setattr(candidate_search, "discover_candidates", discover)
    monkeypatch.setattr(url_pool, "invoke_url_single_url", cancel_during_acquire)
    monkeypatch.setattr(
        retrieval_execution,
        "build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    queued = _install_real_task_transport(monkeypatch, live_database)
    with live_database.engine.begin() as connection:
        root = _submit_retrieval_root(
            connection,
            live_database,
            tag=tag,
            run_id=parent_run_id,
            query_count=1,
            install_authority=True,
            now=datetime.now(UTC),
        )
    child_run_id, executed = _materialize_one_retrieval_child(
        live_database,
        queued,
        parent_run_id=root.run_id,
    )
    with live_database.engine.connect() as connection:
        queued.extend(_ready_work_ids(connection, run_id=child_run_id))
    while queued and not cancellation_results:
        work_id = queued.popleft()
        if work_id in executed:
            continue
        executed.append(work_id)
        _run_real_task(work_id)

    assert len(cancellation_results) == 1
    cancellation = cancellation_results[0]
    assert cancellation["run_id"] == parent_run_id
    assert cancellation["state"] == "CANCELLING"
    assert cancellation["cleanup_required"] is True
    assert candidate_topics == [f"water policy {tag} 1"]
    assert acquired_urls == [candidate_url]

    candidate_kind = (
        build_retrieval_candidate_runtime_definition().operation_contract.ref.kind
    )
    with live_database.engine.connect() as connection:
        runs = PUBLIC_TABLES["runtime_runs"]
        run_states = dict(
            connection.execute(
                sa.select(runs.c.run_id, runs.c.state).where(
                    runs.c.run_id.in_((parent_run_id, child_run_id))
                )
            ).all()
        )
        steps = PUBLIC_TABLES["runtime_steps"]
        step_rows = connection.execute(
            sa.select(
                steps.c.run_id,
                steps.c.step_id,
                steps.c.operation_kind,
                steps.c.state,
                steps.c.attempt_count,
            ).where(steps.c.run_id.in_((parent_run_id, child_run_id)))
        ).mappings().all()
        root_search = next(
            row for row in step_rows if row["operation_kind"] == candidate_kind
        )
        child_steps = {
            str(row["operation_kind"]): row
            for row in step_rows
            if row["run_id"] == child_run_id
        }
        attempts = PUBLIC_TABLES["runtime_effect_attempts"]
        url_attempt = connection.execute(
            sa.select(attempts.c.disposition, attempts.c.receipt_ref).where(
                attempts.c.run_id == child_run_id,
                attempts.c.step_id == child_steps[URL_SINGLE_URL_KIND]["step_id"],
            )
        ).mappings().one()
        events = PUBLIC_TABLES["runtime_events"]
        settled_count = connection.scalar(
            sa.select(sa.func.count()).select_from(events).where(
                events.c.run_id == parent_run_id,
                events.c.event_type == "ActiveChildrenSettled",
            )
        )

    assert run_states == {
        parent_run_id: "CANCELLING",
        child_run_id: "CANCELLING",
    }
    assert root_search["state"] == "SUCCEEDED"
    assert root_search["attempt_count"] == 1
    assert child_steps[RETRIEVAL_CANDIDATE_REVIEW_KIND]["state"] == "SUCCEEDED"
    assert child_steps[RETRIEVAL_CANDIDATE_REVIEW_KIND]["attempt_count"] == 1
    assert child_steps[URL_SINGLE_URL_KIND]["state"] == "CANCEL_REQUESTED"
    assert child_steps[URL_SINGLE_URL_KIND]["attempt_count"] == 1
    for kind in (
        RETRIEVAL_MATERIAL_READ_BODY_KIND,
        RETRIEVAL_MATERIAL_FORMALIZE_KIND,
        RETRIEVAL_MATERIAL_REVALIDATE_KIND,
    ):
        assert child_steps[kind]["state"] == "CANCELLED"
        assert child_steps[kind]["attempt_count"] == 0
    assert url_attempt["disposition"] in {"IN_FLIGHT", "OUTCOME_UNKNOWN"}
    assert url_attempt["receipt_ref"] is None
    assert settled_count == 0


@pytest.mark.integration
def test_revoked_current_grant_blocks_child_without_replaying_completed_prefix(
    live_database: LiveDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.ingest import url_pool
    from app.services.project_retrieval import execution as retrieval_execution
    from app.services.search import candidate_search

    tag = _tag()
    parent_run_id = f"retrieval-revoked-child-{tag}"
    candidate_url = f"https://example.invalid/revoked-{tag}"
    candidate_topics: list[str] = []
    acquired_urls: list[str] = []

    def discover(request: Any) -> CandidateBundle:
        candidate_topics.append(request.topic)
        return CandidateBundle(
            request=request,
            candidates=(
                Candidate(
                    resource_uri=candidate_url,
                    title="Revoked grant witness",
                    snippet="completed prefix",
                    source="controlled-provider",
                    keyword="revocation",
                    original_rank=1,
                    result_rank=1,
                    relevance_score=1.0,
                ),
            ),
            occurrences=(),
            observations=(),
            stop_reason="candidates_observed",
        )

    def unexpected_acquire(request: Any) -> None:
        acquired_urls.append(request.url)

    monkeypatch.setattr(candidate_search, "discover_candidates", discover)
    monkeypatch.setattr(url_pool, "invoke_url_single_url", unexpected_acquire)
    monkeypatch.setattr(
        retrieval_execution,
        "build_source_candidate_plan",
        lambda **_: {"candidate_urls": [{"status": "accepted"}]},
    )
    queued = _install_real_task_transport(monkeypatch, live_database)
    with live_database.engine.begin() as connection:
        root = _submit_retrieval_root(
            connection,
            live_database,
            tag=tag,
            run_id=parent_run_id,
            query_count=1,
            install_authority=True,
            now=datetime.now(UTC),
        )
    child_run_id, executed = _materialize_one_retrieval_child(
        live_database,
        queued,
        parent_run_id=root.run_id,
    )
    with live_database.engine.begin() as connection:
        child_work_ids = _ready_work_ids(connection, run_id=child_run_id)
        assert child_work_ids
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_authority_grants"])
            .where(
                PUBLIC_TABLES["runtime_authority_grants"].c.project_key
                == PROJECT_KEY
            )
            .values(revoked_at=datetime.now(UTC))
        )

    blocked = _run_real_task(child_work_ids[0])
    replay = _run_real_task(executed[0])
    assert blocked["claimed"] == 1
    assert blocked["results"] == [{
        "work_item_id": child_work_ids[0], "state": "REJECTED",
        "disposition": "NOT_STARTED", "executed": False, "committed": False,
        "failure_code": "AUTHORITY_GRANT_INVALID",
    }]
    assert replay["claimed"] == 0
    assert replay["results"] == []
    assert candidate_topics == [f"water policy {tag} 1"]
    assert acquired_urls == []

    candidate_kind = (
        build_retrieval_candidate_runtime_definition().operation_contract.ref.kind
    )
    with live_database.engine.connect() as connection:
        steps = PUBLIC_TABLES["runtime_steps"]
        rows = connection.execute(
            sa.select(
                steps.c.run_id,
                steps.c.operation_kind,
                steps.c.state,
                steps.c.attempt_count,
            ).where(steps.c.run_id.in_((parent_run_id, child_run_id)))
        ).mappings().all()
        prefix = next(row for row in rows if row["operation_kind"] == candidate_kind)
        review = next(
            row
            for row in rows
            if row["run_id"] == child_run_id
            and row["operation_kind"] == RETRIEVAL_CANDIDATE_REVIEW_KIND
        )
        attempts = PUBLIC_TABLES["runtime_effect_attempts"]
        child_attempts = connection.execute(
            sa.select(attempts).where(attempts.c.run_id == child_run_id)
        ).mappings().all()
        work_items = PUBLIC_TABLES["runtime_work_items"]
        claimed = connection.execute(sa.select(work_items).where(
            work_items.c.work_item_id == child_work_ids[0]
        )).mappings().one()
        recovery = connection.execute(sa.select(work_items).where(
            work_items.c.work_item_id == f"reconcile:{claimed['claim_attempt_id']}"
        )).mappings().one()
        events = PUBLIC_TABLES["runtime_events"]
        # Allocating a claim does not spend the EffectStarted-based child budget.
        child_started = connection.scalar(sa.select(sa.func.count()).select_from(events).where(
            events.c.run_id == child_run_id, events.c.event_type == "EffectStarted"
        ))

    assert prefix["state"] == "SUCCEEDED" and prefix["attempt_count"] == 1
    assert review["state"] == "CLAIMED" and review["attempt_count"] == 1
    assert claimed["state"] == "CLAIMED" and claimed["attempt_count"] == 1
    assert len(child_attempts) == 1
    attempt = child_attempts[0]
    assert attempt["attempt_id"] == claimed["claim_attempt_id"]
    assert attempt["disposition"] == "NOT_STARTED"
    assert all(attempt[key] is None for key in (
        "receipt_ref", "receipt_digest", "started_at", "finished_at", "failure_ref", "failure_digest"
    ))
    assert child_started == 0
    assert claimed["lease_token"] and claimed["lease_owner"] and claimed["lease_expires_at"]
    assert recovery["state"] == "PENDING" and recovery["assignment_kind"] == "RECONCILE"
    assert recovery["attempt_count"] == 0 and recovery["due_at"] == claimed["lease_expires_at"]
    assert recovery["reconciliation_attempt_id"] == attempt["attempt_id"]
    assert recovery["assignment_binding_json"]["reconciliation_attempt_id"] == attempt["attempt_id"]
    assert recovery["handler_binding_digest"] == claimed["recovery_handler_binding_digest"]


def _two_active_children(live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch):
    from app.services.search import candidate_search
    tag = _tag()
    def discover(request: Any) -> CandidateBundle:
        return CandidateBundle(request=request, candidates=tuple(
            Candidate(resource_uri=f"https://example.invalid/{tag}/{index}", title=f"candidate {index}",
                      snippet="ordered child", source="controlled-provider", keyword="ordered",
                      original_rank=index + 1, result_rank=index + 1, relevance_score=1.0)
            for index in range(2)), occurrences=(), observations=(), stop_reason="candidates_observed")
    monkeypatch.setattr(candidate_search, "discover_candidates", discover)
    queued = _install_real_task_transport(monkeypatch, live_database)
    with live_database.engine.begin() as connection:
        root = _submit_retrieval_root(connection, live_database, tag=tag, run_id=f"ordered-child-{tag}",
                                      query_count=1, install_authority=True, now=datetime.now(UTC))
    _materialize_one_retrieval_child(live_database, queued, parent_run_id=root.run_id, expected_child_count=2)
    with live_database.engine.connect() as connection:
        events = PUBLIC_TABLES["runtime_events"]
        children = tuple(row["child_run_id"] for row in connection.execute(sa.select(events.c.event_metadata_json).where(
            events.c.project_key == PROJECT_KEY, events.c.run_id == root.run_id,
            events.c.event_type == "ActiveChildMaterialized",
        ).order_by(events.c.seq)).scalars())
        work = tuple(_ready_work_ids(connection, run_id=child)[0] for child in children)
    return root.run_id, children, work


@pytest.mark.integration
def test_ordered_active_children_two_workers_wait_for_completed_prefix(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services.project_retrieval import execution as retrieval_execution
    entered, release = Event(), Event()
    assessed: list[str] = []
    def assessment(**request: Any) -> dict[str, object]:
        assessed.extend(request["urls"])
        if len(assessed) == 1:
            entered.set()
            assert release.wait(20), "first worker was never released"
        return {"rejected_urls": [{"status": "rejected", "blocked_reason": "controlled rejection"}]}
    monkeypatch.setattr(retrieval_execution, "build_source_candidate_plan", assessment)
    parent, children, work = _two_active_children(live_database, monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(_run_real_task, work[0])
        try:
            assert entered.wait(20), "first worker did not enter its actual review effect"
            second = workers.submit(_run_real_task, work[1]).result(timeout=20)
            assert second["claimed"] == 0 and second["results"] == []
            assert len(assessed) == 1
            with live_database.engine.connect() as connection:
                runs = PUBLIC_TABLES["runtime_runs"]
                state = connection.scalar(sa.select(runs.c.state).where(runs.c.run_id == children[0]))
                assert state != "COMPLETED"
        finally:
            release.set()
        assert first.result(timeout=20)["claimed"] == 1
    with live_database.engine.connect() as connection:
        runs = PUBLIC_TABLES["runtime_runs"]
        assert connection.scalar(sa.select(runs.c.state).where(runs.c.run_id == children[0])) == "COMPLETED"
    assert _run_real_task(work[1])["claimed"] == 1
    assert len(assessed) == 2
    with live_database.engine.connect() as connection:
        assert connection.scalar(sa.select(runs.c.state).where(runs.c.run_id == children[1])) == "COMPLETED"
        assert connection.scalar(sa.select(runs.c.state).where(runs.c.run_id == parent)) in {"READY", "RUNNING", "WAITING", "COMPLETED"}


@pytest.mark.integration
@pytest.mark.parametrize("outcome", ["FAILED", "UNKNOWN"])
def test_ordered_active_child_failure_or_unknown_never_releases_suffix(
    live_database: LiveDatabase, monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    from app.services.project_retrieval import execution as retrieval_execution
    from app.services.ingest import url_pool
    from app.successor_runtime.runtime.node import DefiniteInterpreterFailure
    from app.successor_runtime.runtime.replay import ReplayEvent, replay_runtime_events
    assessed: list[str] = []
    acquired: list[str] = []
    def assessment(**request: Any) -> dict[str, object]:
        assessed.extend(request["urls"])
        return {"candidate_urls": [{"status": "accepted"}]}
    def acquire(request: Any) -> None:
        acquired.append(request.url)
        if outcome == "FAILED":
            raise DefiniteInterpreterFailure("URL_POOL_EXECUTION_FAILED")
        raise ConnectionError("controlled missing acknowledgement")
    monkeypatch.setattr(retrieval_execution, "build_source_candidate_plan", assessment)
    monkeypatch.setattr(url_pool, "invoke_url_single_url", acquire)
    parent, children, work = _two_active_children(live_database, monkeypatch)
    assert _run_real_task(work[0])["claimed"] == 1
    with live_database.engine.connect() as connection:
        acquisition = _ready_work_ids(connection, run_id=children[0])
    assert len(acquisition) == 1
    assert _run_real_task(acquisition[0])["claimed"] == 1
    assert _run_real_task(work[1])["claimed"] == 0
    assert len(assessed) == len(acquired) == 1
    with live_database.engine.connect() as connection:
        runs, steps, events = (PUBLIC_TABLES[name] for name in ("runtime_runs", "runtime_steps", "runtime_events"))
        parent_row = connection.execute(sa.select(runs).where(runs.c.run_id == parent)).mappings().one()
        child_rows = dict(connection.execute(sa.select(runs.c.run_id, runs.c.state).where(runs.c.run_id.in_(children))).tuples().all())
        suffix_attempts = connection.scalar(sa.select(sa.func.sum(steps.c.attempt_count)).where(steps.c.run_id == children[1]))
        rows = connection.execute(sa.select(events).where(events.c.run_id == parent).order_by(events.c.seq)).mappings().all()
    assert suffix_attempts == 0
    if outcome == "FAILED":
        assert parent_row["state"] == "FAILED"
        assert child_rows == {children[0]: "FAILED", children[1]: "CANCELLED"}
        causal = rows[-1]
        assert causal["schema_version"] == "mrw.runtime.event.required_step_failed.active_child.v2"
        assert causal["step_id"] is None and causal["attempt_id"] is None
        replay = replay_runtime_events(tuple(ReplayEvent.from_content(
            project_key=PROJECT_KEY, run_id=parent, run_incarnation=parent_row["incarnation"],
            seq=row["seq"], event_type=row["event_type"], schema_version=row["schema_version"],
            step_id=row["step_id"], attempt_id=row["attempt_id"], metadata=row["event_metadata_json"],
            payload_ref=row["payload_ref"], payload_digest=row["payload_digest"], authority_digest=row["authority_digest"],
        ) for row in rows))
        assert replay.run_state.value == "FAILED"
    else:
        assert parent_row["state"] == "WAITING"
        assert child_rows[children[0]] not in {"FAILED", "COMPLETED", "CANCELLED"}
        assert all(row["event_type"] != "RequiredStepFailed" for row in rows)
