import hashlib
import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache, partial
from importlib import import_module
from threading import Lock
from typing import Literal, NoReturn, Protocol, TypeAlias, TypedDict, TypeGuard, runtime_checkable

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, JsonValue, TypeAdapter, ValidationError
from sqlalchemy.exc import DatabaseError, OperationalError, ProgrammingError, SQLAlchemyError

from ..contracts import (
    ApiEnvelope,
    ErrorCode,
    error_response,
    map_exception_to_error,
    success_response,
    task_result_response,
)
from ..contracts.responses import ok
from ..project_customization import get_project_customization
from ..services.agent_batch.routing import apply_async_or_delay, validate_lane
from ..services.agent_batch.task_contract import build_source_library_override_params
from ..services.collect_runtime.contracts import CollectJsonObject, source_library_compat_response
from ..services.ingest.commodity import CommodityIngestResult
from ..services.ingest.adapters import submission_registry as ingest_submission_registry
from ..services.ingest.reports.general import ReportIngestResult
from ..services.ingest.social_application import SocialCollectResult
from ..services.job_logger import list_jobs
from ..services.projects import bind_project, current_project_key
from ..services.skill_runtime import invoke_skill
from ..services.source_library.single_source_guard import (
    SourceLibrarySingleSourceGuardError,
    validate_single_source_guard,
)
from ..settings.config import get_effective_project_key_enforcement_mode, settings
from ..services.ingest.adapters.submission_registry import (
    MaterialIngestRegistryBackendUnavailableError,
    MaterialIngestRegistryConflictError,
)
from ._error_responses import error_json_response

logger = logging.getLogger(__name__)

IngestJsonObject: TypeAlias = dict[str, object]
IngestJsonValue: TypeAlias = object
_INGEST_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


@runtime_checkable
class _AsyncTaskResult(Protocol):
    id: str


@runtime_checkable
class _AsyncTask(Protocol):
    def delay(self, *args: object, **kwargs: object) -> object:
        ...

    def apply_async(
        self,
        *,
        args: tuple[object, ...],
        kwargs: dict[str, object],
        queue: str,
        routing_key: str,
    ) -> object:
        ...


@runtime_checkable
class _TasksModule(Protocol):
    task_ingest_market: _AsyncTask
    task_collect_news_resource: _AsyncTask
    task_collect_reddit: _AsyncTask
    task_collect_weekly_reports: _AsyncTask
    task_collect_monthly_reports: _AsyncTask
    task_collect_data_api: _AsyncTask
    task_collect_policy_regulation: _AsyncTask
    task_ingest_commodity_metrics: _AsyncTask
    task_collect_ecom_prices: _AsyncTask
    task_run_source_library_item: _AsyncTask


@runtime_checkable
class _IngestConfigService(Protocol):
    def get_config(self, project_key: str, config_key: str) -> IngestJsonObject | None:
        ...

    def upsert_config(
        self,
        *,
        project_key: str,
        config_key: str,
        config_type: str,
        payload: IngestJsonObject | None,
    ) -> IngestJsonObject:
        ...


@runtime_checkable
class _SocialIngestApplication(Protocol):
    def collect_data_api(
        self,
        *,
        keywords: list[str],
        platforms: list[str] | None,
        limit: int,
        enable_extraction: bool,
        enable_subreddit_discovery: bool,
        base_subreddits: list[str] | None,
    ) -> SocialCollectResult:
        ...


@runtime_checkable
class _ReportIngestModule(Protocol):
    def collect_weekly_market_reports(self, *, limit: int = 10) -> ReportIngestResult:
        ...

    def collect_monthly_financial_reports(self, *, limit: int = 8) -> ReportIngestResult:
        ...


@runtime_checkable
class _CommodityIngestModule(Protocol):
    def ingest_commodity_metrics(
        self,
        symbols: dict[str, str] | None = None,
        limit: int = 30,
    ) -> CommodityIngestResult:
        ...


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_json_object_dict(value: object) -> TypeGuard[dict[str, JsonValue]]:
    return _is_object_dict(value) and all(isinstance(key, str) for key in value)


def _json_value(value: object, *, path: str) -> JsonValue:
    """Validate an untyped service boundary before publishing JSON."""
    if value is None or isinstance(value, (bool, int, float, str)):
        normalized: JsonValue = value
    elif _is_object_list(value):
        normalized = [
            _json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    elif _is_object_dict(value):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} must use string JSON object keys")
            result[key] = _json_value(item, path=f"{path}.{key}")
        normalized = result
    else:
        raise TypeError(f"{path} contains non-JSON value {type(value).__name__}")
    try:
        return _INGEST_JSON_VALUE_ADAPTER.validate_python(normalized)
    except ValidationError as exc:
        raise TypeError(f"{path} contains an invalid JSON value") from exc


def _json_object(value: object, *, path: str) -> IngestJsonObject:
    parsed = _json_value(value, path=path)
    if not _is_json_object_dict(parsed):
        raise TypeError(f"{path} must be a JSON object")
    result: IngestJsonObject = {}
    result.update(parsed)
    return result


def _optional_json_object(value: object, *, path: str) -> IngestJsonObject | None:
    if value is None:
        return None
    return _json_object(value, path=path)


def _json_string_list(value: object, *, path: str) -> list[str]:
    if not _is_object_list(value) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{path} must be an array of strings")
    return [item for item in value if isinstance(item, str)]


def _json_int(value: object, *, path: str, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise TypeError(f"{path} must be an integer") from exc
    raise TypeError(f"{path} must be an integer")


def _task_result_id(value: object, *, task_name: str) -> str:
    if not isinstance(value, _AsyncTaskResult):
        raise TypeError(f"{task_name} did not return an async task result")
    task_id = str(value.id).strip()
    if not task_id:
        raise RuntimeError(f"{task_name} returned an empty task id")
    return task_id

_INGEST_SUBMISSION_LOCK = Lock()
_INGEST_SUBMISSIONS: dict[str, IngestJsonObject] = {}

@lru_cache(maxsize=1)
def _tasks_module() -> _TasksModule:
    module = import_module("app.services.tasks")
    if not isinstance(module, _TasksModule):
        raise RuntimeError("app.services.tasks does not expose the ingest task contract")
    return module


@lru_cache(maxsize=1)
def _ingest_config_service() -> _IngestConfigService:
    module = import_module("app.services.ingest_config")
    if not isinstance(module, _IngestConfigService):
        raise RuntimeError("app.services.ingest_config does not expose its public service contract")
    return module


def get_ingest_config(project_key: str, config_key: str) -> IngestJsonObject | None:
    """Compatibility seam for the established API tests and direct callers."""
    return _ingest_config_service().get_config(project_key, config_key)


def upsert_ingest_config(
    *,
    project_key: str,
    config_key: str,
    config_type: str,
    payload: IngestJsonObject | None,
) -> IngestJsonObject:
    """Compatibility seam that retains the former module-level service alias."""
    return _ingest_config_service().upsert_config(
        project_key=project_key,
        config_key=config_key,
        config_type=config_type,
        payload=payload,
    )


@lru_cache(maxsize=1)
def _social_ingest_app() -> _SocialIngestApplication:
    from ..services.ingest.social_application import SocialIngestApplicationService

    return SocialIngestApplicationService()


@lru_cache(maxsize=1)
def _report_ingest_module() -> _ReportIngestModule:
    module = import_module("app.services.ingest.reports.general")
    if not isinstance(module, _ReportIngestModule):
        raise RuntimeError("report ingest service does not expose its public producer contract")
    return module


@lru_cache(maxsize=1)
def _commodity_ingest_module() -> _CommodityIngestModule:
    module = import_module("app.services.ingest.commodity")
    if not isinstance(module, _CommodityIngestModule):
        raise RuntimeError("commodity ingest service does not expose its public producer contract")
    return module


def _status_code_for_error_code(code: ErrorCode) -> int:
    if code in {ErrorCode.INVALID_INPUT, ErrorCode.PROJECT_KEY_REQUIRED, ErrorCode.CONFIG_ERROR}:
        return 400
    if code == ErrorCode.NOT_FOUND:
        return 404
    if code == ErrorCode.RATE_LIMITED:
        return 429
    if code in {ErrorCode.UPSTREAM_ERROR, ErrorCode.PARSE_ERROR}:
        return 503 if code == ErrorCode.UPSTREAM_ERROR else 502
    return 500


def _error_500(exc: Exception) -> JSONResponse:
    code, message, details = map_exception_to_error(exc)
    return error_json_response(
        _status_code_for_error_code(code),
        code,
        message,
        details=details,
    )


def _raise_invalid_input(
    message: str,
    *,
    details: IngestJsonObject | None = None,
    status_code: int = 400,
    cause: BaseException | None = None,
) -> NoReturn:
    error = HTTPException(
        status_code=status_code,
        detail=error_response(ErrorCode.INVALID_INPUT, message, details=details),
    )
    if cause is not None:
        raise error from cause
    raise error


def _raise_not_found(message: str, *, details: IngestJsonObject | None = None) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=error_response(ErrorCode.NOT_FOUND, message, details=details),
    )


def _raise_upstream_error(
    message: str,
    *,
    details: IngestJsonObject | None = None,
    cause: BaseException | None = None,
) -> NoReturn:
    error = HTTPException(
        status_code=503,
        detail=error_response(ErrorCode.UPSTREAM_ERROR, message, details=details),
    )
    if cause is not None:
        raise error from cause
    raise error


def _canonical_json(value: IngestJsonValue) -> str:
    normalized = _json_value(value, path="ingest.idempotency_payload")
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _derive_ingest_idempotency(
    *,
    trigger_type: str,
    project_key: str,
    explicit_key: str | None,
    basis: IngestJsonObject,
) -> tuple[str, str]:
    public_key = str(explicit_key or "").strip()
    if not public_key:
        public_key = f"{trigger_type}:{hashlib.sha256(_canonical_json(basis).encode('utf-8')).hexdigest()[:24]}"
    registry_key = f"{trigger_type}:{project_key}:{public_key}"
    return public_key, registry_key


def _submission_id_for_key(registry_key: str) -> str:
    return ingest_submission_registry.submission_id_for_key(registry_key)


def _request_hash_for_payload(payload: IngestJsonObject) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _raise_ingest_registry_conflict(
    exc: MaterialIngestRegistryConflictError,
    *,
    idempotency_key: str,
) -> NoReturn:
    _raise_invalid_input(
        "idempotency_key was already used with a different request payload",
        status_code=409,
        details={
            "reason": "idempotency_key_payload_conflict",
            "idempotency_key": idempotency_key,
            "registry_key": exc.registry_key,
            "request_hash": exc.request_hash,
        },
        cause=exc,
    )


def _raise_ingest_registry_unavailable(
    exc: MaterialIngestRegistryBackendUnavailableError,
) -> NoReturn:
    _raise_upstream_error(
        "ingest submission registry is unavailable",
        details={
            "reason": "ingest_submission_registry_unavailable",
            "registry_key": exc.registry_key,
            "request_hash": exc.request_hash,
            "exception_type": exc.__class__.__name__,
        },
        cause=exc,
    )


def _registry_meta(*, backend: str, degraded: bool) -> IngestJsonObject:
    return {"registry_backend": backend, "registry_degraded": bool(degraded)}


def _reserve_ingest_submission_db(
    *,
    registry_key: str,
    project_key: str,
    idempotency_key: str,
    trigger_type: str,
    subject: IngestJsonObject,
    request_payload: IngestJsonObject,
    request_hash: str,
) -> tuple[IngestJsonObject, bool]:
    raw_submission, duplicate = ingest_submission_registry.reserve_submission_db(
        registry_key=registry_key,
        project_key=project_key,
        idempotency_key=idempotency_key,
        trigger_type=trigger_type,
        subject=subject,
        request_payload=request_payload,
        request_hash=request_hash,
    )
    return _json_object(raw_submission, path="ingest_submission_registry.reserve"), bool(duplicate)


def _complete_ingest_submission_db(*, registry_key: str, response_payload: IngestJsonObject) -> None:
    ingest_submission_registry.complete_submission_db(
        registry_key=registry_key,
        response_payload=response_payload,
    )


def _forget_ingest_submission_db(*, registry_key: str) -> None:
    ingest_submission_registry.forget_submission_db(registry_key=registry_key)


def reserve_ingest_submission_memory_for_test(
    *,
    registry_key: str,
    project_key: str,
    idempotency_key: str,
    trigger_type: str,
    subject: IngestJsonObject,
    request_hash: str,
    degraded: bool,
) -> tuple[IngestJsonObject, bool]:
    with _INGEST_SUBMISSION_LOCK:
        existing = _INGEST_SUBMISSIONS.get(registry_key)
        if existing is not None:
            stored_hash = existing.get("request_hash")
            if stored_hash != request_hash:
                raise MaterialIngestRegistryConflictError(
                    "registry_key already exists with a different request_hash",
                    registry_key=registry_key,
                    request_hash=request_hash,
                )
            return deepcopy(existing), True

        now = datetime.now(timezone.utc).isoformat()
        submission: IngestJsonObject = {
            "submission_id": _submission_id_for_key(registry_key),
            "idempotency_key": idempotency_key,
            "trigger_type": trigger_type,
            "project_key": project_key,
            "registry_key": registry_key,
            "request_hash": request_hash,
            "subject": dict(subject),
            "submission_status": "submitted",
            "duplicate": False,
            "created_at": now,
            "updated_at": now,
            **_registry_meta(backend="memory", degraded=degraded),
        }
        _INGEST_SUBMISSIONS[registry_key] = deepcopy(submission)
        return deepcopy(submission), False


