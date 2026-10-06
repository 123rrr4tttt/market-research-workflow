from __future__ import annotations

from importlib import import_module
from contextlib import nullcontext
from datetime import datetime, timezone
import hashlib
import json
from math import ceil
from typing import TYPE_CHECKING, Mapping, Protocol, TypeGuard, TypedDict

from functorial_kit import Failure

from ..celery_app import celery_app
from ..models.base import SessionLocal
from ..models.entities import EtlJobRun
from .job_logger import complete_job, fail_job, start_job
from .projects import bind_project

if TYPE_CHECKING:
    from app.contracts.json import JSONObject as AgentSessionJsonObject, JSONValue as AgentSessionJsonValue
    from .agent_sessions.store import (
        AgentArtifactPayload,
    )
    from .collect_runtime.contracts import CollectJsonObject, CollectJsonValue
    from .crawlers.base import CrawlerJsonObject, CrawlerJsonValue
    from .indexer.application import IndexingApplicationService
    from .ingest.social_application import SocialIngestApplicationService
    from .project_retrieval.contracts import RetrievalJsonArray, RetrievalJsonObject, RetrievalJsonValue, RetrievalRunResult


TaskObject = dict[str, object]
TaskResult = Mapping[str, object]


class TaskRequest(Protocol):
    @property
    def id(self) -> object: ...


class BoundTask(Protocol):
    @property
    def request(self) -> TaskRequest: ...

    def update_state(self, *, state: str, meta: Mapping[str, object]) -> object: ...


class CrawlerBridgeCall(Protocol):
    def __call__(self, **payload: object) -> object: ...


class DiscoveryWriteResult(TypedDict):
    upserted: int
    skipped: int
    errors: list[object]


class DiscoveryTotals(TypedDict):
    domains_scanned: int
    candidates_count: int
    probe_stats: dict[str, int]
    errors: list[object]
    write_result: DiscoveryWriteResult
    batches_total: int
    batches_completed: int
    pre_simplify: object | None


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _task_object(value: object) -> TaskObject:
    return {str(key): item for key, item in value.items()} if _is_object_mapping(value) else {}


def _task_object_list(value: object) -> list[TaskObject]:
    if not _is_object_list(value):
        return []
    return [_task_object(item) for item in value if _is_object_mapping(item)]


def _agent_session_json_value(value: object) -> AgentSessionJsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_object_list(value):
        return [_agent_session_json_value(item) for item in value]
    if _is_object_mapping(value):
        return {
            str(key): _agent_session_json_value(item)
            for key, item in value.items()
        }
    return str(value)


def _agent_session_json_object(value: object) -> AgentSessionJsonObject:
    if not _is_object_mapping(value):
        return {}
    return {
        str(key): _agent_session_json_value(item)
        for key, item in value.items()
    }


def _crawler_json_value(value: object) -> CrawlerJsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_object_list(value):
        return [_crawler_json_value(item) for item in value]
    if _is_object_mapping(value):
        return {
            str(key): _crawler_json_value(item)
            for key, item in value.items()
        }
    return str(value)


def _crawler_json_object(value: object) -> CrawlerJsonObject:
    if not _is_object_mapping(value):
        return {}
    return {
        str(key): _crawler_json_value(item)
        for key, item in value.items()
    }


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _collect_json_value(value: object) -> CollectJsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_object_list(value):
        return [_collect_json_value(item) for item in value]
    if _is_object_mapping(value):
        return {str(key): _collect_json_value(item) for key, item in value.items()}
    return str(value)


def _collect_json_object(value: object) -> CollectJsonObject:
    if not _is_object_mapping(value):
        return {}
    return {str(key): _collect_json_value(item) for key, item in value.items()}


def _retrieval_array(value: RetrievalJsonValue | None) -> RetrievalJsonArray:
    return value if isinstance(value, list) else []


def _retrieval_object(value: RetrievalJsonValue | None) -> RetrievalJsonObject:
    return value if isinstance(value, dict) else {}


def _retrieval_object_array(value: RetrievalJsonValue | None) -> list[Mapping[str, RetrievalJsonValue]]:
    return [item for item in _retrieval_array(value) if isinstance(item, dict)]


def _retrieval_json_value(value: object) -> RetrievalJsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if _is_object_list(value):
        return [_retrieval_json_value(item) for item in value]
    if _is_object_mapping(value):
        return {str(key): _retrieval_json_value(item) for key, item in value.items()}
    raise TypeError(f"retrieval result contains a non-JSON value: {type(value).__name__}")


def _retrieval_run_result_object(value: RetrievalRunResult) -> RetrievalJsonObject:
    normalized = _retrieval_json_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("retrieval result must be a JSON object")
    return normalized


@celery_app.task(name="project_retrieval.execute")
def task_project_retrieval_run(project_key: str, run_id: str) -> RetrievalJsonObject:
    """Interpret one manually authorized, version-pinned retrieval plan."""
    from .agent_sessions import get_agent_session_service
    from .project_retrieval.execution import execute_retrieval_run
    from .project_retrieval.service import ProjectRetrievalService
    from .project_retrieval.topology import build_topology_service

    with bind_project(project_key):
        service = ProjectRetrievalService()
        run = service.read_run(project_key, run_id)
        if run["status"] != "queued" or not service.claim_run(project_key, run_id):
            # Duplicate deliveries must not start a second Agent session or
            # compete for the run-owned topology identity.
            return service.read_run(project_key, run_id)
        plan: RetrievalJsonObject = service.read_plan(project_key, str(run["plan_id"]))
        plan["run_id"] = run_id
        plan["topology_ref"] = {
            "project_key": project_key, "module_id": "retrieval",
            "namespace": "rapid", "state_id": f"retrieval-run:{run_id}",
        }

        def emit(kind: str, payload: RetrievalJsonObject) -> None:
            phase = "search" if kind == "tool.result" else "session" if kind == "run.started" else "readback"
            service.update_run(project_key, run_id, status="running", phase=phase,
                               receipt={"latest_event": kind, "latest_event_payload": dict(payload)})

        try:
            result = _retrieval_run_result_object(execute_retrieval_run(
                project_key=project_key, plan=plan,
                topology_service=build_topology_service(),
                session_factory=get_agent_session_service, emit=emit,
            ))
        except Exception as exc:  # persist failures rather than leave an endless running row
            failure: RetrievalJsonObject = {
                "phase": "worker",
                "kind": type(exc).__name__,
                "message": str(exc),
            }
            failures: RetrievalJsonArray = [failure]
            result = {"status": "failed", "failures": failures}
        status = str(result.get("status") or "failed")
        if status not in {"completed", "partial", "blocked", "failed"}:
            status = "failed"
        report = _retrieval_object(result.get("report"))
        counts: RetrievalJsonObject = {
            "attempts": len(_retrieval_array(result.get("attempts"))),
            "candidates": len(_retrieval_array(result.get("candidates"))),
            "materials": len(_retrieval_array(result.get("materials"))),
            "formal_graphs": len(_retrieval_array(report.get("formal_graph_refs"))),
        }
        visible_errors: list[Mapping[str, RetrievalJsonValue]] = [
            *_retrieval_object_array(result.get("failures")),
            *_retrieval_object_array(result.get("gaps")),
        ]
        service.update_run(project_key, run_id, status=status, phase="finished", counts=counts,
                           errors=visible_errors, receipt=result)
        return {"run_id": run_id, "status": status, "counts": counts}
