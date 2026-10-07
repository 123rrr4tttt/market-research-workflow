"""Persistence and dispatch for project-bound retrieval methods.

The project declaration is copied into a tenant row exactly once. A changed
packaged declaration requires an explicit refresh; old plans and runs retain
their original snapshot and version.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any, Callable, NoReturn, cast

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.base import SessionLocal
from app.models.project_retrieval import ProjectRetrievalMode, ProjectRetrievalPlan
from app.services.information_topology.modules.retrieval import DomainVocabulary
from app.successor_runtime.capabilities.retrieval_candidate_native import (
    RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
    RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER,
)
from functorial_kit import Failure

from .contracts import RetrievalJsonObject, RetrievalJsonValue
from .failures import ProjectRetrievalFailureCode, retrieval_failure


class RetrievalError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def raise_retrieval_failure(
    code: ProjectRetrievalFailureCode,
    message: str,
    status: int,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift a typed project retrieval failure at the existing service API."""
    failure = retrieval_failure(code, message, site="service.public_api", status=status)
    # kit:boundary owner=retrieval.service class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_project_retrieval_service_rejects_invalid_idempotency_before_io
    raise RetrievalError(failure.code, failure.message, status) from cause


def _canonical_digest(value: Mapping[str, RetrievalJsonValue]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _channel_readiness() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Inspect registered execution ports without invoking a search or URL fetch."""
    required = (
        "source.discovery.plan", "source.web.search", "source.candidate.review",
        "ingest.url_pool.submit", "project_retrieval.formalize_material",
    )
    try:
        from app.services.agent_sessions import get_agent_session_service
        from app.services.agent_core.project_tools import build_project_core_tool_registry

        registry = build_project_core_tool_registry(service=get_agent_session_service())
        channels = [{"capability": name, "registration": "registered" if registry.get(
                         f"skill.{name}" if name == "project_retrieval.formalize_material" else name) else "missing",
                     "connectivity": "not_probed"} for name in required]
    except Exception as exc:
        return [], [{"code": "CHANNEL_INSPECTION_FAILED", "severity": "blocking", "message": str(exc)}]
    diagnostics = [{"code": "CHANNEL_UNAVAILABLE", "severity": "blocking",
                    "message": item["capability"]} for item in channels if item["registration"] == "missing"]
    return channels, diagnostics


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [cast(Mapping[str, Any], item) for item in cast(list[object], value) if isinstance(item, Mapping)]


def _read_historical_run(
    session_factory: Callable[[], Session],
    project_key: str,
    run_id: str,
) -> RetrievalJsonObject | None:
    """Read the retired run row when an existing deployment still retains it."""

    with session_factory() as session:
        connection = session.connection()
        if not inspect(connection).has_table("project_retrieval_runs"):
            return None
        row = connection.execute(
            text(
                "SELECT run_id, plan_id, status, phase, counts, errors, receipt, created_at, updated_at "
                "FROM project_retrieval_runs WHERE project_key = :project_key AND run_id = :run_id"
            ),
            {"project_key": project_key, "run_id": run_id},
        ).mappings().first()
        if row is None:
            return None
        row_values = cast(Mapping[str, object], row)
        raw_counts = row_values.get("counts")
        counts = (
            dict(cast(Mapping[str, RetrievalJsonValue], raw_counts))
            if isinstance(raw_counts, Mapping)
            else {}
        )
        raw_errors = row_values.get("errors")
        errors = (
            list(cast(list[RetrievalJsonValue], raw_errors))
            if isinstance(raw_errors, list)
            else []
        )
        raw_receipt = row_values.get("receipt")
        receipt = (
            dict(cast(Mapping[str, RetrievalJsonValue], raw_receipt))
            if isinstance(raw_receipt, Mapping)
            else {}
        )
        return cast(
            RetrievalJsonObject,
            {
                "run_id": str(row_values["run_id"]),
                "plan_id": str(row_values["plan_id"]),
                "status": str(row_values["status"]),
                "phase": str(row_values["phase"]),
                "counts": counts,
                "errors": errors,
                "receipt": receipt,
                "created_at": str(row_values.get("created_at") or ""),
                "updated_at": str(row_values.get("updated_at") or ""),
                "historical_runtime": "project_retrieval.session_executor.v1",
                "read_only": True,
            },
        )


class ProjectRetrievalService:
    def __init__(self, session_factory: Callable[[], Session] = SessionLocal):
        self.session_factory = session_factory

    def _current(self, session: Session, project_key: str) -> ProjectRetrievalMode:
        row = session.scalar(select(ProjectRetrievalMode).where(
            ProjectRetrievalMode.project_key == project_key,
            ProjectRetrievalMode.is_current.is_(True),
        ))
        if row is not None:
            return row
        from .mode import load_mode
        try:
            snapshot = load_mode(project_key)
        except (FileNotFoundError, ValueError) as exc:
            raise_retrieval_failure("MODE_NOT_FOUND", str(exc), 404, cause=exc)
        row = ProjectRetrievalMode(
            project_key=project_key,
            mode_id=str(snapshot["mode_id"]),
            version=str(snapshot["version"]),
            source_revision=str(snapshot["source_revision"]),
            snapshot=deepcopy(snapshot),
            is_current=True,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            row = session.scalar(select(ProjectRetrievalMode).where(
                ProjectRetrievalMode.project_key == project_key,
                ProjectRetrievalMode.is_current.is_(True),
            ))
            if row is None:
                # kit:boundary owner=retrieval.service class=SHELL_BOUNDARY_EXCEPTION failure_family=database.session_retry.failure witness=test:test_project_retrieval_current_preserves_unresolved_integrity_error
                raise
        return row

    def current(self, project_key: str) -> RetrievalJsonObject:
        from .mode import current_mode
        with self.session_factory() as session:
            return current_mode(self._current(session, project_key).snapshot)

    def domain_vocabulary(self, project_key: str) -> DomainVocabulary | Failure:
        """Resolve the current mode's authored vocabulary for topology writers."""

        from app.services.information_topology.io.retrieval import (
            resolve_domain_vocabulary,
        )

        with self.session_factory() as session:
            snapshot = deepcopy(self._current(session, project_key).snapshot)
        return resolve_domain_vocabulary(project_key, snapshot)

    def refresh(self, project_key: str) -> RetrievalJsonObject:
        """Explicitly adopt a newly packaged project observation.

        Existing plan rows keep their old snapshot. Replacing the bytes under
        an existing version is rejected rather than silently reinterpreted.
        """
        from .mode import current_mode, load_mode
        try:
            snapshot = load_mode(project_key)
        except (FileNotFoundError, ValueError) as exc:
            raise_retrieval_failure("MODE_NOT_FOUND", str(exc), 404, cause=exc)
        with self.session_factory() as session:
            current = session.scalar(select(ProjectRetrievalMode).where(
                ProjectRetrievalMode.project_key == project_key,
                ProjectRetrievalMode.is_current.is_(True),
            ).with_for_update())
            if current is not None and current.version == snapshot["version"]:
                if current.snapshot != snapshot:
                    raise_retrieval_failure("MODE_VERSION_CONFLICT", "changed method requires a new version", 409)
                return current_mode(current.snapshot)
            historical = session.scalar(select(ProjectRetrievalMode).where(
                ProjectRetrievalMode.project_key == project_key,
                ProjectRetrievalMode.mode_id == snapshot["mode_id"],
                ProjectRetrievalMode.version == snapshot["version"],
            ))
            if historical is not None and historical.snapshot != snapshot:
                raise_retrieval_failure("MODE_VERSION_CONFLICT", "version identity already has different contents", 409)
            if current is not None:
                current.is_current = False
            if historical is None:
                historical = ProjectRetrievalMode(
                    project_key=project_key, mode_id=str(snapshot["mode_id"]),
                    version=str(snapshot["version"]), source_revision=str(snapshot["source_revision"]),
                    snapshot=deepcopy(snapshot), is_current=True,
                )
                session.add(historical)
            else:
                historical.is_current = True
            session.commit()
            return current_mode(snapshot)

    def preview(self, project_key: str, *, route_id: str,
                query_ids: list[str] | None = None,
                limits: Mapping[str, int] | None = None) -> RetrievalJsonObject:
        from .mode import compile_preview
        with self.session_factory() as session:
            mode = self._current(session, project_key)
            try:
                plan = compile_preview(mode.snapshot, route_id=route_id,
                                       query_ids=query_ids, limits=limits)
            except ValueError as exc:
                raise_retrieval_failure("INVALID_PLAN", str(exc), 422, cause=exc)
            plan = deepcopy(plan)
            plan["project_key"] = project_key
            plan["mode_id"] = mode.mode_id
            plan["mode_version"] = mode.version
            plan["source_revision"] = mode.source_revision
            plan["binding_snapshot"] = deepcopy(mode.snapshot)
            channels, channel_diagnostics = _channel_readiness()
            plan["channels"] = cast(RetrievalJsonValue, channels)
            plan["diagnostics"] = cast(
                RetrievalJsonValue,
                _mapping_list(plan.get("diagnostics")) + channel_diagnostics,
            )
            # The plan identity must cover every executable input, including
            # the frozen project method; presentation diagnostics are excluded.
            identity = {key: value for key, value in plan.items() if key not in {"plan_id", "diagnostics"}}
            plan["plan_id"] = _canonical_digest(identity)
            existing = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == plan["plan_id"],
            ))
            if existing is None:
                session.add(ProjectRetrievalPlan(
                    project_key=project_key, plan_id=plan["plan_id"],
                    mode_id=mode.mode_id, mode_version=mode.version, payload=plan,
                ))
                try:
                    session.commit()
                except IntegrityError:
                    session.rollback()
            return {key: value for key, value in plan.items() if key != "binding_snapshot"}

    def start(
        self,
        project_key: str,
        *,
        plan_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> RetrievalJsonObject:
        if not idempotency_key.strip() or len(idempotency_key) > 255:
            raise_retrieval_failure(
                "INVALID_IDEMPOTENCY_KEY", "idempotency_key must be nonempty and at most 255 characters", 422,
            )
        if not actor_id.strip():
            raise_retrieval_failure("INVALID_PLAN", "trusted actor identity is required", 403)
        with self.session_factory() as session:
            plan = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == plan_id,
            ))
            if plan is None:
                raise_retrieval_failure("PLAN_NOT_FOUND", "preview plan does not exist", 404)
            if any(item.get("severity") == "blocking" for item in _mapping_list(plan.payload.get("diagnostics"))):
                raise_retrieval_failure("PLAN_BLOCKED", "preview has unavailable execution channels", 409)
            plan_payload = deepcopy(plan.payload)
        from app.composition.production import submit_installed_program
        from app.models.base import engine as runtime_engine
        from app.services.project_retrieval.execution import build_initial_retrieval_program
        from app.successor_runtime.substrate.postgres.runtime_journal import ExactBindingConflict
        from app.successor_runtime.substrate.postgres.authority_provider import (
            CurrentAuthorityGrantUnavailable,
        )
        from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

        run_id = "retrieval:" + sha256(
            json.dumps(
                {"project_key": project_key, "idempotency_key": idempotency_key},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        with runtime_engine.connect() as connection:
            project_scope = ServerProjectScopeResolver(connection=connection).resolve(project_key)
        target = plan_payload.get("topology_ref")
        topology_ref = dict(target) if isinstance(target, Mapping) else {}
        topology_ref.update(
            {
                "project_key": project_key,
                "module_id": str(topology_ref.get("module_id") or "retrieval"),
                "namespace": str(topology_ref.get("namespace") or "runs"),
                "state_id": f"retrieval-run:{run_id}",
            }
        )
        plan_payload["topology_ref"] = cast(RetrievalJsonValue, topology_ref)
        closure = build_initial_retrieval_program(
            project_key=project_key,
            root_run_id=run_id,
            plan=plan_payload,
            project_registry_revision=project_scope.project_registry_revision,
            project_scope_digest=project_scope.scope_digest,
            idempotency_key=idempotency_key,
        )
        try:
            run, work_item_ids = submit_installed_program(
                engine=runtime_engine,
                project_key=project_key,
                actor_id=actor_id,
                program=closure.program,
                operation_catalog=closure.catalog,
                operation_contracts=closure.registry,
                values=closure.values,
                idempotency_id=closure.idempotency_id,
                identity_capability_id=RETRIEVAL_CANDIDATE_DISCOVER_V3_OWNER,
                logical_request_id=idempotency_key,
                identity_operation_kind=RETRIEVAL_CANDIDATE_DISCOVER_V3_KIND,
                run_id=run_id,
                incarnation=closure.incarnation,
                canonical_bindings=closure.canonical_bindings,
                approvals_by_step=closure.approvals_by_step,
                trace_id=f"project-retrieval:{run_id}",
                now=datetime.now(UTC),
                queue="celery",
            )
        except CurrentAuthorityGrantUnavailable as exc:
            raise_retrieval_failure(
                "DISPATCH_FAILED", "retrieval Runtime authority is unavailable", 403, cause=exc
            )
        except ExactBindingConflict as exc:
            raise_retrieval_failure(
                "INVALID_IDEMPOTENCY_KEY", "idempotency key is bound to another retrieval request", 409, cause=exc
            )
        except Exception as exc:
            raise_retrieval_failure("DISPATCH_FAILED", "retrieval Runtime submission failed", 503, cause=exc)
        return {
            "run_id": str(run["run_id"]),
            "plan_id": plan_id,
            "status": str(run["state"]).lower(),
            "ready_work_item_ids": list(work_item_ids),
        }

    def read_run(self, project_key: str, run_id: str, *, actor_id: str) -> RetrievalJsonObject:
        if not actor_id.strip():
            raise_retrieval_failure("RUN_NOT_FOUND", "trusted actor identity is required", 403)
        from app.composition.production import read_installed_program
        from app.models.base import engine as runtime_engine
        from app.successor_runtime.capabilities.retrieval_material_native import (
            RetrievalControl,
        )
        from app.successor_runtime.runtime.ports import RuntimeScope
        from app.successor_runtime.substrate.postgres.models import project_tables
        from app.successor_runtime.substrate.postgres.programs import ProgramRepository
        from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver
        from app.services.project_retrieval.execution import (
            build_retrieval_runtime_journal_reader,
        )
        from sqlalchemy import MetaData

        try:
            run, steps, events = read_installed_program(
                engine=runtime_engine,
                project_key=project_key,
                actor_id=actor_id,
                run_id=run_id,
            )
        except Exception as exc:
            historical = _read_historical_run(self.session_factory, project_key, run_id)
            if historical is not None:
                return historical
            raise_retrieval_failure("RUN_NOT_FOUND", "retrieval Runtime run does not exist", 404, cause=exc)
        with runtime_engine.connect() as connection:
            project_scope = ServerProjectScopeResolver(connection=connection).resolve(project_key)
            scope = RuntimeScope(project_scope=project_scope, actor_id=actor_id)
            program = ProgramRepository(
                connection,
                project_tables(MetaData(), project_scope.resolved_schema),
            ).get(scope, str(run["program_id"]), expected_digest=str(run["program_digest"]))
        metadata = dict(program.metadata)
        if metadata.get("schema") != "mrw.project-retrieval.runtime.program.v1":
            raise_retrieval_failure("RUN_NOT_FOUND", "Runtime run is not a project retrieval root", 404)
        plan_id = str(metadata.get("plan_id") or "")
        plan = self.read_plan(project_key, plan_id)
        control = RetrievalControl(
            project_key=project_key,
            root_run_id=run_id,
            retrieval_budget_id=str(metadata.get("root_budget_id") or ""),
            plan_id=plan_id,
            mode_version=str(metadata.get("mode_version") or ""),
            route_id=str(metadata.get("route_id") or ""),
            round=0,
            plan_snapshot=cast(dict[str, Any], plan),
            budget={},
        )
        observation = build_retrieval_runtime_journal_reader(
            engine=runtime_engine,
            actor_id=actor_id,
        )(control)
        final_control = observation.get("final_control")
        attempts = cast(list[RetrievalJsonValue], observation.get("attempts") or [])
        candidates = cast(list[RetrievalJsonValue], observation.get("candidates") or [])
        materials = cast(list[RetrievalJsonValue], observation.get("materials") or [])
        gaps = cast(list[RetrievalJsonValue], observation.get("gaps") or [])
        failures = cast(list[RetrievalJsonValue], observation.get("failures") or [])
        return cast(
            RetrievalJsonObject,
            {
                "run_id": str(run["run_id"]),
                "plan_id": plan_id,
                "mode_id": plan.get("mode_id"),
                "mode_version": plan.get("mode_version"),
                "route_id": plan.get("route_id"),
                "status": str(run["state"]).lower(),
                "program_id": str(run["program_id"]),
                "plan_digest": str(run["plan_digest"]),
                "step_counts": {
                    state: sum(1 for step in steps if str(step.get("state")) == state)
                    for state in ("PENDING", "READY", "RUNNING", "WAITING", "SUCCEEDED", "FAILED", "CANCELLED")
                },
                "event_count": len(events),
                "attempts": attempts,
                "candidates": candidates,
                "materials": materials,
                "gaps": gaps,
                "failures": failures,
                "topology_write": (
                    cast(Mapping[str, RetrievalJsonValue], final_control).get("topology")
                    if isinstance(final_control, Mapping)
                    else None
                ),
                "result": final_control,
            },
        )

    def read_plan(self, project_key: str, plan_id: str) -> RetrievalJsonObject:
        with self.session_factory() as session:
            row = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == plan_id,
            ))
            if row is None:
                raise_retrieval_failure("PLAN_NOT_FOUND", "preview plan does not exist", 404)
            return deepcopy(row.payload)

    def continue_saved_frontier(
        self,
        project_key: str,
        *,
        plan_id: str,
        proposal_id: str,
        proposal_version: str,
        frontier_id: str,
        remaining_followup_budget: int,
        actor_id: str,
    ) -> RetrievalJsonObject:
        """Execute one persisted Rapid frontier against its frozen base plan.

        This is a compatibility entry to the fixed project retrieval executor.
        It does not claim that the missing original Rapid method or runner has
        been recovered.
        """

        identities = (plan_id, proposal_id, proposal_version, frontier_id)
        if any(not str(value or "").strip() for value in identities):
            raise_retrieval_failure(
                "INVALID_PLAN", "plan and saved frontier identities are required", 422
            )
        if type(remaining_followup_budget) is not int or remaining_followup_budget <= 0:
            raise_retrieval_failure(
                "INVALID_PLAN", "remaining_followup_budget must be a positive integer", 422
            )

        from .proposals import RapidProposalTopologyAdapter
        from .rapid_macro import continuation_plan_from_saved_frontier
        from .topology import build_topology_service

        base_plan = self.read_plan(project_key, str(plan_id))
        topology_service = build_topology_service()
        derived = continuation_plan_from_saved_frontier(
            adapter=RapidProposalTopologyAdapter(topology_service),
            project_key=project_key,
            proposal_id=str(proposal_id),
            proposal_version=str(proposal_version),
            frontier_id=str(frontier_id),
            base_plan=base_plan,
            remaining_followup_budget=remaining_followup_budget,
        )
        if isinstance(derived, Failure):
            return cast(RetrievalJsonObject, {
                "status": "rejected",
                "error": {
                    "family": derived.family,
                    "code": derived.code,
                    "message": derived.message,
                    "context": dict(derived.context or {}),
                },
            })
        derived_plan_id = str(derived.get("plan_id") or "")
        with self.session_factory() as session:
            existing = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == derived_plan_id,
            ))
            if existing is None:
                session.add(ProjectRetrievalPlan(
                    project_key=project_key,
                    plan_id=derived_plan_id,
                    mode_id=str(derived.get("mode_id") or base_plan.get("mode_id") or ""),
                    mode_version=str(derived.get("mode_version") or base_plan.get("mode_version") or ""),
                    payload=deepcopy(derived),
                ))
                session.commit()
        dispatch = self.start(
            project_key,
            plan_id=derived_plan_id,
            idempotency_key=f"rapid:{proposal_id}:{proposal_version}:{frontier_id}",
            actor_id=actor_id,
        )
        return cast(
            RetrievalJsonObject,
            {"status": dispatch["status"], "plan": derived, "dispatch": dispatch,
             "continuation": derived["rapid_continuation"]},
        )