def _reserve_ingest_submission(
    *,
    registry_key: str,
    project_key: str,
    idempotency_key: str,
    trigger_type: str,
    subject: IngestJsonObject,
    request_payload: IngestJsonObject,
) -> tuple[IngestJsonObject, bool]:
    request_hash = _request_hash_for_payload(request_payload)
    try:
        submission, duplicate = _reserve_ingest_submission_db(
            registry_key=registry_key,
            project_key=project_key,
            idempotency_key=idempotency_key,
            trigger_type=trigger_type,
            subject=subject,
            request_payload=request_payload,
            request_hash=request_hash,
        )
        stored_hash = submission.get("request_hash")
        if not isinstance(stored_hash, str):
            _raise_ingest_registry_unavailable(
                MaterialIngestRegistryBackendUnavailableError(
                    "ingest submission registry returned no request_hash",
                    registry_key=registry_key,
                    request_hash=request_hash,
                )
            )
        if stored_hash != request_hash:
            _raise_ingest_registry_conflict(
                MaterialIngestRegistryConflictError(
                    "registry_key already exists with a different request_hash",
                    registry_key=registry_key,
                    request_hash=request_hash,
                ),
                idempotency_key=idempotency_key,
            )
        with _INGEST_SUBMISSION_LOCK:
            _INGEST_SUBMISSIONS[registry_key] = deepcopy(submission)
        return submission, duplicate
    except MaterialIngestRegistryConflictError as exc:
        _raise_ingest_registry_conflict(exc, idempotency_key=idempotency_key)
    except MaterialIngestRegistryBackendUnavailableError as exc:
        _raise_ingest_registry_unavailable(exc)
    except SQLAlchemyError as exc:
        _raise_ingest_registry_unavailable(
            MaterialIngestRegistryBackendUnavailableError(
                str(exc) or exc.__class__.__name__,
                registry_key=registry_key,
                request_hash=request_hash,
            )
        )