from .task_readback_metadata import (
    extract_runtime_readback_payload,
    merge_request_runtime_context,
    merge_runtime_readback_payload,
)

_social_ingest_app: SocialIngestApplicationService | None = None
_indexing_app: IndexingApplicationService | None = None


def _get_social_ingest_app() -> SocialIngestApplicationService:
    global _social_ingest_app
    if _social_ingest_app is None:
        from .ingest.social_application import SocialIngestApplicationService

        _social_ingest_app = SocialIngestApplicationService()
    return _social_ingest_app


def _get_indexing_app() -> IndexingApplicationService:
    global _indexing_app
    if _indexing_app is None:
        from .indexer.application import IndexingApplicationService

        _indexing_app = IndexingApplicationService()
    return _indexing_app


def _normalize_crawler_response(payload: object) -> TaskObject:
    source = _task_object(payload)
    if not source and hasattr(payload, "__dict__"):
        source = {str(key): value for key, value in vars(payload).items() if not str(key).startswith("_")}
    return source or {"raw": payload}


def _map_provider_status(status: str | None, default: str = "running") -> str:
    value = str(status or "").strip().lower()
    if value in {"queued", "accepted", "running", "started", "processing", "retry"}:
        return "running"
    if value in {"completed", "finished", "success", "successful", "done"}:
        return "completed"
    if value in {"failed", "failure", "error", "cancelled", "canceled"}:
        return "failed"
    return default


