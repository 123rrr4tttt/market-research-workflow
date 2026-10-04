"""Persistence and dispatch for project-bound retrieval methods.

The project declaration is copied into a tenant row exactly once. A changed
packaged declaration requires an explicit refresh; old plans and runs retain
their original snapshot and version.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4
from typing import Any, NoReturn

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.base import SessionLocal
from app.models.project_retrieval import ProjectRetrievalMode, ProjectRetrievalPlan, ProjectRetrievalRun

from .failures import ProjectRetrievalFailureCode, retrieval_failure


class RetrievalError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _raise_retrieval_failure(
    code: ProjectRetrievalFailureCode,
    message: str,
    status: int,
    *,
    cause: BaseException | None = None,
) -> NoReturn:
    """Lift a typed project retrieval failure at the existing service API."""
    failure = retrieval_failure(code, message, site="service.public_api", status=status)
    # kit:boundary owner=project_retrieval.service.public_api class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=project_retrieval.failure witness=test:test_project_retrieval_service_lifts_typed_failures
    raise RetrievalError(failure.code, failure.message, status) from cause


def _canonical_digest(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _channel_readiness() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Inspect registered execution ports without invoking a search or URL fetch."""
    required = (
        "source.discovery.plan", "source.web.search", "source.candidate.review",
        "ingest.url_pool.submit", "project_retrieval.formalize_document",
    )
    try:
        from app.services.agent_sessions import get_agent_session_service
        from app.services.agent_core.project_tools import build_project_core_tool_registry

        registry = build_project_core_tool_registry(service=get_agent_session_service())
        channels = [{"capability": name, "registration": "registered" if registry.get(
                         f"skill.{name}" if name == "project_retrieval.formalize_document" else name) else "missing",
                     "connectivity": "not_probed"} for name in required]
    except Exception as exc:
        return [], [{"code": "CHANNEL_INSPECTION_FAILED", "severity": "blocking", "message": str(exc)}]
    diagnostics = [{"code": "CHANNEL_UNAVAILABLE", "severity": "blocking",
                    "message": item["capability"]} for item in channels if item["registration"] == "missing"]
    return channels, diagnostics