def _complete_ingest_submission(*, registry_key: str, response_payload: IngestJsonObject) -> None:
    try:
        _complete_ingest_submission_db(registry_key=registry_key, response_payload=response_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to persist ingest submission completion registry_key=%s err=%s", registry_key, exc)
    with _INGEST_SUBMISSION_LOCK:
        submission = _INGEST_SUBMISSIONS.get(registry_key)
        if submission is None:
            return
        submission["response"] = deepcopy(response_payload)
        submission["updated_at"] = datetime.now(timezone.utc).isoformat()
        if response_payload.get("task_id") is not None:
            submission["task_id"] = response_payload.get("task_id")
        if response_payload.get("status") is not None:
            submission["status"] = response_payload.get("status")
            submission["submission_status"] = response_payload.get("status")


def _forget_ingest_submission(*, registry_key: str) -> None:
    try:
        _forget_ingest_submission_db(registry_key=registry_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to delete ingest submission registry_key=%s err=%s", registry_key, exc)
    with _INGEST_SUBMISSION_LOCK:
        _INGEST_SUBMISSIONS.pop(registry_key, None)


def _apply_submission_fields(
    response_payload: IngestJsonObject,
    *,
    submission: IngestJsonObject,
    duplicate: bool = False,
) -> IngestJsonObject:
    payload = dict(response_payload)
    payload["submission_id"] = submission["submission_id"]
    payload["idempotency_key"] = submission["idempotency_key"]
    payload["submission_status"] = (
        "already_submitted"
        if duplicate
        else str(submission.get("submission_status") or submission.get("status") or "submitted")
    )
    payload["duplicate"] = bool(duplicate)
    payload["registry_backend"] = submission.get("registry_backend") or "memory"
    payload["registry_degraded"] = bool(submission.get("registry_degraded"))
    if submission.get("request_hash"):
        payload["request_hash"] = submission.get("request_hash")
    if duplicate:
        payload["duplicate_of"] = submission["submission_id"]
        payload["duplicate_hint"] = "duplicate idempotency_key; returning existing submission"
    payload.setdefault(
        "trace_chain",
        _build_ingest_trace_chain(
            entrypoint=str(submission.get("trigger_type") or "ingest"),
            project_key=str(submission.get("project_key") or ""),
            submission_id=str(submission.get("submission_id") or ""),
            task_id=str(payload.get("task_id") or ""),
            status=str(payload.get("status") or ""),
            provider=None,
        ),
    )
    trace_chain = _optional_json_object(payload.get("trace_chain"), path="submission.trace_chain") or {}
    payload["trace_id"] = trace_chain.get("trace_id")
    payload["feedback_state"] = _feedback_state_for_submission_payload(
        status=payload.get("status"),
        submission_status=payload.get("submission_status"),
        error=payload.get("error"),
    )
    return payload


def _duplicate_submission_response(submission: IngestJsonObject) -> IngestJsonObject:
    response_payload = submission.get("response")
    parsed_response = _optional_json_object(response_payload, path="submission.response")
    if parsed_response is not None:
        return _apply_submission_fields(parsed_response, submission=submission, duplicate=True)
    return _apply_submission_fields(
        {
            "task_id": submission.get("task_id"),
            "status": submission.get("status") or "submitted",
            "async": True,
            "params": _optional_json_object(submission.get("subject"), path="submission.subject") or {},
        },
        submission=submission,
        duplicate=True,
    )


def _validate_source_library_single_source_guard(
    override_params: IngestJsonObject,
) -> IngestJsonObject | None:
    try:
        return _optional_json_object(
            validate_single_source_guard(override_params),
            path="source_library.single_source_guard",
        )
    except SourceLibrarySingleSourceGuardError as exc:
        _raise_invalid_input(
            str(exc),
            details=_json_object(exc.details, path="source_library.single_source_guard.error_details"),
        )


def _build_ingest_trace_chain(
    *,
    entrypoint: str,
    project_key: str,
    submission_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    provider: str | None = None,
    fallback: IngestJsonObject | None = None,
    retrieval_run_id: str | None = None,
    known_limitations: list[str] | None = None,
) -> IngestJsonObject:
    normalized_submission_id = str(submission_id or "").strip() or None
    normalized_task_id = str(task_id or "").strip() or None
    normalized_retrieval_run_id = str(retrieval_run_id or "").strip() or None
    trace_seed = normalized_submission_id or normalized_task_id or _request_hash_for_payload(
        {"entrypoint": entrypoint, "project_key": project_key}
    )[:16]
    limitations = list(
        dict.fromkeys(
            [
                *(known_limitations or []),
                "ingest_response_does_not_persist_search_retrieval_run",
                "no_real_index_timestamp_at_ingest_response",
            ]
        )
    )
    fallback_payload: IngestJsonObject = {
        "used": "unknown",
        "reason": "provider_execution_not_observed_at_ingest_response",
    }
    if isinstance(fallback, dict):
        fallback_payload.update(fallback)
        fallback_payload.setdefault("used", "unknown")
        fallback_payload.setdefault("reason", "provider_execution_not_observed_at_ingest_response")
    return {
        "contract_version": "ingest_search.trace_chain.v1",
        "trace_id": f"{entrypoint}:{trace_seed}",
        "project_key": project_key,
        "entrypoint": entrypoint,
        "run_order": [
            {
                "order": 1,
                "stage": "ingest_submission",
                "submission_id": normalized_submission_id,
                "status": "registered" if normalized_submission_id else "not_registered",
            },
            {
                "order": 2,
                "stage": "dispatch_or_execution",
                "task_id": normalized_task_id,
                "status": status or ("queued" if normalized_task_id else "completed_or_inline"),
            },
            {
                "order": 3,
                "stage": "search_retrieval_run",
                "retrieval_run_id": normalized_retrieval_run_id,
                "status": "available" if normalized_retrieval_run_id else "not_created_at_ingest_response",
            },
        ],
        "ids": {
            "submission_id": normalized_submission_id,
            "task_id": normalized_task_id,
            "retrieval_run_id": normalized_retrieval_run_id,
        },
        "provider": str(provider or "").strip() or "unknown",
        "fallback": fallback_payload,
        "index": {
            "index_backend": "not_available_at_ingest_response",
            "freshness_state": "not_available",
            "real_timestamp_available": False,
            "timestamp_status": "not_available",
        },
        "known_limitations": limitations,
    }


def _build_worker_runtime_readback(
    *,
    line_key: str,
    trace_id: str | None,
    run_id: str | None = None,
    queue: str | None = None,
) -> IngestJsonObject:
    payload: IngestJsonObject = {
        "line_key": line_key,
        "trace_id": str(trace_id or "").strip(),
    }
    if run_id:
        payload["run_id"] = str(run_id).strip()
    if queue:
        payload["queue"] = str(queue).strip()
    return {key: value for key, value in payload.items() if value}


def _feedback_state_for_submission_payload(
    *,
    status: object,
    submission_status: object,
    error: object = None,
) -> str:
    if error:
        return "failed"
    normalized_status = str(status or "").strip().lower()
    normalized_submission_status = str(submission_status or "").strip().lower()
    state = normalized_status or normalized_submission_status
    if state in {"failed", "error", "errored", "cancelled", "rejected"}:
        return "failed"
    if state.startswith("degraded"):
        return "degraded"
    if state in {"queued", "submitted", "already_submitted", "pending", "running", "started"}:
        return "accepted_pending_worker"
    if state in {"ok", "completed", "complete", "finished", "succeeded", "success"}:
        return "completed"
    return "unknown"


def _submission_history_entry(submission: IngestJsonObject) -> IngestJsonObject:
    response_payload = _optional_json_object(submission.get("response"), path="submission.response") or {}
    task_id = response_payload.get("task_id") or submission.get("task_id")
    runtime_run_ref = response_payload.get("runtime_run_ref") or submission.get("runtime_run_ref")
    status = response_payload.get("status") or submission.get("status") or submission.get("submission_status")
    trace_chain = _optional_json_object(response_payload.get("trace_chain"), path="submission.response.trace_chain")
    if trace_chain is None:
        trace_chain = _build_ingest_trace_chain(
            entrypoint=str(submission.get("trigger_type") or "ingest"),
            project_key=str(submission.get("project_key") or ""),
            submission_id=str(submission.get("submission_id") or ""),
            task_id=str(task_id or ""),
            status=str(status or ""),
            provider=None,
        )
    trace_id = str(response_payload.get("trace_id") or trace_chain.get("trace_id") or "").strip() or None
    submission_status = str(submission.get("submission_status") or status or "submitted")
    entry: IngestJsonObject = {
        "id": submission.get("submission_id"),
        "job_type": "ingest_submission",
        "status": status,
        "task_status": status,
        "task_id": task_id,
        "runtime_run_ref": runtime_run_ref,
        "submission_id": submission.get("submission_id"),
        "idempotency_key": submission.get("idempotency_key"),
        "submission_status": submission_status,
        "trigger_type": submission.get("trigger_type"),
        "project_key": submission.get("project_key"),
        "trace_id": trace_id,
        "trace_chain": trace_chain,
        "feedback_state": _feedback_state_for_submission_payload(
            status=status,
            submission_status=submission_status,
            error=response_payload.get("error") or submission.get("last_error"),
        ),
        "registry_backend": submission.get("registry_backend") or "memory",
        "registry_degraded": bool(submission.get("registry_degraded")),
        "params": {
            "subject": _optional_json_object(submission.get("subject"), path="submission.subject") or {},
            "response": deepcopy(response_payload),
        },
        "started_at": submission.get("created_at"),
        "updated_at": submission.get("updated_at"),
        "finished_at": None,
        "error": response_payload.get("error") or submission.get("last_error"),
    }
    if submission.get("request_hash"):
        entry["request_hash"] = submission.get("request_hash")
    return entry


def _list_recent_ingest_submissions_db(limit: int) -> list[IngestJsonObject]:
    raw_rows = _json_value(
        ingest_submission_registry.list_recent_submissions_db(limit),
        path="ingest_submission_registry.history",
    )
    if not _is_object_list(raw_rows):
        raise TypeError("ingest submission registry history must be an array")
    return [_json_object(row, path=f"ingest_submission_registry.history[{index}]") for index, row in enumerate(raw_rows)]


def _list_recent_ingest_submission_history(limit: int) -> list[IngestJsonObject]:
    limit = max(1, min(int(limit or 20), 100))
    submissions: list[IngestJsonObject] = []
    try:
        submissions.extend(_list_recent_ingest_submissions_db(limit))
    except ProgrammingError as exc:
        msg = str(exc).lower()
        if "does not exist" not in msg and "ingest_submission_registry" not in msg:
            raise
    except DatabaseError as exc:
        msg = str(exc).lower()
        if "ingest_submission_registry" not in msg:
            raise
        logger.warning("ingest submission registry unavailable for history readback: %s", exc)

    with _INGEST_SUBMISSION_LOCK:
        memory_submissions = [deepcopy(item) for item in _INGEST_SUBMISSIONS.values()]

    seen: set[str] = set()
    merged: list[IngestJsonObject] = []
    for submission in [*submissions, *memory_submissions]:
        key = str(submission.get("registry_key") or submission.get("submission_id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(_submission_history_entry(submission))
    merged.sort(key=lambda entry: str(entry.get("updated_at") or entry.get("started_at") or ""), reverse=True)
    return merged[:limit]


def _merge_runtime_readback_override(
    payload: IngestJsonObject | None,
    runtime_readback: IngestJsonObject,
) -> IngestJsonObject:
    merged = dict(payload or {})
    existing = merged.get("runtime_readback")
    existing_payload = _optional_json_object(existing, path="override_params.runtime_readback") or {}
    merged["runtime_readback"] = {**runtime_readback, **existing_payload}
    return merged


def _dispatch_market_collect_async(
    *,
    query_terms: list[str],
    max_items: int,
    project_key: str,
    enable_extraction: bool,
    start_offset: int | None,
    days_back: int | None,
    language: str | None,
    provider: str | None,
    consumer: str,
) -> str:
    # Keep parity with historical async semantics while routing through skill runtime.
    invoked = _json_object(invoke_skill(
        skill_id="ingest.dispatch.market_collect",
        payload={
            "query_terms": list(query_terms or []),
            "max_items": int(max_items),
            "project_key": project_key,
            "provider": provider,
            "language": language,
            "days_back": days_back,
            "lane": "main",
            "override_params": {
                "enable_extraction": bool(enable_extraction),
                "start_offset": start_offset,
            },
        },
        context={
            "actor_role": "business_capability_wrapper",
            "permissions": ["ingest.dispatch.market_collect"],
            "consumer": consumer,
            "trace_id": f"{consumer}.market",
        },
    ), path="skill.ingest.dispatch.market_collect")
    result = _optional_json_object(invoked.get("result"), path="skill.ingest.dispatch.market_collect.result")
    task_id = str((result or {}).get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("market async dispatch skill returned empty task_id")
    return task_id


def _dispatch_source_library_item_async(
    *,
    item_key: str,
    project_key: str,
    override_params: IngestJsonObject,
    consumer: str,
    trace_id: str | None = None,
    workflow_run_id: str | None = None,
) -> str:
    invoked = _json_object(invoke_skill(
        skill_id="ingest.dispatch.source_library_item",
        payload={
            "item_key": item_key,
            "project_key": project_key,
            "override_params": dict(override_params or {}),
            "lane": "subagent",
            "trace_id": str(trace_id or "").strip() or None,
            "workflow_run_id": str(workflow_run_id or "").strip() or None,
        },
        context={
            "actor_role": "business_capability_wrapper",
            "permissions": ["ingest.dispatch.source_library_item"],
            "consumer": consumer,
            "trace_id": str(trace_id or "").strip() or f"{consumer}.source_library",
        },
    ), path="skill.ingest.dispatch.source_library_item")
    result = _optional_json_object(invoked.get("result"), path="skill.ingest.dispatch.source_library_item.result")
    task_id = str((result or {}).get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("source library async dispatch skill returned empty task_id")
    return task_id


def _skill_dispatch_ingest_market_collect(payload: IngestJsonObject) -> IngestJsonObject:
    query_terms = _normalize_query_terms(
        _json_string_list(payload.get("query_terms"), path="skill.market.query_terms"),
        None,
    )
    raw_max_items = payload.get("max_items")
    max_items = _normalize_max_items(raw_max_items if isinstance(raw_max_items, int) else None, None)
    project_key = _require_project_key(str(payload.get("project_key") or "").strip() or None)
    lane = validate_lane(str(payload.get("lane") or "").strip() or None)
    override_params = _optional_json_object(payload.get("override_params"), path="skill.market.override_params") or {}
    enable_extraction = bool(override_params.get("enable_extraction", True))
    start_offset = override_params.get("start_offset")
    if not isinstance(start_offset, int):
        start_offset = None
    trace_id = str(payload.get("trace_id") or "").strip() or None
    workflow_run_id = str(payload.get("workflow_run_id") or "").strip() or None
    raw_days_back = payload.get("days_back")
    days_back = raw_days_back if isinstance(raw_days_back, int) else None
    language = str(payload.get("language") or "").strip() or None
    provider = str(payload.get("provider") or "").strip() or None
    task: object = apply_async_or_delay(
        _tasks_module().task_ingest_market,
        (
            query_terms,
            max_items,
            enable_extraction,
            project_key,
            start_offset,
            days_back,
            language,
            provider,
        ),
        {"workflow_run_id": workflow_run_id, "trace_id": trace_id},
        lane,
    )
    return {"task_id": _task_result_id(task, task_name="task_ingest_market")}


def _skill_dispatch_ingest_source_library_item(payload: IngestJsonObject) -> IngestJsonObject:
    item_key = str(payload.get("item_key") or "").strip()
    if not item_key:
        raise ValueError("item_key is required")
    project_key = _require_project_key(str(payload.get("project_key") or "").strip() or None)
    lane = validate_lane(str(payload.get("lane") or "").strip() or None)
    override_params = _optional_json_object(payload.get("override_params"), path="skill.source_library.override_params") or {}
    trace_id = str(payload.get("trace_id") or "").strip() or None
    workflow_run_id = str(payload.get("workflow_run_id") or "").strip() or None
    task: object = apply_async_or_delay(
        _tasks_module().task_run_source_library_item,
        (item_key, project_key, override_params),
        {"workflow_run_id": workflow_run_id, "trace_id": trace_id},
        lane,
    )
    return {"task_id": _task_result_id(task, task_name="task_run_source_library_item")}


# Accessed dynamically by the skill runtime bootstrap; public aliases keep that
# contribution edge visible to static analysis without duplicating registration.
skill_dispatch_ingest_market_collect = _skill_dispatch_ingest_market_collect
skill_dispatch_ingest_source_library_item = _skill_dispatch_ingest_source_library_item


def _require_project_key(project_key: str | None) -> str:
    """Stage-1 policy: allow context fallback but emit warning for observability."""
    key = (project_key or "").strip()
    if key:
        return key

    enforcement_mode = get_effective_project_key_enforcement_mode()
    if enforcement_mode == "require":
        raise HTTPException(
            status_code=400,
            detail=error_response(
                ErrorCode.PROJECT_KEY_REQUIRED,
                "project_key is required. Please select a project first.",
            ),
        )

    fallback = (current_project_key() or "").strip()
    if fallback:
        logger.warning("project_key_fallback_used endpoint=ingest resolved_project_key=%s", fallback)
        return fallback

    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.PROJECT_KEY_REQUIRED,
            "project_key is required. Please select a project first.",
        ),
    )


def _normalize_query_terms(
    query_terms: list[str] | None,
    legacy_keywords: list[str] | None,
    *,
    field_name: str = "query_terms",
) -> list[str]:
    raw_terms = query_terms if query_terms is not None else legacy_keywords
    terms = [str(item).strip() for item in (raw_terms or []) if str(item).strip()]
    if not terms:
        _raise_invalid_input(
            f"{field_name} is required and cannot be empty.",
            details={"field": field_name, "value": raw_terms or []},
        )
    # Preserve order while deduplicating.
    return list(dict.fromkeys(terms))


def _normalize_max_items(
    max_items: int | None,
    legacy_limit: int | None,
    *,
    default_value: int = 20,
    min_value: int = 1,
    max_value: int = 100,
) -> int:
    value = max_items if max_items is not None else legacy_limit
    if value is None:
        value = default_value
    value = int(value)
    return max(min_value, min(max_value, value))


def _expand_query_terms_with_topic_focus(
    query_terms: list[str],
    *,
    topic_focus: str | None,
    language: str | None,
) -> tuple[list[str], IngestJsonObject]:
    focus = str(topic_focus or "").strip().lower()
    if focus not in {"company", "product", "operation"}:
        return query_terms, {}
    try:
        from ..services.search.web import generate_topic_keywords
        topic = " ".join(query_terms[:4]).strip() or (query_terms[0] if query_terms else "")
        kw = _json_object(generate_topic_keywords(
            topic,
            topic_focus=focus,
            language=language or "zh",
            base_keywords=query_terms,
        ), path="search.generate_topic_keywords")
        raw_extra = kw.get("search_keywords")
        extra = _json_string_list(raw_extra, path="search.generate_topic_keywords.search_keywords") if raw_extra else []
        merged = list(dict.fromkeys([*query_terms, *extra]))
        return merged, {"topic_focus": focus, "topic_hints": kw.get("topic_hints") or [], "topic_search_keywords": extra}
    except Exception as exc:  # noqa: BLE001
        logger.warning("topic keyword expansion failed focus=%s err=%s", focus, exc)
        return query_terms, {}


router = APIRouter(prefix="/ingest", tags=["ingest"])
IngestJsonEnvelope = ApiEnvelope[JsonValue]


class IngestConfigUpsertPayload(BaseModel):
    project_key: str | None = Field(default=None, description="Project key (optional, fallback to context)")
    config_key: str = Field(..., min_length=1, description="Config key, e.g. social_forum")
    config_type: str = Field(..., min_length=1, description="Config type")
    payload: IngestJsonObject | None = Field(default=None, description="Config payload (JSON)")


@router.get("/config", response_model=IngestJsonEnvelope)
def get_ingest_config_endpoint(
    project_key: str | None = Query(default=None),
    config_key: str = Query(..., description="Config key, e.g. social_forum"),
) -> IngestJsonObject | JSONResponse:
    """Get ingest config by project_key and config_key."""
    pk = _require_project_key(project_key)
    raw_data = get_ingest_config(pk, config_key)
    if raw_data is None:
        return error_json_response(404, ErrorCode.NOT_FOUND, f"Config not found: {config_key}")
    return ok(raw_data)


@router.post("/config", response_model=IngestJsonEnvelope)
def post_ingest_config_endpoint(body: IngestConfigUpsertPayload) -> IngestJsonObject:
    """Upsert ingest config."""
    pk = _require_project_key(body.project_key)
    try:
        data = upsert_ingest_config(
            project_key=pk,
            config_key=body.config_key,
            config_type=body.config_type,
            payload=body.payload,
        )
        return ok(data)
    except ValueError as exc:
        _raise_invalid_input(
            str(exc) or "Invalid ingest config payload.",
            details={"config_key": body.config_key, "exception_type": exc.__class__.__name__},
        )
    except Exception as exc:
        code, message, details = map_exception_to_error(exc)
        status_code = 503 if code == ErrorCode.UPSTREAM_ERROR else 500
        raise HTTPException(
            status_code=status_code,
            detail=error_response(
                code,
                message,
                details=details or {"config_key": body.config_key, "exception_type": exc.__class__.__name__},
            ),
        ) from exc


class MarketIngestRequest(BaseModel):
    """Generic market info (web search). Project-specific fixed sources use source library."""
    query_terms: list[str] | None = Field(default=None, description="查询词列表")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词")
    max_items: int | None = Field(default=None, ge=1, le=100, description="每查询词结果数")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")
    project_key: str | None = Field(default=None, description="项目标识")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(Google CSE: 1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    language: str | None = Field(default=None, description="语言 en/zh")
    provider: str | None = Field(default=None, description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


class SingleUrlIngestRequest(BaseModel):
    url: str = Field(..., min_length=1, description="单个网页 URL")
    query_terms: list[str] | None = Field(default=None, description="可选查询词（用于增强提取）")
    idempotency_key: str | None = Field(default=None, description="Optional client-supplied key to deduplicate repeated submissions")
    strict_mode: bool = Field(default=False, description="是否启用严格模式")
    search_expand: bool = Field(default=True, description="搜索页是否展开抓取结果链接")
    search_expand_limit: int = Field(default=3, ge=1, le=20, description="搜索页展开抓取的URL上限")
    search_provider: str | None = Field(default="auto", description="搜索页来源提供方，auto/google/ddg_html")
    search_fallback_provider: str | None = Field(default="ddg_html", description="搜索结果不足时的兜底提供方，如 ddg_html")
    fallback_on_insufficient: bool = Field(default=True, description="搜索结果不足时是否启用兜底搜索")
    allow_search_summary_write: bool = Field(default=False, description="当不展开搜索结果时是否允许将搜索摘要写入文档")
    min_results_required: int = Field(default=6, ge=1, le=20, description="判定搜索页有效结果数的阈值")
    target_candidates: int = Field(default=6, ge=1, le=20, description="搜索页目标候选数")
    decode_redirect_wrappers: bool = Field(default=True, description="是否解包搜索重定向链接")
    filter_low_value_candidates: bool = Field(default=True, description="是否过滤低价值候选链接")
    light_filter_enabled: bool = Field(default=True, description="是否启用轻度过滤(Stage F)")
    light_filter_min_score: int = Field(default=30, ge=0, le=100, description="轻度过滤最低通过分数")
    light_filter_reject_static_assets: bool = Field(default=True, description="轻度过滤是否拒绝静态资源URL")
    light_filter_reject_search_noise_domain: bool = Field(default=True, description="轻度过滤是否拒绝搜索噪音域名")
    project_key: str | None = Field(default=None, description="项目标识")
    async_mode: bool = Field(default=False, description="是否走 Celery 异步任务")


class NewsRequest(BaseModel):
    limit: int = Field(default=10, ge=1, le=50, description="抓取的条数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class RedditRequest(BaseModel):
    subreddit: str = Field(default_factory=lambda: settings.default_reddit_subreddit, description="子论坛名称")
    limit: int = Field(default=20, ge=1, le=100, description="抓取贴文数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class CommodityRequest(BaseModel):
    limit: int = Field(default=30, ge=1, le=365, description="每个指标抓取的历史天数")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


class EcomPriceRequest(BaseModel):
    limit: int = Field(default=100, ge=1, le=500, description="最大商品数量")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")


@router.post("/market", response_model=IngestJsonEnvelope)
def ingest_market(payload: MarketIngestRequest) -> IngestJsonObject | JSONResponse:
    """Generic market info (web search). Project-specific fixed sources use source library."""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords, field_name="query_terms")
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language=payload.language or "en"
    )
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task_id = _dispatch_market_collect_async(
            query_terms=query_terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=payload.enable_extraction,
            start_offset=payload.start_offset,
            days_back=payload.days_back,
            language=payload.language,
            provider=payload.provider,
            consumer="ingest.market.api",
        )
        return success_response(
            task_result_response(
                task_id=task_id,
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.collect_runtime import collect_request_from_market_api, run_collect
            req = collect_request_from_market_api(
                query_terms=query_terms,
                max_items=max_items,
                project_key=project_key,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            )
            cr = run_collect(req)
            raw = _optional_json_object(cr.meta.get("raw"), path="collect.market.meta.raw") or {
                "inserted": cr.inserted,
                "updated": cr.updated,
                "skipped": cr.skipped,
                "display_meta": cr.display_meta,
            }
            if topic_meta:
                raw["topic_focus"] = topic_meta.get("topic_focus")
                raw["topic_hints"] = topic_meta.get("topic_hints") or []
                raw["topic_search_keywords"] = topic_meta.get("topic_search_keywords") or []
            return ok(raw)
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/url/single", response_model=IngestJsonEnvelope)
def ingest_url_single(
    payload: SingleUrlIngestRequest, request: Request
) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    normalized_url = str(payload.url or "").strip()
    if not normalized_url:
        raise HTTPException(
            status_code=400,
            detail=error_response(ErrorCode.INVALID_INPUT, "url is required and cannot be empty."),
        )

    effective_payload: IngestJsonObject = {
        "url": normalized_url,
        "query_terms": payload.query_terms,
        "idempotency_key": str(payload.idempotency_key or "").strip() or None,
        "strict_mode": payload.strict_mode,
        "search_expand": bool(payload.search_expand),
        "search_expand_limit": int(payload.search_expand_limit),
        "search_provider": payload.search_provider,
        "search_fallback_provider": payload.search_fallback_provider,
        "fallback_on_insufficient": bool(payload.fallback_on_insufficient),
        "allow_search_summary_write": bool(payload.allow_search_summary_write),
        "min_results_required": int(payload.min_results_required),
        "target_candidates": int(payload.target_candidates),
        "decode_redirect_wrappers": bool(payload.decode_redirect_wrappers),
        "filter_low_value_candidates": bool(payload.filter_low_value_candidates),
        "light_filter_enabled": bool(payload.light_filter_enabled),
        "light_filter_min_score": int(payload.light_filter_min_score),
        "light_filter_reject_static_assets": bool(payload.light_filter_reject_static_assets),
        "light_filter_reject_search_noise_domain": bool(payload.light_filter_reject_search_noise_domain),
        "async_mode": bool(payload.async_mode),
    }

    search_options: IngestJsonObject | None = None
    if (
        not bool(payload.search_expand)
        or int(payload.search_expand_limit) != 3
        or str(payload.search_provider or "auto").strip().lower() != "auto"
        or str(payload.search_fallback_provider or "ddg_html").strip().lower() != "ddg_html"
        or not bool(payload.fallback_on_insufficient)
        or bool(payload.allow_search_summary_write)
        or int(payload.min_results_required) != 6
        or int(payload.target_candidates) != 6
        or not bool(payload.decode_redirect_wrappers)
        or not bool(payload.filter_low_value_candidates)
        or not bool(payload.light_filter_enabled)
        or int(payload.light_filter_min_score) != 30
        or not bool(payload.light_filter_reject_static_assets)
        or not bool(payload.light_filter_reject_search_noise_domain)
    ):
        search_options = dict(effective_payload)
        search_options.pop("url", None)
        search_options.pop("query_terms", None)
        search_options.pop("idempotency_key", None)
        search_options.pop("strict_mode", None)
        search_options.pop("async_mode", None)

    registry_key: str | None = None
    if payload.async_mode:
        from ..services.request_identity import require_trusted_actor_context

        actor_context = require_trusted_actor_context(request)
        idempotency_key, registry_key = _derive_ingest_idempotency(
            trigger_type="ingest.url.single",
            project_key=project_key,
            explicit_key=payload.idempotency_key,
            basis={
                "project_key": project_key,
                "url": normalized_url,
                "query_terms": payload.query_terms or [],
                "strict_mode": bool(payload.strict_mode),
                "search_options": search_options or {},
            },
        )
        submission, duplicate = _reserve_ingest_submission(
            registry_key=registry_key,
            project_key=project_key,
            idempotency_key=idempotency_key,
            trigger_type="ingest.url.single",
            subject={"url": normalized_url, "project_key": project_key},
            request_payload={
                "project_key": project_key,
                "url": normalized_url,
                "query_terms": payload.query_terms or [],
                "strict_mode": bool(payload.strict_mode),
                "search_options": search_options or {},
                "async_mode": True,
            },
        )
        if duplicate:
            return ok(_duplicate_submission_response(submission))
        try:
            from app.composition.production import submit_installed_program
            from app.models.base import engine as runtime_engine
            from app.successor_runtime.capabilities.acquisition_url import (
                URL_SINGLE_URL_KIND,
                URL_SINGLE_URL_OWNER,
                UrlSingleUrlRequest,
                build_url_single_url_program,
            )
            from app.successor_runtime.substrate.postgres.session import ServerProjectScopeResolver

            submission_id = str(submission.get("submission_id") or idempotency_key)
            run_id = f"url-single-{submission_id}"
            trace_id = f"ingest.url.single:{submission_id}"
            actor_id = actor_context.actor_id
            extra_params: CollectJsonObject = {
                "strict_mode": bool(payload.strict_mode),
                "enable_extraction": True,
            }
            if isinstance(search_options, dict):
                extra_params.update(source_library_compat_response(search_options))

            with runtime_engine.connect() as connection:
                project_scope = ServerProjectScopeResolver(connection=connection).resolve(project_key)
            closure = build_url_single_url_program(
                request=UrlSingleUrlRequest(
                    url=normalized_url,
                    project_key=project_key,
                    query_terms=tuple(payload.query_terms or []),
                    extra_params=extra_params,
                    enable_extraction=True,
                ),
                program_id=f"program:{run_id}",
                project_key=project_key,
                project_registry_revision=project_scope.project_registry_revision,
                project_scope_digest=project_scope.scope_digest,
                incarnation=f"url-single:{submission_id}",
            )
            run, work_item_ids = submit_installed_program(
                engine=runtime_engine,
                project_key=project_key,
                actor_id=actor_id,
                program=closure.program,
                operation_catalog=closure.catalog,
                operation_contracts=closure.registry,
                values=closure.values,
                idempotency_id=f"url-single-idem:{run_id}",
                identity_capability_id=URL_SINGLE_URL_OWNER,
                logical_request_id=idempotency_key,
                identity_operation_kind=URL_SINGLE_URL_KIND,
                run_id=run_id,
                incarnation=f"url-single:{submission_id}",
                canonical_bindings=closure.canonical_bindings,
                approvals_by_step={},
                trace_id=trace_id,
                now=datetime.now(timezone.utc),
                queue="celery",
            )
            canonical_run_id = str(run.get("run_id") or run_id)
            run_ref = f"runtime-run:{canonical_run_id}"
        except Exception:
            _forget_ingest_submission(registry_key=registry_key)
            raise
        task_payload = _json_object(task_result_response(
            task_id=None,
            async_mode=True,
            params={
                "url": normalized_url,
                "query_terms": payload.query_terms,
                "strict_mode": payload.strict_mode,
                **({"search_options": search_options} if isinstance(search_options, dict) else {}),
            },
        ), path="ingest.url.single.async_response")
        task_payload["status"] = "submitted"
        task_payload["runtime_run_ref"] = run_ref
        task_payload["runtime_state"] = str(run.get("state") or "")
        task_payload["work_item_ids"] = list(work_item_ids)
        task_payload["effective_payload"] = effective_payload
        task_payload = _apply_submission_fields(task_payload, submission=submission)
        task_payload["trace_chain"] = _build_ingest_trace_chain(
            entrypoint="ingest.url.single",
            project_key=project_key,
            submission_id=str(task_payload.get("submission_id") or "") or None,
            task_id=str(task_payload.get("task_id") or "") or None,
            status=str(task_payload.get("status") or "") or None,
            provider=payload.search_provider or "auto",
            fallback={
                "enabled": bool(payload.fallback_on_insufficient),
                "provider": payload.search_fallback_provider,
                "used": "unknown",
                "reason": "async_url_ingest_dispatched_provider_execution_pending",
            },
        )
        _complete_ingest_submission(registry_key=registry_key, response_payload=task_payload)
        return ok(task_payload)

    try:
        idempotency_key, registry_key = _derive_ingest_idempotency(
            trigger_type="ingest.url.single",
            project_key=project_key,
            explicit_key=payload.idempotency_key,
            basis={
                "project_key": project_key,
                "url": normalized_url,
                "query_terms": payload.query_terms or [],
                "strict_mode": bool(payload.strict_mode),
                "search_options": search_options or {},
            },
        )
        submission, duplicate = _reserve_ingest_submission(
            registry_key=registry_key,
            project_key=project_key,
            idempotency_key=idempotency_key,
            trigger_type="ingest.url.single",
            subject={"url": normalized_url, "project_key": project_key},
            request_payload={
                "project_key": project_key,
                "url": normalized_url,
                "query_terms": payload.query_terms or [],
                "strict_mode": bool(payload.strict_mode),
                "search_options": search_options or {},
                "async_mode": False,
            },
        )
        if duplicate:
            return ok(_duplicate_submission_response(submission))
        with bind_project(project_key):
            from ..services.ingest.url_pool import ingest_url_via_source_library_frontdoor

            result = _json_object(ingest_url_via_source_library_frontdoor(
                url=normalized_url,
                project_key=project_key,
                query_terms=payload.query_terms,
                strict_mode=payload.strict_mode,
                search_options=search_options,
                frontdoor_options={"enabled": True},
                entrypoint="ingest.url.single",
                source_name="ingest_url_single",
                enable_extraction=True,
            ), path="ingest.url.single.result")
            result.setdefault("effective_payload", effective_payload)
            result = _apply_submission_fields(result, submission=submission)
            result["trace_chain"] = _build_ingest_trace_chain(
                entrypoint="ingest.url.single",
                project_key=project_key,
                submission_id=str(result.get("submission_id") or "") or None,
                task_id=str(result.get("task_id") or "") or None,
                status=str(result.get("status") or "") or None,
                provider=payload.search_provider or "auto",
                fallback={
                    "enabled": bool(payload.fallback_on_insufficient),
                    "provider": payload.search_fallback_provider,
                    "used": bool(str(result.get("status") or "").lower().startswith("degraded")),
                    "reason": (
                        "sync_url_ingest_returned_degraded_status"
                        if str(result.get("status") or "").lower().startswith("degraded")
                        else "no_fallback_observed_in_ingest_response"
                    ),
                },
            )
            _complete_ingest_submission(registry_key=registry_key, response_payload=result)
            return ok(result)
    except Exception as exc:  # noqa: BLE001
        if registry_key:
            _forget_ingest_submission(registry_key=registry_key)
        return _error_500(exc)


@router.get("/history", response_model=IngestJsonEnvelope)
def ingest_history(limit: int = 20) -> IngestJsonObject:
    try:
        normalized_limit = max(1, min(int(limit or 20), 100))
        submissions = _list_recent_ingest_submission_history(normalized_limit)
        raw_jobs = _json_value(list_jobs(limit=normalized_limit), path="ingest.history.jobs")
        if not _is_object_list(raw_jobs):
            raise TypeError("ingest history jobs readback must be an array")
        jobs = [_json_object(job, path=f"ingest.history.jobs[{index}]") for index, job in enumerate(raw_jobs)]
        return _json_object(success_response([*submissions, *jobs]), path="ingest.history.response")
    except (OperationalError, DatabaseError) as e:
        logger.exception("数据库连接失败")
        _raise_upstream_error(
            "数据库服务不可用，请检查数据库服务是否已启动。",
            details={"reason": str(e)},
        )
    except Exception as e:
        logger.exception("获取历史记录失败")
        error_msg = str(e)
        if "Connection" in error_msg or "db" in error_msg.lower() or "database" in error_msg.lower() or "timeout" in error_msg.lower():
            _raise_upstream_error(
                "数据库服务不可用，请检查数据库服务是否已启动。",
                details={"reason": error_msg},
            )
        raise HTTPException(
            status_code=500,
            detail=error_response(
                ErrorCode.INTERNAL_ERROR,
                "获取历史记录失败。",
                details={"reason": error_msg},
            ),
        )


def _dispatch_news_resource(resource_id: str, payload: NewsRequest) -> IngestJsonObject | JSONResponse:
    """Dispatch to news resource handler. Effective = shared (总库) + project (子项目库), project overrides."""
    project_key = _require_project_key(payload.project_key)
    customization = get_project_customization(project_key)
    shared = customization.get_shared_news_resource_handlers()
    project_handlers = customization.get_news_resource_handlers()
    handlers = {**shared, **project_handlers}
    handler = handlers.get(resource_id)
    if not handler:
        _raise_not_found(
            f"Project '{project_key}' does not support news resource '{resource_id}'.",
            details={"project_key": project_key, "resource_id": resource_id},
        )
    if payload.async_mode:
        task: object = _tasks_module().task_collect_news_resource.delay(resource_id, payload.limit, project_key)
        return _json_object(success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_news_resource"),
                async_mode=True,
                params={"resource_id": resource_id, "limit": payload.limit},
            )
        ), path="ingest.news_resource.async_response")
    try:
        with bind_project(project_key):
            return _json_object(
                success_response(_json_object(handler(payload.limit), path="ingest.news_resource.result")),
                path="ingest.news_resource.response",
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


_NEWS_RESOURCE_DISPLAY_NAMES: dict[str, str] = {
    "google_news": "Google News",
}


def _resource_display_name(resource_id: str) -> str:
    return _NEWS_RESOURCE_DISPLAY_NAMES.get(resource_id) or resource_id.replace("_", " ").title()


class SourceLibraryRunItem(BaseModel):
    item_key: str | None = Field(default=None, min_length=1)
    handler_key: str | None = Field(default=None, min_length=1)
    idempotency_key: str | None = None
    source_mode: Literal["protocol_search", "provider_harvest", "site_search", "url_execution"] | None = None
    query_terms: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1, le=100)
    provider: str | None = None
    language: str | None = None
    scope: str | None = None
    platforms: list[str] = Field(default_factory=list)
    async_mode: bool = False
    override_params: IngestJsonObject = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class SourceLibraryRunPayload(BaseModel):
    item_key: str | None = Field(default=None, min_length=1)
    handler_key: str | None = Field(default=None, min_length=1, description="Run all items under this handler key (provider/kind)")
    idempotency_key: str | None = Field(default=None, description="Optional client-supplied key to deduplicate repeated submissions")
    source_mode: Literal["protocol_search", "provider_harvest", "site_search", "url_execution"] | None = Field(default=None)
    query_terms: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=1, le=100)
    provider: str | None = Field(default=None)
    language: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    platforms: list[str] = Field(default_factory=list)
    project_key: str | None = Field(default=None)
    async_mode: bool = Field(default=False)
    override_params: IngestJsonObject = Field(default_factory=dict)
    items: list[object] | None = Field(
        default=None,
        description="统一批量 item 入口；每个元素使用 item_key/handler_key 结构。",
    )


class SourceLibrarySyncPayload(BaseModel):
    project_key: str | None = Field(default=None)


def _ensure_handler_cluster_item(*, project_key: str, handler_key: str) -> tuple[str, int]:
    from ..services.resource_pool import list_site_entries
    from ..services.source_library.item_writer import (
        sync_handler_cluster_items,
    )

    hk = str(handler_key or "").strip().lower()
    if not hk:
        _raise_invalid_input("handler_key is required", details={"field": "handler_key"})
    if hk == "url_routing":
        _raise_invalid_input(
            "handler_key=url_routing is item-level URL routing, not a URL-entry(entry_type) cluster. Use item_key to run url_routing items.",
            details={"field": "handler_key", "value": hk},
        )

    page = 1
    page_size = 200
    site_entries: list[str] = []
    while True:
        rows, total = list_site_entries(
            scope="effective",
            project_key=project_key,
            entry_type=hk,
            enabled=True,
            page=page,
            page_size=page_size,
        )
        for r in rows:
            u = str(r.get("site_url") or "").strip()
            if u and u not in site_entries:
                site_entries.append(u)
        if not rows or page * page_size >= int(total or 0):
            break
        page += 1

    if not site_entries:
        _raise_not_found(
            f"No enabled site_entries found for handler_key={hk}",
            details={"handler_key": hk},
        )

    sync_response = _json_object(
        sync_handler_cluster_items(
            project_key=project_key,
            handlers=[hk],
            incremental=False,
            max_site_entries=len(site_entries),
        ),
        path="source_library.handler_cluster.sync",
    )
    sync_data = _json_object(
        sync_response.get("data"),
        path="source_library.handler_cluster.sync.data",
    )
    raw_results = sync_data.get("results")
    if not _is_object_list(raw_results):
        raise TypeError("source_library.handler_cluster.sync.data.results must be an array")
    item_key = f"handler.cluster.{hk}"
    for index, raw_result in enumerate(raw_results):
        result = _json_object(
            raw_result,
            path=f"source_library.handler_cluster.sync.data.results[{index}]",
        )
        if result.get("handler_key") != hk or result.get("item_key") != item_key:
            continue
        site_entries_after = _json_int(
            result.get("site_entries_after"),
            path=f"source_library.handler_cluster.sync.data.results[{index}].site_entries_after",
        )
        if site_entries_after <= 0:
            raise TypeError("source_library handler cluster sync returned an empty cluster")
        return item_key, site_entries_after
    raise TypeError("source_library handler cluster sync omitted the requested handler")


def _run_single_source_library_entry(
    *,
    project_key: str,
    item_key: str,
    handler_key: str,
    idempotency_key: str | None,
    source_mode: str,
    query_terms: list[str] | None,
    urls: list[str] | None,
    max_items: int | None,
    provider: str | None,
    language: str | None,
    scope: str | None,
    platforms: list[str] | None,
    async_mode: bool,
    override_params: IngestJsonObject | None,
) -> IngestJsonObject:
    def _external_terminal_payload(raw_result: object) -> IngestJsonObject:
        result: CollectJsonObject = source_library_compat_response(raw_result)
        terminal_output = result.get("terminal_output")
        if isinstance(terminal_output, dict):
            raw_authority_output = result.get("authority_output")
            authority_output = raw_authority_output if isinstance(raw_authority_output, dict) else None
            raw_compat_projection = result.get("compat_projection")
            compat_projection = raw_compat_projection if isinstance(raw_compat_projection, dict) else None
            raw_frontdoor_ingress = result.get("frontdoor_ingress")
            frontdoor_ingress = raw_frontdoor_ingress if isinstance(raw_frontdoor_ingress, dict) else None
            raw_postprocess_frontdoor = result.get("postprocess_frontdoor")
            postprocess_frontdoor = raw_postprocess_frontdoor if isinstance(raw_postprocess_frontdoor, dict) else None
            raw_legacy_result = result.get("legacy_result")
            legacy_result = raw_legacy_result if isinstance(raw_legacy_result, dict) else None
            if authority_output is None and frontdoor_ingress and postprocess_frontdoor and legacy_result is not None:
                from ..services.collect_runtime.adapters.source_library import (
                    build_source_library_authority_output,
                    build_source_library_compat_projection,
                )

                authority_output = build_source_library_authority_output(
                    terminal_output=terminal_output,
                    frontdoor_ingress=frontdoor_ingress,
                    postprocess_frontdoor=postprocess_frontdoor,
                    legacy_result=legacy_result,
                )
                compat_projection = build_source_library_compat_projection(
                    legacy_result=legacy_result,
                    authority_output=authority_output,
                )
            response_payload: CollectJsonObject = dict(terminal_output)
            response_payload.setdefault("terminal_output", terminal_output)
            if isinstance(authority_output, dict):
                response_payload["authority_output"] = dict(authority_output)
            if isinstance(compat_projection, dict):
                response_payload["compat_projection"] = dict(compat_projection)
            if isinstance(frontdoor_ingress, dict):
                response_payload["frontdoor_ingress"] = dict(frontdoor_ingress)
            if isinstance(postprocess_frontdoor, dict):
                response_payload["postprocess_frontdoor"] = dict(postprocess_frontdoor)
            if isinstance(legacy_result, dict):
                response_payload["legacy_result"] = dict(legacy_result)
                response_payload["legacy_result_is_deprecated"] = bool(result.get("legacy_result_is_deprecated", True))
            if result.get("display_meta") is not None and "display_meta" not in response_payload:
                response_payload["display_meta"] = result.get("display_meta")
            return _json_object(response_payload, path="source_library.terminal_output")
        from ..services.source_library.terminal_output import build_source_library_terminal_output

        return _json_object(
            build_source_library_terminal_output(result_payload=result, collect_result=None),
            path="source_library.compat_terminal_output",
        )

    resolved_item_key = str(item_key or "").strip()
    resolved_handler_key = str(handler_key or "").strip()
    mode_count = int(bool(resolved_item_key)) + int(bool(resolved_handler_key))
    if mode_count == 0:
        _raise_invalid_input(
            "item_key or handler_key is required.",
            details={"fields": ["item_key", "handler_key"]},
        )
    if mode_count > 1:
        _raise_invalid_input(
            "item_key and handler_key are mutually exclusive.",
            details={"fields": ["item_key", "handler_key"]},
        )

    final_override_params = _json_object(build_source_library_override_params(
        {
            "override_params": dict(override_params or {}),
            "query_terms": list(query_terms or []),
            "urls": list(urls or []),
            "max_items": max_items,
            "provider": provider,
            "language": language,
            "scope": scope,
            "platforms": list(platforms or []),
            "source_mode": str(source_mode or "").strip().lower() or None,
        },
        workflow_run_id=str((override_params or {}).get("workflow_run_id") or "").strip() or None,
    ), path="source_library.override_params")
    if resolved_handler_key:
        resolved_item_key, site_entry_count = _ensure_handler_cluster_item(
            project_key=project_key,
            handler_key=resolved_handler_key,
        )
        final_override_params.setdefault("_handler_key", resolved_handler_key)
        final_override_params.setdefault("_handler_site_entry_count", site_entry_count)
    single_source_guard = _validate_source_library_single_source_guard(final_override_params)

    submission: IngestJsonObject | None = None
    registry_key: str | None = None
    public_idempotency_key = str(idempotency_key or "").strip()
    if public_idempotency_key:
        public_idempotency_key, registry_key = _derive_ingest_idempotency(
            trigger_type="ingest.source_library.run",
            project_key=project_key,
            explicit_key=public_idempotency_key,
            basis={"project_key": project_key, "item_key": resolved_item_key, "override_params": final_override_params},
        )
        submission, duplicate = _reserve_ingest_submission(
            registry_key=registry_key,
            project_key=project_key,
            idempotency_key=public_idempotency_key,
            trigger_type="ingest.source_library.run",
            subject={"item_key": resolved_item_key, "project_key": project_key},
            request_payload={
                "project_key": project_key,
                "item_key": resolved_item_key,
                "source_mode": str(source_mode or "").strip().lower() or None,
                "override_params": final_override_params,
                "async_mode": bool(async_mode),
            },
        )
        if duplicate:
            return {"mode": "source_library_item", "result": _duplicate_submission_response(submission)}

    if async_mode:
        dispatch_trace_id = None
        dispatch_run_id = None
        if public_idempotency_key:
            dispatch_trace_id = f"ingest.source_library.run:{(submission or {}).get('submission_id') or public_idempotency_key}"
            dispatch_run_id = str((submission or {}).get("submission_id") or public_idempotency_key or "").strip() or None
            final_override_params = _merge_runtime_readback_override(
                final_override_params,
                _build_worker_runtime_readback(
                    line_key="resource_source_library",
                    trace_id=dispatch_trace_id,
                    run_id=dispatch_run_id,
                    queue="local.resource_source_library",
                ),
            )
        try:
            task_id = _dispatch_source_library_item_async(
                item_key=resolved_item_key,
                project_key=project_key,
                override_params=final_override_params,
                consumer="ingest.source_library.run",
                trace_id=dispatch_trace_id,
                workflow_run_id=dispatch_run_id,
            )
        except Exception:
            if registry_key:
                _forget_ingest_submission(registry_key=registry_key)
            raise
        result_payload = _json_object(task_result_response(
            task_id=task_id,
            async_mode=True,
            params={"item_key": resolved_item_key},
        ), path="source_library.async_result")
        if single_source_guard is not None:
            result_payload["single_source_guard"] = single_source_guard
            result_payload["strict_source"] = single_source_guard
        if submission and registry_key:
            result_payload = _apply_submission_fields(result_payload, submission=submission)
        result_payload["trace_chain"] = _build_ingest_trace_chain(
            entrypoint="ingest.source_library.run",
            project_key=project_key,
            submission_id=str(result_payload.get("submission_id") or "") or None,
            task_id=str(result_payload.get("task_id") or "") or None,
            status=str(result_payload.get("status") or "") or None,
            provider=str(final_override_params.get("provider") or final_override_params.get("source_mode") or "source_library"),
            fallback={
                "enabled": "unknown",
                "used": "unknown",
                "reason": "async_source_library_dispatched_provider_execution_pending",
            },
            known_limitations=["source_library_resolver_selects_final_provider_after_dispatch"],
        )
        if submission and registry_key:
            _complete_ingest_submission(registry_key=registry_key, response_payload=result_payload)
        return {"mode": "source_library_item", "result": result_payload}

    from ..services.collect_runtime import run_source_library_item_compat

    try:
        result: object = run_source_library_item_compat(
            item_key=resolved_item_key,
            project_key=project_key,
            override_params=source_library_compat_response(final_override_params),
        )
    except Exception:
        if registry_key:
            _forget_ingest_submission(registry_key=registry_key)
        raise
    result_payload = _external_terminal_payload(result)
    if single_source_guard is not None:
        result_payload["single_source_guard"] = single_source_guard
        result_payload["strict_source"] = single_source_guard
    if submission and registry_key:
        result_payload = _apply_submission_fields(result_payload, submission=submission)
    result_payload["trace_chain"] = _build_ingest_trace_chain(
        entrypoint="ingest.source_library.run",
        project_key=project_key,
        submission_id=str(result_payload.get("submission_id") or "") or None,
        task_id=str(result_payload.get("task_id") or "") or None,
        status=str(result_payload.get("status") or "") or None,
        provider=str(final_override_params.get("provider") or final_override_params.get("source_mode") or "source_library"),
        fallback={
            "enabled": "unknown",
            "used": "unknown",
            "reason": "source_library_terminal_output_does_not_report_fallback_usage",
        },
        known_limitations=["source_library_terminal_output_has_no_search_index_timestamp"],
    )
    if submission and registry_key:
        _complete_ingest_submission(registry_key=registry_key, response_payload=result_payload)
    return {"mode": "source_library_item", "result": result_payload}


@router.post("/source-library/run", response_model=IngestJsonEnvelope)
def ingest_source_library_run(payload: SourceLibraryRunPayload) -> IngestJsonObject | JSONResponse:
    """Run source-library item(s) with unified item-style batch support."""
    project_key = _require_project_key(payload.project_key)
    if payload.items:
        if payload.item_key or payload.handler_key:
            _raise_invalid_input(
                "When items is provided, top-level item_key/handler_key must be empty.",
                details={"field": "items"},
            )
        entries: list[SourceLibraryRunItem] = []
        for index, raw_entry in enumerate(payload.items):
            if not _is_object_dict(raw_entry):
                _raise_invalid_input(
                    "items must be an array of objects.",
                    details={"field": "items", "index": index},
                )
            try:
                entries.append(SourceLibraryRunItem.model_validate(raw_entry))
            except ValidationError as exc:
                _raise_invalid_input(
                    "items contains an invalid entry.",
                    details={"field": "items", "index": index, "reason": str(exc)},
                )
    else:
        entries = [
            SourceLibraryRunItem(
                item_key=payload.item_key,
                handler_key=payload.handler_key,
                idempotency_key=payload.idempotency_key,
                async_mode=payload.async_mode,
                source_mode=payload.source_mode,
                query_terms=payload.query_terms,
                urls=payload.urls,
                max_items=payload.max_items,
                provider=payload.provider,
                language=payload.language,
                scope=payload.scope,
                platforms=payload.platforms,
                override_params=payload.override_params,
            )
        ]

    try:
        results: list[IngestJsonObject] = []
        for idx, entry in enumerate(entries):
            present_fields = entry.model_fields_set
            entry_idempotency_key = (
                entry.idempotency_key
                if "idempotency_key" in present_fields
                else payload.idempotency_key
            )
            entry_source_mode = (
                entry.source_mode
                if "source_mode" in present_fields
                else payload.source_mode
            )
            entry_query_terms = (
                entry.query_terms
                if "query_terms" in present_fields
                else payload.query_terms
            )
            entry_urls = entry.urls if "urls" in present_fields else payload.urls
            entry_max_items = (
                entry.max_items
                if "max_items" in present_fields
                else payload.max_items
            )
            entry_provider = (
                entry.provider
                if "provider" in present_fields
                else payload.provider
            )
            entry_language = (
                entry.language
                if "language" in present_fields
                else payload.language
            )
            entry_scope = entry.scope if "scope" in present_fields else payload.scope
            entry_platforms = (
                entry.platforms
                if "platforms" in present_fields
                else payload.platforms
            )
            entry_async_mode = (
                entry.async_mode
                if "async_mode" in present_fields
                else payload.async_mode
            )
            entry_override_params = (
                entry.override_params
                if "override_params" in present_fields
                else payload.override_params
            )
            item_result = _run_single_source_library_entry(
                project_key=project_key,
                item_key=str(entry.item_key or "").strip(),
                handler_key=str(entry.handler_key or "").strip(),
                idempotency_key=str(entry_idempotency_key or "").strip() or None,
                source_mode=str(entry_source_mode or "").strip(),
                query_terms=entry_query_terms,
                urls=entry_urls,
                max_items=entry_max_items,
                provider=str(entry_provider or "").strip() or None,
                language=str(entry_language or "").strip() or None,
                scope=str(entry_scope or "").strip() or None,
                platforms=entry_platforms,
                async_mode=entry_async_mode,
                override_params=entry_override_params,
            )
            results.append({"index": idx, **item_result})

        if len(results) == 1:
            return success_response(results[0]["result"])

        queued = 0
        for item in results:
            result_payload = _optional_json_object(item.get("result"), path="source_library.batch.result")
            if result_payload and result_payload.get("task_id"):
                queued += 1
            raw_tasks = result_payload.get("tasks") if result_payload else None
            if _is_object_list(raw_tasks):
                queued += len(raw_tasks)
        return success_response(
            {
                "batch": True,
                "count": len(results),
                "queued": queued,
                "items": results,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/source-library/sync", response_model=IngestJsonEnvelope)
def ingest_source_library_sync(payload: SourceLibrarySyncPayload) -> IngestJsonObject | JSONResponse:
    """Sync shared source library from files to DB. Entry point for ingest flow."""
    try:
        from ..services.source_library import sync_shared_library_from_files
        result = _json_object(sync_shared_library_from_files(), path="source_library.sync")
        return _json_object(success_response({"ok": True, **result}), path="source_library.sync_response")
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.get("/news-resources", response_model=IngestJsonEnvelope)
def list_news_resources(
    project_key: str | None = Query(default=None),
    scope: str = Query(default="effective", description="shared | project | effective"),
) -> IngestJsonObject:
    """List available news ingest resources for the project. Effective = shared + project merged."""
    pk = _require_project_key(project_key)
    if scope not in ("shared", "project", "effective"):
        scope = "effective"
    customization = get_project_customization(pk)
    shared = customization.get_shared_news_resource_handlers()
    project_handlers = customization.get_news_resource_handlers()
    items: list[IngestJsonObject] = []
    if scope == "shared":
        for rid in shared:
            items.append({"resource_id": rid, "name": _resource_display_name(rid), "scope": "shared"})
    elif scope == "project":
        for rid in project_handlers:
            items.append({"resource_id": rid, "name": _resource_display_name(rid), "scope": "project"})
    else:
        merged: dict[str, IngestJsonObject] = {}
        for rid in shared:
            merged[rid] = {"resource_id": rid, "name": _resource_display_name(rid), "scope": "shared"}
        for rid in project_handlers:
            merged[rid] = {"resource_id": rid, "name": _resource_display_name(rid), "scope": "project"}
        items = list(merged.values())
    return success_response({"items": items, "scope": scope})


@router.post("/news/resource/{resource_id}", response_model=IngestJsonEnvelope)
def ingest_news_resource(resource_id: str, payload: NewsRequest) -> IngestJsonObject | JSONResponse:
    """Generic project news resource entrypoint."""
    return _dispatch_news_resource(resource_id, payload)


@router.post("/subprojects/{subproject_key}/news/{resource_id}", response_model=IngestJsonEnvelope)
def ingest_subproject_news_resource(
    subproject_key: str,
    resource_id: str,
    payload: NewsRequest,
) -> IngestJsonObject | JSONResponse:
    """Subproject-scoped news resource entrypoint."""
    route_project_key = (subproject_key or "").strip()
    if not route_project_key:
        _raise_invalid_input(
            "subproject_key is required",
            details={"field": "subproject_key", "value": subproject_key},
        )
    body_project_key = (payload.project_key or "").strip()
    if body_project_key and body_project_key != route_project_key:
        _raise_invalid_input(
            "project_key in body must match subproject_key in path",
            details={"project_key": body_project_key, "subproject_key": route_project_key},
        )
    scoped_payload = payload.model_copy(update={"project_key": route_project_key})
    return _dispatch_news_resource(resource_id, scoped_payload)


@router.post("/social/reddit", response_model=IngestJsonEnvelope)
def ingest_reddit(payload: RedditRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_reddit.delay(payload.subreddit, payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_reddit"),
                async_mode=True,
                params={"subreddit": payload.subreddit, "limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            from ..services.ingest.news import collect_reddit_discussions
            return _json_object(
                success_response(_json_object(
                    collect_reddit_discussions(subreddit=payload.subreddit, limit=payload.limit),
                    path="ingest.reddit.result",
                )),
                path="ingest.reddit.response",
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/reports/weekly", response_model=IngestJsonEnvelope)
def ingest_weekly_reports(payload: NewsRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_weekly_reports.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_weekly_reports"),
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            return success_response(
                _report_ingest_module().collect_weekly_market_reports(limit=payload.limit)
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/reports/monthly", response_model=IngestJsonEnvelope)
def ingest_monthly_reports(payload: NewsRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_monthly_reports.delay(payload.limit, project_key)
        return success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_monthly_reports"),
                async_mode=True,
                params={"limit": payload.limit},
            )
        )
    try:
        with bind_project(project_key):
            return success_response(
                _report_ingest_module().collect_monthly_financial_reports(limit=payload.limit)
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


class DataApiRequest(BaseModel):
    query_terms: list[str] | None = Field(default=None, description="统一查询词列表（推荐）")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词列表")
    platforms: list[str] = Field(default=["reddit"], description="平台列表（目前支持reddit）")
    max_items: int | None = Field(default=None, ge=1, le=100, description="统一字段：每个查询词的结果数量限制")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段：每个关键词的结果数量限制")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    enable_subreddit_discovery: bool = Field(default=True, description="是否启用子论坛发现功能（自动发现相关子论坛）")
    base_subreddits: list[str] | None = Field(default=None, description="基础子论坛列表（如果为None，使用默认列表）")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


class PolicyRegulationRequest(BaseModel):
    query_terms: list[str] | None = Field(default=None, description="统一查询词列表（推荐）")
    keywords: list[str] | None = Field(default=None, description="兼容字段：搜索关键词列表")
    max_items: int | None = Field(default=None, ge=1, le=100, description="统一字段：每个查询词的结果数量限制")
    limit: int | None = Field(default=None, ge=1, le=100, description="兼容字段：每个关键词的结果数量限制")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否异步执行")
    project_key: str | None = Field(default=None, description="项目标识")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    language: str | None = Field(default=None, description="语言 en/zh")
    provider: str | None = Field(default=None, description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")
    topic_focus: str | None = Field(default=None, description="专题焦点 company/product/operation（可选）")


class GraphStructuredSelectedNode(BaseModel):
    type: str = Field(..., description="节点类型")
    id: str | None = Field(default=None, description="兼容字段：节点ID")
    entry_id: str | None = Field(default=None, description="节点入口ID（优先）")
    label: str = Field(..., description="节点标签")
    topic_focus: str | None = Field(default=None, description="可选专题焦点 company/product/operation/general")


class GraphStructuredSelectedEdge(BaseModel):
    source_entry_id: str | None = Field(default=None, description="边起点 entry_id（可选）")
    target_entry_id: str | None = Field(default=None, description="边终点 entry_id（可选）")
    relation: str | None = Field(default=None, description="关系类型（可选）")
    label: str | None = Field(default=None, description="关系标签（可选）")


class GraphStructuredDashboardParams(BaseModel):
    language: str | None = Field(default="en", description="语言 en/zh")
    provider: str | None = Field(default="auto", description="搜索服务 serper/google/serpstack/serpapi/ddg/auto")
    max_items: int | None = Field(default=20, ge=1, le=100, description="每批每关键词结果数")
    start_offset: int | None = Field(default=None, ge=1, le=91, description="起始偏移(1=第1条,11=第2页)")
    days_back: int | None = Field(default=None, ge=1, le=365, description="仅搜最近N天")
    enable_extraction: bool = Field(default=True, description="是否启用LLM结构化提取")
    async_mode: bool = Field(default=False, description="是否异步执行")
    platforms: list[str] = Field(default=["reddit"], description="数据源平台列表")
    enable_subreddit_discovery: bool = Field(default=True, description="是否启用子论坛发现")
    base_subreddits: list[str] | None = Field(default=None, description="基础子论坛列表")
    source_item_keys: list[str] = Field(default_factory=list, description="来源库 item_key 列表（可选）")
    project_key: str | None = Field(default=None, description="项目标识")


class GraphStructuredSearchRequest(BaseModel):
    selected_nodes: list[GraphStructuredSelectedNode] = Field(default_factory=list, description="图谱选中节点")
    selected_edges: list[GraphStructuredSelectedEdge] = Field(default_factory=list, description="图谱选中边（可选）")
    dashboard: GraphStructuredDashboardParams = Field(default_factory=GraphStructuredDashboardParams, description="采集面板参数")
    llm_assist: bool = Field(default=False, description="是否使用 LLM 扩展关键词")
    flow_type: str = Field(default="collect", description="执行流类型")
    intent_mode: Literal["keyword", "keyword_llm"] | None = Field(default=None, description="意图模式（未传时兼容 llm_assist）")


class _GroupedIntent(TypedDict):
    entry_id: str
    intent: str
    batch_type: str
    topic_focus: str | None
    terms: list[str]


_SOCIAL_NODE_TYPES = {"post", "keyword", "topic", "sentimenttag", "user", "subreddit", "social"}
_MARKET_NODE_TYPES = {"market", "marketdata", "segment", "company", "product", "operation"}
_POLICY_NODE_TYPES = {"policy", "policytype", "keypoint"}
_SHARED_NODE_TYPES = {"entity", "state"}
_COMPANY_HINTS = ("company", "enterprise", "organization", "brand", "vendor", "supplier", "corp", "inc", "公司", "企业", "品牌", "厂商", "供应商")
_PRODUCT_HINTS = ("product", "item", "sku", "model", "segment", "game", "产品", "商品", "品类", "型号", "游戏")
_OPERATION_HINTS = ("operation", "operations", "channel", "sales", "logistics", "retail", "market", "region", "state", "运营", "渠道", "销售", "物流", "门店", "市场", "地区", "州")


def _normalize_graph_label(node: GraphStructuredSelectedNode) -> str:
    label = str(node.label or "").strip()
    if label:
        return label
    nid = _entry_id_of(node)
    if nid:
        return nid
    return str(node.type or "").strip()


def _entry_id_of(node: GraphStructuredSelectedNode) -> str:
    entry_id = str(node.entry_id or "").strip()
    if entry_id:
        return entry_id
    return str(node.id or "").strip()


def _classify_node_batch_types(node: GraphStructuredSelectedNode) -> list[str]:
    nt = str(node.type or "").strip().lower()
    if nt in _POLICY_NODE_TYPES:
        return ["policy"]
    if nt in _SOCIAL_NODE_TYPES:
        return ["social"]
    if nt in _MARKET_NODE_TYPES:
        return ["market"]
    if nt in _SHARED_NODE_TYPES:
        return ["policy", "market"]
    return ["market"]


def _infer_market_topic_focus(node: GraphStructuredSelectedNode) -> str:
    explicit = str(node.topic_focus or "").strip().lower()
    if explicit in {"company", "product", "operation", "general"}:
        return explicit
    text = f"{node.type} {node.label}".lower()
    if any(h in text for h in _COMPANY_HINTS):
        return "company"
    if any(h in text for h in _PRODUCT_HINTS):
        return "product"
    if any(h in text for h in _OPERATION_HINTS):
        return "operation"
    return "general"


def _unique_terms(terms: list[str]) -> list[str]:
    return list(dict.fromkeys([str(t).strip() for t in terms if str(t).strip()]))


def _normalize_batch_token(value: str, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    out = "".join(ch if (ch.isalnum() or ch in {"-", "_"}) else "_" for ch in text)
    out = out.strip("_")
    return out or fallback


def _resolve_intent_mode(payload: GraphStructuredSearchRequest) -> Literal["keyword", "keyword_llm"]:
    mode = str(payload.intent_mode or "").strip().lower()
    if mode == "keyword":
        return "keyword"
    if mode == "keyword_llm":
        return "keyword_llm"
    return "keyword_llm" if payload.llm_assist else "keyword"


def _collect_intents_for_node(node: GraphStructuredSelectedNode) -> list[dict[str, str]]:
    intents: list[dict[str, str]] = []
    for batch_type in _classify_node_batch_types(node):
        if batch_type == "market":
            focus = _infer_market_topic_focus(node)
            intents.append(
                {
                    "batch_type": "market",
                    "intent": f"market_{focus}",
                    "topic_focus": focus,
                }
            )
            continue
        intents.append({"batch_type": batch_type, "intent": batch_type})
    return intents


def _run_policy_batch(
    *,
    project_key: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str = "policy",
) -> IngestJsonObject:
    terms = _unique_terms(query_terms)
    topic_meta: IngestJsonObject = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    if dashboard.async_mode:
        task: object = _tasks_module().task_collect_policy_regulation.delay(
            terms,
            max_items,
            dashboard.enable_extraction,
            project_key,
            dashboard.start_offset,
            dashboard.days_back,
            dashboard.language,
            dashboard.provider,
        )
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "policy",
            "query_terms": terms,
            "task_id": _task_result_id(task, task_name="task_collect_policy_regulation"),
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        from ..services.collect_runtime import collect_request_from_policy_api, run_collect

        req = collect_request_from_policy_api(
            query_terms=terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=dashboard.enable_extraction,
            start_offset=dashboard.start_offset,
            days_back=dashboard.days_back,
            language=dashboard.language or "en",
            provider=dashboard.provider or "auto",
        )
        cr = run_collect(req)
        raw = _optional_json_object(cr.meta.get("raw"), path="collect.policy.meta.raw") or {
            "inserted": cr.inserted,
            "updated": cr.updated,
            "skipped": cr.skipped,
            "display_meta": cr.display_meta,
        }
        if topic_meta:
            raw["topic_meta"] = topic_meta
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "policy",
            "query_terms": terms,
            "async_mode": False,
            "result": raw,
        }


def _run_data_api_batch(
    *,
    project_key: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str = "data_api",
) -> IngestJsonObject:
    terms = _unique_terms(query_terms)
    topic_meta: IngestJsonObject = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    if dashboard.async_mode:
        task: object = _tasks_module().task_collect_data_api.delay(
            terms,
            dashboard.platforms,
            max_items,
            dashboard.enable_extraction,
            dashboard.enable_subreddit_discovery,
            dashboard.base_subreddits,
            project_key,
        )
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "data_api",
            "query_terms": terms,
            "platforms": dashboard.platforms,
            "task_id": _task_result_id(task, task_name="task_collect_data_api"),
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        result: IngestJsonObject = dict(_social_ingest_app().collect_data_api(
            keywords=terms,
            platforms=dashboard.platforms,
            limit=max_items,
            enable_extraction=dashboard.enable_extraction,
            enable_subreddit_discovery=dashboard.enable_subreddit_discovery,
            base_subreddits=dashboard.base_subreddits,
        ), path="ingest.data_api.batch.result")
        if topic_meta:
            result.setdefault("topic_meta", topic_meta)
        return {
            "batch_id": batch_id,
            "batch_name": batch_id,
            "type": "data_api",
            "query_terms": terms,
            "platforms": dashboard.platforms,
            "async_mode": False,
            "result": result,
        }


def _run_market_batch(
    *,
    project_key: str,
    query_terms: list[str],
    topic_focus: str,
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str | None = None,
) -> IngestJsonObject:
    terms = _unique_terms(query_terms)
    topic_meta: IngestJsonObject = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=topic_focus,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    final_batch_id = batch_id or f"market:{topic_focus}"
    if dashboard.async_mode:
        task_id = _dispatch_market_collect_async(
            query_terms=terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=dashboard.enable_extraction,
            start_offset=dashboard.start_offset,
            days_back=dashboard.days_back,
            language=dashboard.language,
            provider=dashboard.provider,
            consumer="ingest.graph_structured.market_batch",
        )
        return {
            "batch_id": final_batch_id,
            "batch_name": final_batch_id,
            "type": "market",
            "topic_focus": topic_focus,
            "query_terms": terms,
            "task_id": task_id,
            "async_mode": True,
            **({"topic_meta": topic_meta} if topic_meta else {}),
        }

    with bind_project(project_key):
        from ..services.collect_runtime import collect_request_from_market_api, run_collect

        req = collect_request_from_market_api(
            query_terms=terms,
            max_items=max_items,
            project_key=project_key,
            enable_extraction=dashboard.enable_extraction,
            start_offset=dashboard.start_offset,
            days_back=dashboard.days_back,
            language=dashboard.language or "en",
            provider=dashboard.provider or "auto",
        )
        cr = run_collect(req)
        raw = _optional_json_object(cr.meta.get("raw"), path="collect.market_batch.meta.raw") or {
            "inserted": cr.inserted,
            "updated": cr.updated,
            "skipped": cr.skipped,
            "display_meta": cr.display_meta,
        }
        if topic_meta:
            raw["topic_meta"] = topic_meta
        return {
            "batch_id": final_batch_id,
            "batch_name": final_batch_id,
            "type": "market",
            "topic_focus": topic_focus,
            "query_terms": terms,
            "async_mode": False,
            "result": raw,
        }


def _run_source_collect_batch(
    *,
    project_key: str,
    entry_id: str,
    intent: str,
    query_terms: list[str],
    dashboard: GraphStructuredDashboardParams,
    llm_assist: bool,
    batch_id: str,
    source_item_key: str | None = None,
) -> IngestJsonObject:
    terms = _unique_terms(query_terms)
    topic_meta: IngestJsonObject = {}
    if llm_assist:
        terms, topic_meta = _expand_query_terms_with_topic_focus(
            terms,
            topic_focus=None,
            language=dashboard.language or "en",
        )
    max_items = _normalize_max_items(dashboard.max_items, None)
    normalized_entry_id = _normalize_batch_token(entry_id, fallback="unknown")
    normalized_intent = _normalize_batch_token(intent, fallback="general")
    selected_item_key = str(source_item_key or "").strip()
    item_key = selected_item_key
    from ..services.collect_runtime import run_source_library_item_compat

    with bind_project(project_key):
        existed_before = True
        auto_generated_item = False
        if not item_key:
            # Append a short hash to avoid collisions after token normalization.
            fingerprint = hashlib.sha1(
                f"{entry_id}::{intent}".encode("utf-8"),
                usedforsecurity=False,
            ).hexdigest()[:8]
            item_key = f"graph::{normalized_entry_id}::{normalized_intent}::{fingerprint}"
            from ..services.source_library import list_effective_items
            from ..services.source_library.item_writer import (
                SourceLibraryItemUpsertPayload,
                upsert_project_item,
            )
            existing = list_effective_items(scope="effective", project_key=project_key)
            existed_before = any(
                str(item.get("item_key") or "").strip() == item_key
                for item in existing
            )
            generated_params: dict[str, JsonValue] = {
                "query_terms": [term for term in terms],
                "keywords": [term for term in terms],
                "limit": max_items,
                "scope": "effective",
            }
            upsert_project_item(
                payload=SourceLibraryItemUpsertPayload(
                    item_key=item_key,
                    name=f"Graph Source {normalized_entry_id} {normalized_intent}",
                    channel_key="url_pool",
                    description="Graph structured-search generated source_collect item.",
                    params=generated_params,
                    tags=["graph_structured", normalized_entry_id, normalized_intent],
                    enabled=True,
                    extra={
                        "generated_by": "graph_structured_search",
                        "entry_id": normalized_entry_id,
                        "intent": normalized_intent,
                        "flow_type": "source_collect",
                    },
                ),
                project_key=project_key,
            )
            auto_generated_item = True
        override_params: IngestJsonObject = {
            "query_terms": terms,
            "keywords": terms,
            "limit": max_items,
            "scope": "effective",
            "provider": dashboard.provider or "auto",
            "language": dashboard.language or "en",
            "enable_extraction": dashboard.enable_extraction,
        }
        if dashboard.async_mode:
            task_id = _dispatch_source_library_item_async(
                item_key=item_key,
                project_key=project_key,
                override_params=override_params,
                consumer="ingest.graph_structured.source_collect",
            )
            return {
                "batch_id": batch_id,
                "batch_name": batch_id,
                "type": "source_collect",
                "entry_id": entry_id,
                "intent": intent,
                "item_key": item_key,
                "query_terms": terms,
                "task_id": task_id,
                "async_mode": True,
                "result": {
                    "sources_inserted": 0,
                    "sources_updated": 0,
                    "skipped": 0,
                    "errors": [],
                    "item_inserted": 0 if (existed_before or not auto_generated_item) else 1,
                    "item_updated": 1 if (existed_before and auto_generated_item) else 0,
                    "bootstrap_required": False,
                    "warnings": [],
                },
                **({"topic_meta": topic_meta} if topic_meta else {}),
            }

        run_result = run_source_library_item_compat(
            item_key=item_key,
            project_key=project_key,
            override_params=source_library_compat_response(override_params),
        )

    parsed_run_result = _json_object(run_result, path="source_library.graph_collect.result")
    authority_output = _optional_json_object(
        parsed_run_result.get("authority_output"),
        path="source_library.graph_collect.authority_output",
    ) or {}
    authority_summary = _optional_json_object(
        authority_output.get("summary"),
        path="source_library.graph_collect.authority_summary",
    ) or {}
    write_effects = _optional_json_object(
        authority_summary.get("write_effects"),
        path="source_library.graph_collect.write_effects",
    ) or {}
    raw_errors = write_effects.get("errors")
    errors = raw_errors if _is_object_list(raw_errors) else []
    sources_inserted = _json_int(write_effects.get("inserted"), path="source_library.write_effects.inserted")
    sources_updated = _json_int(write_effects.get("updated"), path="source_library.write_effects.updated")
    skipped = _json_int(write_effects.get("skipped"), path="source_library.write_effects.skipped")
    has_errors = any(str(e or "").strip() for e in errors)
    bootstrap_required = bool(authority_summary.get("bootstrap_required")) if authority_summary else (sources_inserted + sources_updated == 0 and not has_errors)
    warnings: list[str] = []
    if bootstrap_required:
        warnings.append("No source candidates produced. Bootstrap URL pool or source templates, then retry source_collect.")
    return {
        "batch_id": batch_id,
        "batch_name": batch_id,
        "type": "source_collect",
        "entry_id": entry_id,
        "intent": intent,
        "item_key": item_key,
        "query_terms": terms,
        "async_mode": False,
        "result": {
            "sources_inserted": sources_inserted,
            "sources_updated": sources_updated,
            "skipped": skipped,
            "errors": [str(error or "") for error in errors],
            "item_inserted": 0 if (existed_before or not auto_generated_item) else 1,
            "item_updated": 1 if (existed_before and auto_generated_item) else 0,
            "bootstrap_required": bootstrap_required,
            "warnings": warnings,
        },
        **({"topic_meta": topic_meta} if topic_meta else {}),
    }


@router.post("/data-api", response_model=IngestJsonEnvelope)
def ingest_data_api(payload: DataApiRequest) -> IngestJsonObject | JSONResponse:
    """Run data API collection by keywords."""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language="en"
    )
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_data_api.delay(
            query_terms,
            payload.platforms,
            max_items,
            payload.enable_extraction,
            payload.enable_subreddit_discovery,
            payload.base_subreddits,
            project_key,
        )
        return _json_object(success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_data_api"),
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items, "platforms": payload.platforms, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
            )
        ), path="ingest.data_api.async_response")
    try:
        with bind_project(project_key):
            result: IngestJsonObject = dict(_social_ingest_app().collect_data_api(
                keywords=query_terms,
                platforms=payload.platforms,
                limit=max_items,
                enable_extraction=payload.enable_extraction,
                enable_subreddit_discovery=payload.enable_subreddit_discovery,
                base_subreddits=payload.base_subreddits,
            ), path="ingest.data_api.result")
            if topic_meta:
                result.setdefault("topic_focus", topic_meta.get("topic_focus"))
                result.setdefault("topic_hints", topic_meta.get("topic_hints") or [])
                result.setdefault("topic_search_keywords", topic_meta.get("topic_search_keywords") or [])
            return ok(result)
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/graph/structured-search", response_model=IngestJsonEnvelope)
def ingest_graph_structured_search(payload: GraphStructuredSearchRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.dashboard.project_key)
    if not payload.selected_nodes:
        _raise_invalid_input(
            "selected_nodes is required and cannot be empty.",
            details={"field": "selected_nodes", "value": []},
        )
    flow_type = str(payload.flow_type or "collect").strip().lower()
    if flow_type not in {"collect", "source_collect"}:
        _raise_invalid_input(
            "flow_type must be collect or source_collect.",
            details={"field": "flow_type", "value": flow_type},
        )
    intent_mode = _resolve_intent_mode(payload)
    llm_assist = intent_mode == "keyword_llm"
    source_item_keys = _unique_terms(payload.dashboard.source_item_keys or [])
    selected_edge_count = len(payload.selected_edges or [])
    logger.info(
        "graph structured search accepted project=%s flow_type=%s intent_mode=%s nodes=%s edges=%s",
        project_key,
        flow_type,
        intent_mode,
        len(payload.selected_nodes),
        selected_edge_count,
    )

    grouped_intents: dict[tuple[str, str, str], _GroupedIntent] = {}
    for node in payload.selected_nodes:
        entry_id = _entry_id_of(node)
        if not entry_id:
            continue
        label = _normalize_graph_label(node)
        if not label:
            continue
        for spec in _collect_intents_for_node(node):
            key = (entry_id, str(spec.get("intent") or "").strip(), str(spec.get("batch_type") or "").strip())
            current = grouped_intents.get(key)
            if current is None:
                grouped_intents[key] = {
                    "entry_id": entry_id,
                    "intent": key[1],
                    "batch_type": key[2],
                    "topic_focus": spec.get("topic_focus"),
                    "terms": [label],
                }
            else:
                current["terms"] = _unique_terms([*current["terms"], label])

    if not grouped_intents:
        _raise_invalid_input(
            "selected_nodes does not contain usable labels.",
            details={"field": "selected_nodes"},
        )

    batches: list[IngestJsonObject] = []
    async_dispatchers: list[Callable[[], IngestJsonObject]] = []
    batch_seq: dict[tuple[str, str, str], int] = {}
    try:
        ordered_specs = sorted(
            grouped_intents.values(),
            key=lambda spec: (spec["entry_id"], spec["intent"], spec["batch_type"]),
        )
        for spec in ordered_specs:
            entry_id = spec["entry_id"].strip()
            intent = spec["intent"].strip() or "general"
            batch_type = spec["batch_type"].strip()
            terms = _unique_terms(spec["terms"])
            if not entry_id or not terms:
                continue
            key = (flow_type, entry_id, intent)
            batch_seq[key] = batch_seq.get(key, 0) + 1
            batch_id = f"{_normalize_batch_token(flow_type, fallback='collect')}:{_normalize_batch_token(entry_id, fallback='unknown')}:{_normalize_batch_token(intent, fallback='general')}:b{batch_seq[key]}"
            if flow_type == "source_collect":
                if source_item_keys:
                    for idx, source_item_key in enumerate(source_item_keys):
                        call = partial(
                            _run_source_collect_batch,
                            project_key=project_key,
                            entry_id=entry_id,
                            intent=intent,
                            query_terms=terms,
                            dashboard=payload.dashboard,
                            llm_assist=llm_assist,
                            batch_id=f"{batch_id}:src{idx + 1}",
                            source_item_key=source_item_key,
                        )
                        if payload.dashboard.async_mode:
                            async_dispatchers.append(call)
                        else:
                            batches.append(call())
                else:
                    call = partial(
                        _run_source_collect_batch,
                        project_key=project_key,
                        entry_id=entry_id,
                        intent=intent,
                        query_terms=terms,
                        dashboard=payload.dashboard,
                        llm_assist=llm_assist,
                        batch_id=batch_id,
                    )
                    if payload.dashboard.async_mode:
                        async_dispatchers.append(call)
                    else:
                        batches.append(call())
                continue
            if batch_type == "policy":
                call = partial(
                    _run_policy_batch,
                    project_key=project_key,
                    query_terms=terms,
                    dashboard=payload.dashboard,
                    llm_assist=llm_assist,
                    batch_id=batch_id,
                )
                if payload.dashboard.async_mode:
                    async_dispatchers.append(call)
                else:
                    batches.append(call())
            elif batch_type == "social":
                call = partial(
                    _run_data_api_batch,
                    project_key=project_key,
                    query_terms=terms,
                    dashboard=payload.dashboard,
                    llm_assist=llm_assist,
                    batch_id=batch_id,
                )
                if payload.dashboard.async_mode:
                    async_dispatchers.append(call)
                else:
                    batches.append(call())
            elif batch_type == "market":
                call = partial(
                    _run_market_batch,
                    project_key=project_key,
                    query_terms=terms,
                    topic_focus=str(spec.get("topic_focus") or "general"),
                    dashboard=payload.dashboard,
                    llm_assist=llm_assist,
                    batch_id=batch_id,
                )
                if payload.dashboard.async_mode:
                    async_dispatchers.append(call)
                else:
                    batches.append(call())
        if async_dispatchers:
            if len(async_dispatchers) == 1:
                batches.append(async_dispatchers[0]())
            else:
                worker_count = max(
                    1,
                    min(
                        int(settings.graph_structured_async_dispatch_workers or 4),
                        len(async_dispatchers),
                    ),
                )
                ordered_results: list[IngestJsonObject | None] = [None] * len(async_dispatchers)
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    future_to_index = {
                        executor.submit(dispatcher): idx for idx, dispatcher in enumerate(async_dispatchers)
                    }
                    for future in as_completed(future_to_index):
                        ordered_results[future_to_index[future]] = future.result()
                batches.extend([result for result in ordered_results if result is not None])
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)

    type_counts: dict[str, int] = {"policy": 0, "data_api": 0, "market": 0, "source_collect": 0}
    for batch in batches:
        bt = str(batch.get("type") or "").strip().lower()
        if bt in type_counts:
            type_counts[bt] += 1

    summary: IngestJsonObject = {
        "selected_node_count": len(payload.selected_nodes),
        "selected_edge_count": selected_edge_count,
        "batch_count": len(batches),
        "async_mode": payload.dashboard.async_mode,
        "llm_assist": llm_assist,
        "flow_type": flow_type,
        "intent_mode": intent_mode,
        "types": {
            "policy": type_counts["policy"],
            "data_api": type_counts["data_api"],
            "social": type_counts["data_api"],
            "market": type_counts["market"],
            "source_collect": type_counts["source_collect"],
        },
        "source_item_key_count": len(source_item_keys),
    }
    accepted = len(batches)
    queued = sum(1 for b in batches if b.get("task_id"))
    failed = 0
    for batch in batches:
        result = _optional_json_object(batch.get("result"), path="ingest.graph.batch.result")
        if result is None:
            continue
        raw_errors = result.get("errors")
        if _is_object_list(raw_errors) and any(str(error or "").strip() for error in raw_errors):
            failed += 1
    summary["accepted"] = accepted
    summary["queued"] = queued
    summary["failed"] = failed
    if payload.dashboard.async_mode:
        summary["task_count"] = queued

    selected_edges_meta = [
        {
            "source_entry_id": str(edge.source_entry_id or "").strip() or None,
            "target_entry_id": str(edge.target_entry_id or "").strip() or None,
            "relation": str(edge.relation or "").strip() or None,
            "label": str(edge.label or "").strip() or None,
        }
        for edge in (payload.selected_edges or [])
    ]

    return _json_object(success_response(
        {
            "flow_type": flow_type,
            "intent_mode": intent_mode,
            "batches": batches,
            "summary": summary,
            "meta": {
                "selected_edge_count": selected_edge_count,
                "selected_edges": selected_edges_meta,
                "source_item_keys": source_item_keys,
            },
        }
    ), path="ingest.graph.response")


@router.post("/policy/regulation", response_model=IngestJsonEnvelope)
def ingest_policy_regulation(payload: PolicyRegulationRequest) -> IngestJsonObject | JSONResponse:
    """收集政策法规相关新闻"""
    project_key = _require_project_key(payload.project_key)
    query_terms = _normalize_query_terms(payload.query_terms, payload.keywords)
    query_terms, topic_meta = _expand_query_terms_with_topic_focus(
        query_terms, topic_focus=payload.topic_focus, language=payload.language or "en"
    )
    max_items = _normalize_max_items(payload.max_items, payload.limit)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_policy_regulation.delay(
            query_terms,
            max_items,
            payload.enable_extraction,
            project_key,
            payload.start_offset,
            payload.days_back,
            payload.language,
            payload.provider,
        )
        return _json_object(success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_policy_regulation"),
                async_mode=True,
                params={"query_terms": query_terms, "max_items": max_items, **({"topic_focus": payload.topic_focus} if payload.topic_focus else {})},
            )
        ), path="ingest.policy.async_response")
    try:
        with bind_project(project_key):
            from ..services.collect_runtime import collect_request_from_policy_api, run_collect
            req = collect_request_from_policy_api(
                query_terms=query_terms,
                max_items=max_items,
                project_key=project_key,
                enable_extraction=payload.enable_extraction,
                start_offset=payload.start_offset,
                days_back=payload.days_back,
                language=payload.language or "en",
                provider=payload.provider or "auto",
            )
            cr = run_collect(req)
            raw = _optional_json_object(cr.meta.get("raw"), path="collect.policy.meta.raw") or {
                "inserted": cr.inserted,
                "updated": cr.updated,
                "skipped": cr.skipped,
                "display_meta": cr.display_meta,
            }
            if topic_meta:
                raw["topic_focus"] = topic_meta.get("topic_focus")
                raw["topic_hints"] = topic_meta.get("topic_hints") or []
                raw["topic_search_keywords"] = topic_meta.get("topic_search_keywords") or []
            return _json_object(success_response(raw), path="ingest.policy.response")
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/commodity/metrics", response_model=IngestJsonEnvelope)
def ingest_commodity(payload: CommodityRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task: object = _tasks_module().task_ingest_commodity_metrics.delay(payload.limit, project_key)
        return _json_object(success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_ingest_commodity_metrics"),
                async_mode=True,
                params={"limit": payload.limit},
            )
        ), path="ingest.commodity.async_response")
    try:
        with bind_project(project_key):
            return success_response(
                _commodity_ingest_module().ingest_commodity_metrics(limit=payload.limit)
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)


@router.post("/ecom/prices", response_model=IngestJsonEnvelope)
def ingest_ecom_prices(payload: EcomPriceRequest) -> IngestJsonObject | JSONResponse:
    project_key = _require_project_key(payload.project_key)
    if payload.async_mode:
        task: object = _tasks_module().task_collect_ecom_prices.delay(payload.limit, project_key)
        return _json_object(success_response(
            task_result_response(
                task_id=_task_result_id(task, task_name="task_collect_ecom_prices"),
                async_mode=True,
                params={"limit": payload.limit},
            )
        ), path="ingest.ecom.async_response")
    try:
        with bind_project(project_key):
            from ..services.ingest.ecom import collect_ecom_price_observations
            return _json_object(
                success_response(_json_object(
                    collect_ecom_price_observations(limit=payload.limit),
                    path="ingest.ecom.result",
                )),
                path="ingest.ecom.response",
            )
    except Exception as exc:  # noqa: BLE001
        return _error_500(exc)