def _map_control_status(status: str | None, default: str = "running") -> str:
    value = str(status or "").strip().lower()
    if value in {"ok", "completed", "finished", "done", "success", "successful"}:
        return "completed"
    if value in {"queued", "accepted", "running", "started", "processing", "retry"}:
        return "running"
    if value in {"failed", "failure", "error", "cancelled", "canceled"}:
        return "failed"
    return default


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_hash(value: object) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        encoded = str(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _build_task_runtime_readback(
    *,
    line_key: str,
    task_request: TaskRequest | None,
    source_payload: TaskResult | None = None,
    workflow_run_id: str | None = None,
    trace_id: str | None = None,
    fallback_worker_name: str,
    fallback_queue: str,
) -> TaskObject:
    metadata = {
        **extract_runtime_readback_payload(source_payload or {}),
        "line_key": line_key,
    }
    if str(workflow_run_id or "").strip():
        metadata.setdefault("workflow_run_id", str(workflow_run_id).strip())
        metadata.setdefault("run_id", str(workflow_run_id).strip())
    if str(trace_id or "").strip():
        metadata.setdefault("trace_id", str(trace_id).strip())
    return merge_request_runtime_context(
        metadata,
        task_request,
        fallback_worker_name=fallback_worker_name,
        fallback_queue=fallback_queue,
        status="running",
        event="worker_started",
    )


def _attach_completed_runtime_readback(
    result: TaskResult,
    runtime_readback: TaskResult,
) -> TaskObject:
    payload = dict(result or {})
    payload["runtime_readback"] = merge_runtime_readback_payload(
        dict(runtime_readback or {}),
        runtime_readback,
        status="completed",
        event="completed",
        event_source="celery_worker",
    )
    return payload


def _start_resource_pool_job(
    *,
    job_type: str,
    task_request: TaskRequest | None,
    params: TaskResult,
) -> int:
    runtime_readback = _build_task_runtime_readback(
        line_key="resource_source_library",
        task_request=task_request,
        source_payload=params,
        fallback_worker_name="celery",
        fallback_queue="celery",
    )
    runtime_readback["project_key"] = str(params["project_key"])
    return start_job(
        job_type,
        {
            **params,
            "runtime_readback": runtime_readback,
        },
        external_job_id=str(getattr(task_request, "id", None) or "").strip() or None,
    )


def _finish_resource_pool_job(
    *,
    job_id: int,
    task_request: TaskRequest | None,
    result: TaskResult,
) -> None:
    complete_job(
        job_id,
        result=dict(result),
        external_job_id=str(getattr(task_request, "id", None) or "").strip() or None,
    )


def _fail_resource_pool_job(
    *,
    job_id: int,
    task_request: TaskRequest | None,
    error: Exception,
) -> None:
    fail_job(
        job_id,
        str(error),
        external_job_id=str(getattr(task_request, "id", None) or "").strip() or None,
    )


def _compact_agent_task_value(value: object, *, max_items: int = 20, max_depth: int = 4) -> object:
    if max_depth <= 0:
        return "..."
    if _is_object_mapping(value):
        out: TaskObject = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                out["..."] = f"{len(value) - max_items} more"
                break
            out[str(key)] = _compact_agent_task_value(item, max_items=max_items, max_depth=max_depth - 1)
        return out
    if _is_object_list(value):
        return [_compact_agent_task_value(item, max_items=max_items, max_depth=max_depth - 1) for item in value[:max_items]]
    if isinstance(value, str) and len(value) > 1200:
        return f"{value[:1200]}..."
    return value


def _agent_url_pool_marker(search_options: TaskObject | None) -> TaskObject:
    if search_options is None:
        return {}
    marker = search_options.get("_agent_core_url_pool_submission")
    return _task_object(marker)


def _agent_session_canceled(marker: TaskObject) -> bool:
    session_id = str(marker.get("session_id") or "").strip()
    if not session_id:
        return False
    try:
        from .agent_sessions.service import get_agent_session_service

        session = get_agent_session_service().get_session(session_id)
    except Exception:  # noqa: BLE001
        return False
    if isinstance(session, Failure):
        return False
    return str(session.get("status") or "").strip().lower() == "canceled"


def _record_agent_url_pool_task_event(
    marker: TaskObject,
    *,
    status: str,
    result: TaskResult | None = None,
    error: str | None = None,
) -> None:
    session_id = str(marker.get("session_id") or "").strip()
    if not session_id:
        return
    artifact_name = str(marker.get("artifact_name") or "ingest.url_pool_submissions.json").strip() or "ingest.url_pool_submissions.json"
    task_id = str(marker.get("task_id") or "").strip()
    url = str(marker.get("url") or "").strip()
    idempotency_key = str(marker.get("idempotency_key") or "").strip()
    event_payload: AgentSessionJsonObject = {
        "event_id": _stable_hash({"session_id": session_id, "task_id": task_id, "url": url, "status": status}),
        "contract_version": "ingest.url_pool.task_event.v1",
        "project_key": str(marker.get("project_key") or "").strip(),
        "url": url,
        "task_id": task_id,
        "status": status,
        "idempotency_key": idempotency_key,
        "candidate_review_key": str(marker.get("candidate_review_key") or "").strip(),
        "source_call_id": str(marker.get("source_call_id") or "").strip(),
        "recorded_at": _utcnow_iso(),
        "result": _agent_session_json_value(
            _compact_agent_task_value(result or {}, max_items=18, max_depth=4)
        ),
        "error": str(error or "").strip() or None,
    }
    try:
        from .agent_sessions.service import get_agent_session_service

        service = get_agent_session_service()
        artifacts = service.list_artifacts(session_id)
        if isinstance(artifacts, Failure):
            return
        existing_events_artifact = next(
            (item for item in artifacts if item.get("name") == "ingest.url_pool_task_events.json"),
            None,
        )
        events_content = _task_object((existing_events_artifact or {}).get("content_json"))
        events = _task_object_list(events_content.get("events"))
        events = [item for item in events if str(item.get("event_id") or "") != event_payload["event_id"]]
        events.append(_task_object(event_payload))
        task_events_content: AgentSessionJsonObject = {
            "contract_version": "ingest.url_pool.task_event.v1",
            "updated_at": event_payload["recorded_at"],
            "events": _agent_session_json_value(events[-100:]),
        }
        task_events_artifact: AgentArtifactPayload = {
            "session_id": session_id,
            "name": "ingest.url_pool_task_events.json",
            "artifact_type": "url_pool_ingest_task_event_state",
            "mime_type": "application/json",
            "content_text": json.dumps(
                task_events_content,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            "content_json": task_events_content,
            "metadata": {
                "contract_version": "ingest.url_pool.task_event.v1",
                "auto_written_by": "task_ingest_url_via_source_library",
            },
        }
        service.store.upsert_artifact(
            task_events_artifact
        )

        existing_submission_artifact = next((item for item in artifacts if item.get("name") == artifact_name), None)
        submission_content = _task_object((existing_submission_artifact or {}).get("content_json"))
        submissions = _task_object_list(submission_content.get("submissions"))
        for submission in submissions:
            same_key = idempotency_key and str(submission.get("idempotency_key") or "") == idempotency_key
            same_url = url and str(submission.get("url") or "").strip() == url
            if not same_key and not same_url:
                continue
            task_events = _task_object_list(submission.get("task_events"))
            task_events = [item for item in task_events if str(item.get("event_id") or "") != event_payload["event_id"]]
            task_events.append(event_payload)
            submission["task_events"] = task_events[-20:]
            submission["latest_task_status"] = status
            submission["latest_task_event_at"] = event_payload["recorded_at"]
            if status == "completed":
                submission["completed_at"] = event_payload["recorded_at"]
                submission["task_result"] = event_payload["result"]
            if status == "failed":
                submission["failed_at"] = event_payload["recorded_at"]
                submission["task_error"] = event_payload["error"]
        if submissions:
            updated_submission_content = _agent_session_json_object({
                **submission_content,
                "updated_at": event_payload["recorded_at"],
                "submissions": submissions[-100:],
            })
            submission_artifact: AgentArtifactPayload = {
                "session_id": session_id,
                "name": artifact_name,
                "artifact_type": "url_pool_ingest_submission_state",
                "mime_type": "application/json",
                "content_text": json.dumps(
                    updated_submission_content,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
                "content_json": updated_submission_content,
                "metadata": {
                    "contract_version": str(
                        updated_submission_content.get("contract_version")
                        or "ingest.url_pool.submit.v1"
                    ),
                    "auto_updated_by": "task_ingest_url_via_source_library",
                },
            }
            service.store.upsert_artifact(
                submission_artifact
            )
        service.store.append_event(
            session_id,
            event_type=f"ingest.url_pool.task.{status}",
            payload=event_payload,
        )
    except Exception:  # noqa: BLE001
        return


def _load_crawlers_bridge_api() -> tuple[CrawlerBridgeCall, CrawlerBridgeCall]:
    from . import crawlers

    _ = crawlers  # importing the package registers built-in providers
    try:
        module = import_module(".crawlers.bridge", package=__package__)
    except Exception:
        module = None

    submit_fn = getattr(module, "submit_crawler_job", None) if module else None
    poll_fn = getattr(module, "poll_crawler_job", None) if module else None
    if callable(submit_fn) and callable(poll_fn):
        return submit_fn, poll_fn

    from .crawlers.base import CrawlerDispatchRequest
    from .crawlers.registry import get_provider

    def _fallback_submit(**payload: object) -> TaskObject:
        provider_key = str(payload.get("provider") or payload.get("external_provider") or "").strip()
        provider = get_provider(provider_key)
        if not provider:
            raise ValueError(f"crawler provider is not registered: {provider_key}")
        request = CrawlerDispatchRequest(
            provider=provider_key,
            project=str(payload.get("project") or ""),
            spider=str(payload.get("spider") or ""),
            arguments=_crawler_json_object(payload.get("arguments")),
            settings=_crawler_json_object(payload.get("settings")),
            version=_optional_text(payload.get("version")),
            priority=_optional_int(payload.get("priority")),
            job_id=_optional_text(payload.get("external_job_id")),
        )
        result = provider.dispatch(request)
        if isinstance(result, Failure):
            raise RuntimeError(result.message)
        return {
            "provider_status": result.provider_status,
            "provider_job_id": result.provider_job_id,
            "provider_type": result.provider_type,
            "attempt_count": result.attempt_count,
            "raw": result.raw,
        }

    def _fallback_poll(**payload: object) -> TaskObject:
        provider_key = str(payload.get("external_provider") or payload.get("provider") or "").strip()
        provider = get_provider(provider_key)
        if not provider:
            raise ValueError(f"crawler provider is not registered: {provider_key}")
        poll_fn_local = getattr(provider, "poll", None)
        if not callable(poll_fn_local):
            raise ValueError(f"crawler provider does not support poll(): {provider_key}")
        external_job_id = _optional_text(payload.get("external_job_id"))
        if external_job_id is None:
            raise ValueError("external_job_id is required")
        result = poll_fn_local(
            external_job_id=external_job_id,
            project=_optional_text(payload.get("project")),
            spider=_optional_text(payload.get("spider")),
            options=_task_object(payload.get("options")),
        )
        if isinstance(result, Failure):
            raise RuntimeError(result.message)
        return _normalize_crawler_response(result)

    return _fallback_submit, _fallback_poll


def _load_db_job_tracking(job_id: int) -> TaskObject:
    with SessionLocal() as session:
        row = session.get(EtlJobRun, int(job_id))
        if not row:
            return {}
        tracking: TaskObject = {
            "external_provider": row.external_provider,
            "external_job_id": row.external_job_id,
            "retry_count": row.retry_count,
            "status": row.status,
            "params": _task_object(row.params),
        }
        return tracking


@celery_app.task
def task_select_prompt_time_windows(
    project_key: str | None = None,
    noun_group_ids: list[str] | None = None,
    prompt_group_ids: list[str] | None = None,
    source_domains: list[str] | None = None,
    candidate_windows: list[str] | None = None,
    top_k: int = 10,
    prefer_low_density: bool = True,
    exclude_high_dup: bool = True,
    min_overlap: float = 0.35,
    target_overlap: float = 0.55,
    eta: float = 0.08,
    delta_max: float = 0.12,
    tau: float = 0.03,
    avoid_peak: bool = True,
    end: str | None = None,
) -> TaskObject:
    from .stats import query_prompt_time_density_priority

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else datetime.now(timezone.utc).date()
        windows = candidate_windows or ["7d", "30d", "90d"]
        rows = query_prompt_time_density_priority(
            end=end_date,
            candidate_windows=windows,
            source_domains=source_domains,
            noun_group_ids=noun_group_ids,
            prompt_group_ids=prompt_group_ids,
            prefer_low_density=prefer_low_density,
            exclude_high_dup=exclude_high_dup,
            min_overlap=min_overlap,
            target_overlap=target_overlap,
            eta=eta,
            delta_max=delta_max,
            tau=tau,
            avoid_peak=avoid_peak,
            project_key=project_key,
        )
        selected = rows[: max(1, int(top_k or 10))]
        response: TaskObject = {
            "project_key": project_key,
            "end": end_date.isoformat(),
            "candidate_windows": windows,
            "selected": selected,
            "total": len(rows),
        }
        return response


@celery_app.task(bind=True)
def task_ingest_market(
    self: BoundTask,
    query_terms: list[str],
    max_items: int = 20,
    enable_extraction: bool = True,
    project_key: str | None = None,
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str | None = None,
    provider: str | None = None,
    workflow_run_id: str | None = None,
    trace_id: str | None = None,
    line_key: str | None = None,
    queue: str | None = None,
    runtime_readback: TaskObject | None = None,
) -> TaskObject:
    from .collect_runtime import collect_request_from_market_api, run_collect

    runtime_readback = _build_task_runtime_readback(
        line_key=line_key or "search_discovery_index",
        task_request=getattr(self, "request", None),
        source_payload={"runtime_readback": runtime_readback} if runtime_readback else None,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
        fallback_worker_name="local.task_ingest_market",
        fallback_queue=queue or "local.search_discovery_index",
    )
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        req = collect_request_from_market_api(
            query_terms=query_terms,
            max_items=max_items,
            project_key=project_key,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
            enable_extraction=enable_extraction,
        )
        if str(workflow_run_id or "").strip():
            req.source_context = {**(req.source_context or {}), "workflow_run_id": str(workflow_run_id)}
        if str(trace_id or "").strip():
            req.source_context = {**(req.source_context or {}), "trace_id": str(trace_id)}
        req.source_context = _collect_json_object({
            **(req.source_context or {}),
            "runtime_readback": runtime_readback,
        })
        cr = run_collect(req)
        raw = _collect_json_object((cr.meta or {}).get("raw"))
        if not raw:
            raw = {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped}
        return _attach_completed_runtime_readback(raw, runtime_readback)


@celery_app.task(bind=True)
def task_ingest_url_via_source_library(
    self: BoundTask,
    url: str,
    query_terms: list[str] | None = None,
    strict_mode: bool = False,
    project_key: str | None = None,
    search_options: TaskObject | None = None,
) -> TaskObject:
    from .ingest.url_pool import ingest_url_via_source_library_frontdoor

    marker = _agent_url_pool_marker(search_options)
    if _agent_session_canceled(marker):
        result: TaskObject = {
            "status": "canceled",
            "abort_requested": True,
            "url": url,
            "project_key": project_key,
            "reason": "agent_session_canceled_before_url_pool_ingest",
        }
        _record_agent_url_pool_task_event(marker, status="canceled", result=result)
        return result
    runtime_readback = _build_task_runtime_readback(
        line_key="ingest",
        task_request=getattr(self, "request", None),
        source_payload=search_options,
        fallback_worker_name="local.task_ingest_url_via_source_library",
        fallback_queue="local.ingest",
    )
    enriched_search_options = {
        **(search_options or {}),
        "runtime_readback": runtime_readback,
    }
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        job_id = start_job(
            "url_pool_fetch",
            {
                "mode": "single_url_async",
                "url": url,
                "project_key": project_key,
                "query_terms": list(query_terms or []),
                "runtime_readback": runtime_readback,
            },
        )
        try:
            result = ingest_url_via_source_library_frontdoor(
                url=url,
                project_key=project_key,
                query_terms=query_terms,
                strict_mode=strict_mode,
                search_options=enriched_search_options,
                frontdoor_options={"enabled": True},
                entrypoint="ingest.url.single.async",
                source_name="task_ingest_url_via_source_library",
                enable_extraction=True,
            )
        except Exception as exc:  # noqa: BLE001
            fail_job(job_id, str(exc))
            _record_agent_url_pool_task_event(marker, status="failed", error=str(exc))
            raise
        completed_result = _attach_completed_runtime_readback(result, runtime_readback)
        complete_job(job_id, result=completed_result)
        _record_agent_url_pool_task_event(marker, status="completed", result=completed_result)
        return completed_result



@celery_app.task
def task_index_policy(document_ids: list[int], project_key: str | None = None) -> TaskObject:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(_get_indexing_app().index_policy(document_ids=document_ids))


@celery_app.task
def task_collect_news_resource(
    resource_id: str,
    limit: int = 10,
    project_key: str | None = None,
) -> TaskObject:
    """Dispatch to news resource handler. Effective = shared (总库) + project (子项目库), project overrides."""
    from ..project_customization import get_project_customization

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        customization = get_project_customization(project_key)
        shared = customization.get_shared_news_resource_handlers()
        project_handlers = customization.get_news_resource_handlers()
        handlers = {**shared, **project_handlers}
        handler = handlers.get(resource_id)
        if not handler:
            raise ValueError(f"Project '{project_key}' does not support news resource '{resource_id}'")
        return _task_object(handler(limit))


@celery_app.task(bind=True)
def task_extract_resource_pool_from_documents(
    self: BoundTask,
    project_key: str,
    scope: str = "project",
    doc_type: list[str] | None = None,
    state: list[str] | None = None,
    document_ids: list[int] | None = None,
    limit: int = 500,
) -> TaskObject:
    """Extract URLs from documents into resource pool."""
    from .resource_pool import extract_from_documents

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        params: TaskObject = {
            "project_key": project_key,
            "scope": scope,
            "doc_type": doc_type,
            "state": state,
            "document_ids": document_ids,
            "limit": limit,
        }
        job_id = _start_resource_pool_job(
            job_type="resource_pool_extract",
            task_request=getattr(self, "request", None),
            params=params,
        )
        try:
            result = _task_object(extract_from_documents(
                project_key=project_key,
                scope=scope,
                doc_type=doc_type,
                state=state,
                document_ids=document_ids,
                limit=limit,
            ))
        except Exception as exc:
            _fail_resource_pool_job(
                job_id=job_id,
                task_request=getattr(self, "request", None),
                error=exc,
            )
            raise
        _finish_resource_pool_job(
            job_id=job_id,
            task_request=getattr(self, "request", None),
            result=result,
        )
        return result


@celery_app.task(bind=True)
def task_extract_resource_pool_from_tasks(
    self: BoundTask,
    project_key: str,
    scope: str = "project",
    task_ids: list[int] | None = None,
    job_type: str | None = None,
    since: str | None = None,
    limit: int = 100,
) -> TaskObject:
    """Extract URLs from EtlJobRun params into resource pool."""
    from .resource_pool import extract_from_tasks

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        params: TaskObject = {
            "project_key": project_key,
            "scope": scope,
            "task_ids": task_ids,
            "job_type": job_type,
            "since": since,
            "limit": limit,
        }
        job_id = _start_resource_pool_job(
            job_type="resource_pool_capture",
            task_request=getattr(self, "request", None),
            params=params,
        )
        try:
            result = _task_object(extract_from_tasks(
                project_key=project_key,
                scope=scope,
                task_ids=task_ids,
                job_type=job_type,
                since=since,
                limit=limit,
            ))
        except Exception as exc:
            _fail_resource_pool_job(
                job_id=job_id,
                task_request=getattr(self, "request", None),
                error=exc,
            )
            raise
        _finish_resource_pool_job(
            job_id=job_id,
            task_request=getattr(self, "request", None),
            result=result,
        )
        return result


@celery_app.task(bind=True)
def task_discover_site_entries_batched(
    self: BoundTask,
    project_key: str,
    url_scope: str = "effective",
    target_scope: str = "project",
    domain: str | None = None,
    limit_domains: int = 50,
    probe_timeout: float = 8.0,
    include_link_alternate: bool = True,
    sitemap_paths: list[str] | None = None,
    rss_paths: list[str] | None = None,
    allow_domains: list[str] | None = None,
    deny_domains: list[str] | None = None,
    run_auto_classify: bool = False,
    use_llm: bool = False,
    write: bool = True,
    batch_size: int = 20,
    simplify_pool_first: bool = True,
) -> TaskObject:
    from .resource_pool import (
        discover_site_entries_from_urls,
        list_discovery_domains,
        simplify_site_entries,
        write_discovered_site_entries,
    )

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        params: TaskObject = {
            "project_key": project_key,
            "url_scope": url_scope,
            "target_scope": target_scope,
            "domain": domain,
            "limit_domains": limit_domains,
            "probe_timeout": probe_timeout,
            "include_link_alternate": include_link_alternate,
            "sitemap_paths": sitemap_paths,
            "rss_paths": rss_paths,
            "allow_domains": allow_domains,
            "deny_domains": deny_domains,
            "run_auto_classify": run_auto_classify,
            "use_llm": use_llm,
            "write": write,
            "batch_size": batch_size,
            "simplify_pool_first": simplify_pool_first,
        }
        job_id = _start_resource_pool_job(
            job_type="resource_pool_discover",
            task_request=getattr(self, "request", None),
            params=params,
        )
        try:
            domains = list_discovery_domains(
                project_key=project_key,
                url_scope=url_scope,
                domain=domain,
                limit_domains=limit_domains,
                allow_domains=allow_domains,
                deny_domains=deny_domains,
            )
            batch_size = max(1, min(100, int(batch_size or 20)))
            totals: DiscoveryTotals = {
                "domains_scanned": 0,
                "candidates_count": 0,
                "probe_stats": {},
                "errors": [],
                "write_result": {"upserted": 0, "skipped": 0, "errors": []},
                "batches_total": ceil(len(domains) / batch_size) if domains else 0,
                "batches_completed": 0,
                "pre_simplify": None,
            }
            if simplify_pool_first and write and target_scope in {"project", "shared"}:
                try:
                    totals["pre_simplify"] = simplify_site_entries(
                        scope=target_scope,
                        project_key=project_key if target_scope == "project" else None,
                        dry_run=False,
                    )
                except Exception as exc:
                    totals["pre_simplify"] = {"error": str(exc)}
            self.update_state(
                state="STARTED",
                meta={
                    "phase": "prepared",
                    "batches_total": totals["batches_total"],
                    "batches_completed": totals["batches_completed"],
                    "pre_simplify": totals["pre_simplify"],
                },
            )
            for i in range(0, len(domains), batch_size):
                batch_domains = domains[i : i + batch_size]
                result = discover_site_entries_from_urls(
                    project_key=project_key,
                    url_scope=url_scope,
                    target_scope=target_scope,
                    domain=None,
                    limit_domains=max(len(batch_domains), 1),
                    probe_timeout=probe_timeout,
                    include_link_alternate=include_link_alternate,
                    sitemap_paths=sitemap_paths,
                    rss_paths=rss_paths,
                    allow_domains=batch_domains,
                    deny_domains=deny_domains,
                    run_auto_classify=run_auto_classify,
                    use_llm=use_llm,
                )
                totals["domains_scanned"] += int(result.domains_scanned or 0)
                totals["candidates_count"] += len(result.candidates or [])
                totals["errors"].extend(result.errors or [])
                for k, v in (result.probe_stats or {}).items():
                    totals["probe_stats"][k] = int(totals["probe_stats"].get(k, 0)) + int(v or 0)
                if write:
                    wr = write_discovered_site_entries(
                        project_key=project_key,
                        candidates=result.candidates,
                        target_scope=target_scope,
                        dry_run=False,
                    )
                    totals["write_result"]["upserted"] += int(wr.upserted or 0)
                    totals["write_result"]["skipped"] += int(wr.skipped or 0)
                    totals["write_result"]["errors"].extend(wr.errors or [])
                totals["batches_completed"] += 1
                self.update_state(
                    state="STARTED",
                    meta={
                        "phase": "discovering",
                        "batches_total": totals["batches_total"],
                        "batches_completed": totals["batches_completed"],
                        "domains_scanned": totals["domains_scanned"],
                        "candidates_count": totals["candidates_count"],
                        "probe_stats": totals["probe_stats"],
                        "write_result": totals["write_result"],
                        "pre_simplify": totals["pre_simplify"],
                    },
                )
        except Exception as exc:
            _fail_resource_pool_job(
                job_id=job_id,
                task_request=getattr(self, "request", None),
                error=exc,
            )
            raise
        _finish_resource_pool_job(
            job_id=job_id,
            task_request=getattr(self, "request", None),
            result=totals,
        )
        return dict(totals)


@celery_app.task
def task_collect_reddit(subreddit: str = "news", limit: int = 20, project_key: str | None = None) -> TaskObject:
    from .ingest.news import collect_reddit_discussions

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(collect_reddit_discussions(subreddit=subreddit, limit=limit))


@celery_app.task
def task_collect_weekly_reports(limit: int = 10, project_key: str | None = None) -> TaskObject:
    from .ingest.reports.general import collect_weekly_market_reports

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(collect_weekly_market_reports(limit=limit))


@celery_app.task
def task_collect_monthly_reports(limit: int = 8, project_key: str | None = None) -> TaskObject:
    from .ingest.reports.general import collect_monthly_financial_reports

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(collect_monthly_financial_reports(limit=limit))


@celery_app.task
def task_collect_data_api(
    keywords: list[str],
    platforms: list[str] | None = None,
    limit: int = 20,
    enable_extraction: bool = True,
    enable_subreddit_discovery: bool = True,
    base_subreddits: list[str] | None = None,
    project_key: str | None = None,
) -> TaskObject:
    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(_get_social_ingest_app().collect_data_api(
            keywords=keywords,
            platforms=platforms,
            limit=limit,
            enable_extraction=enable_extraction,
            enable_subreddit_discovery=enable_subreddit_discovery,
            base_subreddits=base_subreddits,
        ))


@celery_app.task
def task_collect_policy_regulation(
    keywords: list[str],
    limit: int = 20,
    enable_extraction: bool = True,
    project_key: str | None = None,
    start_offset: int | None = None,
    days_back: int | None = None,
    language: str | None = None,
    provider: str | None = None,
) -> TaskObject:
    from .collect_runtime import collect_request_from_policy_api, run_collect

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        req = collect_request_from_policy_api(
            query_terms=keywords,
            max_items=limit,
            project_key=project_key,
            start_offset=start_offset,
            days_back=days_back,
            language=language or "en",
            provider=provider or "auto",
            enable_extraction=enable_extraction,
        )
        cr = run_collect(req)
        raw = _collect_json_object((cr.meta or {}).get("raw"))
        if raw:
            return dict(raw)
        response: TaskObject = {"inserted": cr.inserted, "updated": cr.updated, "skipped": cr.skipped}
        return response


@celery_app.task
def task_ingest_commodity_metrics(limit: int = 30, project_key: str | None = None) -> TaskObject:
    from .ingest.commodity import ingest_commodity_metrics

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(ingest_commodity_metrics(limit=limit))


@celery_app.task
def task_collect_ecom_prices(limit: int = 100, project_key: str | None = None) -> TaskObject:
    from .ingest.ecom import collect_ecom_price_observations

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(collect_ecom_price_observations(limit=limit))


@celery_app.task
def task_sync_aggregator(
) -> TaskObject:
    # Aggregator reads from public + all project schemas.
    from .aggregator import sync_project_data_to_aggregator
    return _task_object(sync_project_data_to_aggregator())


@celery_app.task(bind=True)
def task_worker_observability_noop(
    self: BoundTask,
    request_id: str | None = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    project_key: str | None = None,
    candidate_id: str | None = None,
    queue: str | None = None,
    runtime_readback: TaskObject | None = None,
) -> TaskObject:
    """Execute one identity-preserving observation without effect sinks."""

    runtime_readback = _build_task_runtime_readback(
        line_key="worker_observability",
        task_request=getattr(self, "request", None),
        source_payload={"runtime_readback": runtime_readback} if runtime_readback else None,
        workflow_run_id=run_id or request_id,
        trace_id=trace_id,
        fallback_worker_name="local.task_worker_observability_noop",
        fallback_queue=queue or "celery",
    )
    response: TaskObject = {
        "contract_version": "production.observability.worker-noop.v1",
        "status": "completed",
        "effect_sinks": "none",
        "request_id": request_id,
        "run_id": run_id or request_id,
        "trace_id": trace_id,
        "project_key": project_key,
        "candidate_id": candidate_id,
        "effect_boundary": {
            "external_provider_calls": 0,
            "database_writes": 0,
            "filesystem_writes": 0,
            "queue_side_effects": 0,
        },
        "runtime_readback": merge_runtime_readback_payload(
            dict(runtime_readback or {}),
            {
                "request_id": request_id,
                "trace_id": trace_id,
                "project_key": project_key,
                "candidate_id": candidate_id,
            },
            status="completed",
            event="completed",
            event_source="celery_worker",
        ),
    }
    return response


@celery_app.task
def task_raw_import_documents(payload: TaskObject, project_key: str | None = None) -> TaskObject:
    from .ingest.raw_import import run_raw_import_documents

    ctx = bind_project(project_key) if project_key else nullcontext()
    with ctx:
        return _task_object(run_raw_import_documents(payload=payload or {}, project_key=project_key or ""))


@celery_app.task(bind=True)
def task_run_source_library_item(
    self: BoundTask,
    item_key: str,
    project_key: str | None = None,
    override_params: TaskObject | None = None,
    workflow_run_id: str | None = None,
    trace_id: str | None = None,
    line_key: str | None = None,
    queue: str | None = None,
    runtime_readback: TaskObject | None = None,
) -> TaskObject:
    from .collect_runtime import run_source_library_item_compat

    runtime_readback = _build_task_runtime_readback(
        line_key=line_key or "resource_source_library",
        task_request=getattr(self, "request", None),
        source_payload={"runtime_readback": runtime_readback} if runtime_readback else override_params,
        workflow_run_id=workflow_run_id,
        trace_id=trace_id,
        fallback_worker_name="local.task_run_source_library_item",
        fallback_queue=queue or "local.resource_source_library",
    )
    result = run_source_library_item_compat(
        item_key=item_key,
        project_key=project_key,
        override_params=_collect_json_object({
            **(override_params or {}),
            **({"workflow_run_id": str(workflow_run_id)} if str(workflow_run_id or "").strip() else {}),
            **({"trace_id": str(trace_id)} if str(trace_id or "").strip() else {}),
            "runtime_readback": runtime_readback,
        }),
    )
    return _attach_completed_runtime_readback(result, runtime_readback)


@celery_app.task
def task_submit_crawler_job(
    job_id: int,
    provider: str,
    project: str,
    spider: str,
    arguments: TaskObject | None = None,
    settings: TaskObject | None = None,
    version: str | None = None,
    priority: int | None = None,
) -> TaskObject:
    from .job_logger import fail_job, update_job_tracking

    submit_fn, _ = _load_crawlers_bridge_api()
    try:
        submitted = _normalize_crawler_response(
            submit_fn(
                provider=provider,
                project=project,
                spider=spider,
                arguments=arguments or {},
                settings=settings or {},
                version=version,
                priority=priority,
            )
        )
        external_job_id = str(
            submitted.get("external_job_id")
            or submitted.get("provider_job_id")
            or ""
        ).strip() or None
        external_provider = str(
            submitted.get("external_provider")
            or submitted.get("provider_type")
            or provider
            or ""
        ).strip() or None
        retry_count = submitted.get("retry_count")
        if retry_count is None:
            retry_count = submitted.get("attempt_count")
        update_job_tracking(
            int(job_id),
            external_job_id=external_job_id,
            external_provider=external_provider,
            retry_count=_optional_int(retry_count),
            status=_map_provider_status(_optional_text(submitted.get("provider_status")), default="running"),
            result={"crawler_submit": submitted},
        )
        return {
            "job_id": int(job_id),
            "external_provider": external_provider,
            "external_job_id": external_job_id,
            "status": _map_provider_status(_optional_text(submitted.get("provider_status")), default="running"),
            "raw": submitted,
        }
    except Exception as exc:
        fail_job(int(job_id), str(exc))
        raise


@celery_app.task
def task_poll_crawler_job(
    job_id: int,
    external_provider: str | None = None,
    external_job_id: str | None = None,
    project: str | None = None,
    spider: str | None = None,
    options: TaskObject | None = None,
) -> TaskObject:
    from .job_logger import fail_job, update_job_tracking

    _, poll_fn = _load_crawlers_bridge_api()
    tracked = _load_db_job_tracking(int(job_id))
    provider = external_provider or tracked.get("external_provider")
    provider_job_id = external_job_id or tracked.get("external_job_id")
    if not provider or not provider_job_id:
        raise ValueError(
            f"missing crawler tracking fields for job_id={job_id}: "
            f"external_provider={provider!r}, external_job_id={provider_job_id!r}"
        )

    try:
        polled = _normalize_crawler_response(
            poll_fn(
                external_provider=provider,
                external_job_id=provider_job_id,
                provider=provider,
                project=project,
                spider=spider,
                options=options or {},
            )
        )
        provider_status = polled.get("provider_status") or polled.get("status")
        retry_count = polled.get("retry_count")
        if retry_count is None:
            retry_count = polled.get("attempt_count")
        mapped_status = _map_provider_status(
            _optional_text(provider_status),
            default=str(tracked.get("status") or "running"),
        )
        update_job_tracking(
            int(job_id),
            external_job_id=str(polled.get("external_job_id") or provider_job_id),
            external_provider=str(polled.get("external_provider") or provider),
            retry_count=_optional_int(retry_count),
            status=mapped_status,
            result={"crawler_poll": polled},
            error=str(polled.get("error") or "") or None,
        )
        return {
            "job_id": int(job_id),
            "external_provider": str(polled.get("external_provider") or provider),
            "external_job_id": str(polled.get("external_job_id") or provider_job_id),
            "status": mapped_status,
            "raw": polled,
        }
    except Exception as exc:
        fail_job(int(job_id), str(exc), external_provider=str(provider), external_job_id=str(provider_job_id))
        raise


@celery_app.task
def task_crawler_deploy_version(
    project: str,
    version: str,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: TaskObject | None = None,
    job_id: int | None = None,
) -> TaskObject:
    return _execute_crawler_deploy_version(
        project=project,
        version=version,
        egg_file_path=egg_file_path,
        egg_content_b64=egg_content_b64,
        base_url=base_url,
        metadata=metadata,
        job_id=job_id,
    )


def _execute_crawler_deploy_version(
    *,
    project: str,
    version: str,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: TaskObject | None = None,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import deploy_scrapy_project_version
    from .job_logger import fail_job, update_job_tracking

    try:
        result = deploy_scrapy_project_version(
            project=project,
            version=version,
            egg_file_path=egg_file_path,
            egg_content_b64=egg_content_b64,
            base_url=base_url,
            metadata=metadata or {},
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status=_map_control_status(result.get("provider_status")),
                result={"crawler_deploy": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_register_source_library_scrapy_binding(
    project_key: str,
    channel_key: str,
    item_key: str,
    spider: str,
    scrapy_project: str,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: TaskObject | None = None,
    settings: TaskObject | None = None,
    item_params_patch: TaskObject | None = None,
    channel_extra_patch: TaskObject | None = None,
    item_extra_patch: TaskObject | None = None,
    enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    return _execute_register_source_library_scrapy_binding(
        project_key=project_key,
        channel_key=channel_key,
        item_key=item_key,
        spider=spider,
        scrapy_project=scrapy_project,
        channel_name=channel_name,
        item_name=item_name,
        description=description,
        arguments=arguments,
        settings=settings,
        item_params_patch=item_params_patch,
        channel_extra_patch=channel_extra_patch,
        item_extra_patch=item_extra_patch,
        enabled=enabled,
        job_id=job_id,
    )


def _execute_register_source_library_scrapy_binding(
    *,
    project_key: str,
    channel_key: str,
    item_key: str,
    spider: str,
    scrapy_project: str,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: TaskObject | None = None,
    settings: TaskObject | None = None,
    item_params_patch: TaskObject | None = None,
    channel_extra_patch: TaskObject | None = None,
    item_extra_patch: TaskObject | None = None,
    enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import register_or_update_source_library_scrapy_binding
    from .job_logger import fail_job, update_job_tracking

    try:
        result = register_or_update_source_library_scrapy_binding(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            spider=spider,
            scrapy_project=scrapy_project,
            channel_name=channel_name,
            item_name=item_name,
            description=description,
            arguments=arguments or {},
            settings=settings or {},
            item_params_patch=item_params_patch or {},
            channel_extra_patch=channel_extra_patch or {},
            item_extra_patch=item_extra_patch or {},
            enabled=enabled,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="running",
                result={"crawler_auto_register": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_orchestrate_crawler_deploy(
    project_key: str,
    scrapy_project: str,
    spider: str,
    channel_key: str,
    item_key: str,
    version: str,
    deploy_run_id: int | None = None,
    egg_file_path: str | None = None,
    egg_content_b64: str | None = None,
    base_url: str | None = None,
    metadata: TaskObject | None = None,
    channel_name: str | None = None,
    item_name: str | None = None,
    description: str | None = None,
    arguments: TaskObject | None = None,
    settings: TaskObject | None = None,
    item_params_patch: TaskObject | None = None,
    channel_extra_patch: TaskObject | None = None,
    item_extra_patch: TaskObject | None = None,
    enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import finalize_deploy_run
    from .job_logger import fail_job, update_job_tracking

    try:
        if egg_file_path or egg_content_b64:
            deploy_result = _execute_crawler_deploy_version(
                project=scrapy_project,
                version=version,
                egg_file_path=egg_file_path,
                egg_content_b64=egg_content_b64,
                base_url=base_url,
                metadata=metadata or {},
                job_id=job_id,
            )
        else:
            deploy_result = {
                "provider_type": "scrapy",
                "provider_status": "skipped_no_artifact",
                "project": scrapy_project,
                "version": version,
                "raw": {"reason": "egg artifact not provided; registration-only mode"},
            }
        register_result = _execute_register_source_library_scrapy_binding(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            spider=spider,
            scrapy_project=scrapy_project,
            channel_name=channel_name,
            item_name=item_name,
            description=description,
            arguments=arguments or {},
            settings=settings or {},
            item_params_patch=item_params_patch or {},
            channel_extra_patch=channel_extra_patch or {},
            item_extra_patch=item_extra_patch or {},
            enabled=enabled,
            job_id=job_id,
        )
        orchestrated: TaskObject = {
            "project_key": project_key,
            "channel_key": channel_key,
            "item_key": item_key,
            "provider_type": "scrapy",
            "deploy": deploy_result,
            "register": register_result,
        }
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="completed",
                result={"crawler_deploy_orchestration": orchestrated},
            )
        if deploy_run_id is not None:
            finalize_deploy_run(int(deploy_run_id), status="succeeded")
        return orchestrated
    except Exception as exc:
        if deploy_run_id is not None:
            finalize_deploy_run(int(deploy_run_id), status="failed", error=str(exc))
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_crawler_rollback_version(
    project: str,
    version: str,
    base_url: str | None = None,
    job_id: int | None = None,
) -> TaskObject:
    return _execute_crawler_rollback_version(
        project=project,
        version=version,
        base_url=base_url,
        job_id=job_id,
    )


def _execute_crawler_rollback_version(
    *,
    project: str,
    version: str,
    base_url: str | None = None,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import rollback_scrapy_project_version
    from .job_logger import fail_job, update_job_tracking

    try:
        result = rollback_scrapy_project_version(
            project=project,
            version=version,
            base_url=base_url,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status=_map_control_status(result.get("provider_status")),
                result={"crawler_rollback": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_disable_source_library_channel_provider_native(
    project_key: str,
    channel_key: str,
    item_key: str | None = None,
    keep_item_enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    return _execute_disable_source_library_channel_provider_native(
        project_key=project_key,
        channel_key=channel_key,
        item_key=item_key,
        keep_item_enabled=keep_item_enabled,
        job_id=job_id,
    )


def _execute_disable_source_library_channel_provider_native(
    *,
    project_key: str,
    channel_key: str,
    item_key: str | None = None,
    keep_item_enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import apply_source_library_native_rollback
    from .job_logger import fail_job, update_job_tracking

    try:
        result = apply_source_library_native_rollback(
            project_key=project_key,
            channel_key=channel_key,
            item_key=item_key,
            keep_item_enabled=keep_item_enabled,
        )
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="running",
                result={"crawler_provider_native_rollback": result},
            )
        return result
    except Exception as exc:
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise


@celery_app.task
def task_orchestrate_crawler_rollback(
    project_key: str,
    scrapy_project: str,
    channel_key: str,
    deploy_run_id: int | None = None,
    item_key: str | None = None,
    version: str | None = None,
    base_url: str | None = None,
    disable_provider_type_to_native: bool = True,
    keep_item_enabled: bool = True,
    job_id: int | None = None,
) -> TaskObject:
    from .crawlers_mgmt import finalize_deploy_run
    from .job_logger import fail_job, update_job_tracking

    try:
        rollback_result: TaskObject | None = None
        if version:
            rollback_result = _execute_crawler_rollback_version(
                project=scrapy_project,
                version=version,
                base_url=base_url,
                job_id=job_id,
            )

        native_result: TaskObject | None = None
        if disable_provider_type_to_native:
            native_result = _execute_disable_source_library_channel_provider_native(
                project_key=project_key,
                channel_key=channel_key,
                item_key=item_key,
                keep_item_enabled=keep_item_enabled,
                job_id=job_id,
            )

        orchestrated: TaskObject = {
            "project_key": project_key,
            "channel_key": channel_key,
            "item_key": item_key,
            "provider_type": "native" if disable_provider_type_to_native else "scrapy",
            "rollback": rollback_result,
            "provider_toggle": native_result,
        }
        if job_id is not None:
            update_job_tracking(
                int(job_id),
                status="completed",
                result={"crawler_rollback_orchestration": orchestrated},
            )
        if deploy_run_id is not None:
            finalize_deploy_run(int(deploy_run_id), status="succeeded")
        return orchestrated
    except Exception as exc:
        if deploy_run_id is not None:
            finalize_deploy_run(int(deploy_run_id), status="failed", error=str(exc))
        if job_id is not None:
            fail_job(int(job_id), str(exc), external_provider="scrapy")
        raise