class ProjectRetrievalService:
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def _current(self, session, project_key: str) -> ProjectRetrievalMode:
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
            _raise_retrieval_failure("MODE_NOT_FOUND", str(exc), 404, cause=exc)
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
                # kit:boundary owner=project_retrieval.service.persistence_race class=SHELL_BOUNDARY_EXCEPTION failure_family=database.session_retry.failure witness=test:test_project_retrieval_current_preserves_unresolved_integrity_error
                raise
        return row

    def current(self, project_key: str) -> dict[str, Any]:
        from .mode import current_mode
        with self.session_factory() as session:
            return current_mode(self._current(session, project_key).snapshot)

    def domain_vocabulary(self, project_key: str) -> Any:
        """Resolve the current mode's authored vocabulary for topology writers."""

        from app.services.information_topology.io.retrieval import (
            resolve_domain_vocabulary,
        )

        with self.session_factory() as session:
            snapshot = deepcopy(self._current(session, project_key).snapshot)
        return resolve_domain_vocabulary(project_key, snapshot)

    def refresh(self, project_key: str) -> dict[str, Any]:
        """Explicitly adopt a newly packaged project observation.

        Existing plan rows keep their old snapshot. Replacing the bytes under
        an existing version is rejected rather than silently reinterpreted.
        """
        from .mode import current_mode, load_mode
        try:
            snapshot = load_mode(project_key)
        except (FileNotFoundError, ValueError) as exc:
            _raise_retrieval_failure("MODE_NOT_FOUND", str(exc), 404, cause=exc)
        with self.session_factory() as session:
            current = session.scalar(select(ProjectRetrievalMode).where(
                ProjectRetrievalMode.project_key == project_key,
                ProjectRetrievalMode.is_current.is_(True),
            ).with_for_update())
            if current is not None and current.version == snapshot["version"]:
                if current.snapshot != snapshot:
                    _raise_retrieval_failure("MODE_VERSION_CONFLICT", "changed method requires a new version", 409)
                return current_mode(current.snapshot)
            historical = session.scalar(select(ProjectRetrievalMode).where(
                ProjectRetrievalMode.project_key == project_key,
                ProjectRetrievalMode.mode_id == snapshot["mode_id"],
                ProjectRetrievalMode.version == snapshot["version"],
            ))
            if historical is not None and historical.snapshot != snapshot:
                _raise_retrieval_failure("MODE_VERSION_CONFLICT", "version identity already has different contents", 409)
            if current is not None:
                current.is_current = False
            if historical is None:
                historical = ProjectRetrievalMode(
                    project_key=project_key, mode_id=snapshot["mode_id"],
                    version=snapshot["version"], source_revision=snapshot["source_revision"],
                    snapshot=deepcopy(snapshot), is_current=True,
                )
                session.add(historical)
            else:
                historical.is_current = True
            session.commit()
            return current_mode(snapshot)

    def preview(self, project_key: str, *, route_id: str,
                query_ids: list[str] | None = None,
                limits: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from .mode import compile_preview
        with self.session_factory() as session:
            mode = self._current(session, project_key)
            try:
                plan = compile_preview(mode.snapshot, route_id=route_id,
                                       query_ids=query_ids, limits=limits)
            except ValueError as exc:
                _raise_retrieval_failure("INVALID_PLAN", str(exc), 422, cause=exc)
            plan = deepcopy(plan)
            plan["project_key"] = project_key
            plan["mode_id"] = mode.mode_id
            plan["mode_version"] = mode.version
            plan["source_revision"] = mode.source_revision
            plan["binding_snapshot"] = deepcopy(mode.snapshot)
            plan["channels"], channel_diagnostics = _channel_readiness()
            plan["diagnostics"] = list(plan.get("diagnostics") or []) + channel_diagnostics
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

    def start(self, project_key: str, *, plan_id: str, idempotency_key: str) -> dict[str, Any]:
        if not idempotency_key.strip() or len(idempotency_key) > 255:
            _raise_retrieval_failure(
                "INVALID_IDEMPOTENCY_KEY", "idempotency_key must be nonempty and at most 255 characters", 422,
            )
        with self.session_factory() as session:
            existing = session.scalar(select(ProjectRetrievalRun).where(
                ProjectRetrievalRun.project_key == project_key,
                ProjectRetrievalRun.idempotency_key == idempotency_key,
            ))
            if existing is not None:
                if existing.plan_id != plan_id:
                    _raise_retrieval_failure("IDEMPOTENCY_CONFLICT", "idempotency key already names another plan", 409)
                return {"run_id": existing.run_id, "status": existing.status}
            plan = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == plan_id,
            ))
            if plan is None:
                _raise_retrieval_failure("PLAN_NOT_FOUND", "preview plan does not exist", 404)
            if any(isinstance(item, Mapping) and item.get("severity") == "blocking"
                   for item in (plan.payload.get("diagnostics") or [])):
                _raise_retrieval_failure("PLAN_BLOCKED", "preview has unavailable execution channels", 409)
            run_id = f"pr_{uuid4().hex}"
            session.add(ProjectRetrievalRun(
                project_key=project_key, run_id=run_id, plan_id=plan_id,
                idempotency_key=idempotency_key, status="queued", phase="dispatch",
                counts={}, errors=[], receipt={},
            ))
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                existing = session.scalar(select(ProjectRetrievalRun).where(
                    ProjectRetrievalRun.project_key == project_key,
                    ProjectRetrievalRun.idempotency_key == idempotency_key,
                ))
                if existing is None or existing.plan_id != plan_id:
                    _raise_retrieval_failure(
                        "IDEMPOTENCY_CONFLICT", "idempotency key race or conflicting plan", 409,
                        cause=exc,
                    )
                return {"run_id": existing.run_id, "status": existing.status}
        try:
            from app.services.tasks import task_project_retrieval_run
            task_project_retrieval_run.apply_async(args=(project_key, run_id))
        except Exception as exc:  # queue failure is persisted, not reported as a running job
            self.update_run(project_key, run_id, status="dispatch_failed", phase="dispatch",
                            errors=[{"code": "DISPATCH_FAILED", "message": str(exc)}])
            _raise_retrieval_failure("DISPATCH_FAILED", "retrieval worker dispatch failed", 503, cause=exc)
        return {"run_id": run_id, "status": "queued"}

    def read_run(self, project_key: str, run_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.scalar(select(ProjectRetrievalRun).where(
                ProjectRetrievalRun.project_key == project_key,
                ProjectRetrievalRun.run_id == run_id,
            ))
            if row is None:
                _raise_retrieval_failure("RUN_NOT_FOUND", "retrieval run does not exist", 404)
            return {"run_id": row.run_id, "plan_id": row.plan_id, "status": row.status,
                    "phase": row.phase, "counts": row.counts, "errors": row.errors,
                    "receipt": row.receipt, "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None}

    def read_plan(self, project_key: str, plan_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            row = session.scalar(select(ProjectRetrievalPlan).where(
                ProjectRetrievalPlan.project_key == project_key,
                ProjectRetrievalPlan.plan_id == plan_id,
            ))
            if row is None:
                _raise_retrieval_failure("PLAN_NOT_FOUND", "preview plan does not exist", 404)
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
    ) -> dict[str, Any]:
        """Execute one persisted Rapid frontier against its frozen base plan.

        This is a compatibility entry to the fixed project retrieval executor.
        It does not claim that the missing original Rapid method or runner has
        been recovered.
        """

        identities = (plan_id, proposal_id, proposal_version, frontier_id)
        if any(not str(value or "").strip() for value in identities):
            _raise_retrieval_failure(
                "INVALID_PLAN", "plan and saved frontier identities are required", 422
            )
        if type(remaining_followup_budget) is not int or remaining_followup_budget <= 0:
            _raise_retrieval_failure(
                "INVALID_PLAN", "remaining_followup_budget must be a positive integer", 422
            )

        from functorial_kit import Failure

        from app.services.agent_sessions import get_agent_session_service

        from .proposals import RapidProposalTopologyAdapter
        from .rapid_macro import execute_saved_frontier
        from .topology import build_topology_service

        base_plan = self.read_plan(project_key, str(plan_id))
        # The worker normally adds a run-owned topology target before invoking
        # the executor.  Rapid continuation is a direct macro entrypoint, so
        # provide the same target here instead of treating the missing runtime
        # decoration as a topology capability failure.
        if not isinstance(base_plan.get("topology_ref"), Mapping):
            base_plan["topology_ref"] = {
                "project_key": project_key,
                "module_id": "retrieval",
                "namespace": "rapid",
                "state_id": f"retrieval-run:rapid-continuation:{proposal_id}:{frontier_id}",
            }
        topology_service = build_topology_service()
        result = execute_saved_frontier(
            adapter=RapidProposalTopologyAdapter(topology_service),
            project_key=project_key,
            proposal_id=str(proposal_id),
            proposal_version=str(proposal_version),
            frontier_id=str(frontier_id),
            base_plan=base_plan,
            remaining_followup_budget=remaining_followup_budget,
            topology_service=topology_service,
            session_factory=get_agent_session_service,
        )
        if isinstance(result, Failure):
            return {
                "status": "rejected",
                "error": {
                    "family": result.family,
                    "code": result.code,
                    "message": result.message,
                    "context": dict(result.context or {}),
                },
            }
        return {"status": "completed", **result}

    def claim_run(self, project_key: str, run_id: str) -> bool:
        """Only one worker may turn a queued run into an executing run."""
        with self.session_factory() as session:
            result = session.execute(update(ProjectRetrievalRun).where(
                ProjectRetrievalRun.project_key == project_key,
                ProjectRetrievalRun.run_id == run_id,
                ProjectRetrievalRun.status == "queued",
            ).values(status="running", phase="session"))
            session.commit()
            return result.rowcount == 1

    def update_run(self, project_key: str, run_id: str, *, status: str, phase: str,
                   counts: Mapping[str, Any] | None = None,
                   errors: list[Mapping[str, Any]] | None = None,
                   receipt: Mapping[str, Any] | None = None) -> None:
        values: dict[str, Any] = {"status": status, "phase": phase}
        if counts is not None:
            values["counts"] = dict(counts)
        if errors is not None:
            values["errors"] = [dict(error) for error in errors]
        if receipt is not None:
            values["receipt"] = dict(receipt)
        with self.session_factory() as session:
            session.execute(update(ProjectRetrievalRun).where(
                ProjectRetrievalRun.project_key == project_key,
                ProjectRetrievalRun.run_id == run_id,
            ).values(**values))
            session.commit()
