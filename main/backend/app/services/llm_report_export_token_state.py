from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any

from sqlalchemy import or_, select
from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import llm_report_request_failures

from ..models.base import run_with_session_retry
from ..models.llm_report_export_token_state import LlmReportExportTokenState

_LLM_REPORT_EXPORT_TOKEN_STATES: dict[str, dict[str, Any]] = {}
_LLM_REPORT_EXPORT_TOKEN_STATE_LOCK = RLock()
_FAILURE_WITNESS = "test:test_w01_request_failures"
_FAILURE_CONTEXT_KEYS = frozenset(
    {"owner", "operation", "failure_family", "public_exception", "public_message", "witness"}
)


def _request_failure(code: str, message: str, *, operation: str, **details: Any) -> Failure:
    return llm_report_request_failures.fail(
        code,
        message,
        {
            "owner": "llm_report_export_token_state",
            "operation": operation,
            "failure_family": llm_report_request_failures.name,
            "public_exception": "ValueError",
            "public_message": message,
            "witness": _FAILURE_WITNESS,
            **details,
        },
    )


def _raise_request_failure(failure: Failure) -> None:
    context = failure.context or {}
    if not llm_report_request_failures.matches(failure) or _FAILURE_CONTEXT_KEYS - set(context):
        # kit:boundary owner=llm_report_export_token_state.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_request_failures
        raise TypeError("llm report request failure lift context is incomplete or inconsistent")
    # kit:boundary owner=llm_report_export_token_state.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=llm.report.request.failure witness=test:test_w01_request_failures
    raise ValueError(str(context["public_message"]))


def _validate_retention_days(value: Any) -> int | Failure:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return _request_failure(
            "retention_days_invalid",
            "retention_days must be >= 1",
            operation="prune_llm_report_export_token_states",
        )
    if normalized < 1:
        return _request_failure(
            "retention_days_invalid",
            "retention_days must be >= 1",
            operation="prune_llm_report_export_token_states",
        )
    return normalized


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_str_or_none(value: Any, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_length] if max_length else text


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    return {}


def _normalize_record(payload: dict[str, Any], *, used: bool = False, revoked: bool = False) -> dict[str, Any]:
    source = _json_safe_payload(payload)
    now = _utcnow()
    used_at = _parse_datetime(source.get("used_at")) or (now if used else None)
    revoked_at = _parse_datetime(source.get("revoked_at")) or (now if revoked else None)
    last_seen_at = _parse_datetime(source.get("last_seen_at")) or now
    return {
        "contract_version": source.get("contract_version") or "llm_report.export_token_state.v1",
        "record_source": "llm_report_export_token_state",
        "artifact_id": _as_str_or_none(source.get("artifact_id"), max_length=128),
        "actor_id": _as_str_or_none(source.get("actor_id"), max_length=128),
        "project_key": _as_str_or_none(source.get("project_key"), max_length=64),
        "trace_id": _as_str_or_none(source.get("trace_id"), max_length=128),
        "request_id": _as_str_or_none(source.get("request_id"), max_length=128),
        "job_id": _as_int_or_none(source.get("job_id")),
        "used_at": _isoformat(used_at),
        "revoked_at": _isoformat(revoked_at),
        "revoke_reason": _as_str_or_none(source.get("revoke_reason") or source.get("reason")),
        "last_seen_at": _isoformat(last_seen_at),
        "payload": source,
    }


def _normalize_claim_record(payload: dict[str, Any]) -> dict[str, Any]:
    source = _json_safe_payload(payload)
    normalized = _normalize_record(
        {
            **source,
            "used_at": None,
            "revoked_at": None,
            "last_seen_at": source.get("last_seen_at"),
        }
    )
    normalized["payload"] = source
    return normalized


def _merge_memory_record(current: dict[str, Any] | None, update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current or {})
    payload = {
        **_json_safe_payload(merged.get("payload")),
        **_json_safe_payload(update.get("payload")),
    }
    for key, value in update.items():
        if value is not None:
            merged[key] = value
    if merged.get("used_at") and update.get("used_at"):
        merged["used_at"] = current.get("used_at") if current and current.get("used_at") else update.get("used_at")
    if merged.get("revoked_at") and update.get("revoked_at"):
        merged["revoked_at"] = current.get("revoked_at") if current and current.get("revoked_at") else update.get("revoked_at")
    merged["payload"] = payload
    merged["contract_version"] = "llm_report.export_token_state.v1"
    merged["record_source"] = "llm_report_export_token_state"
    return merged


def _remember_state(record: dict[str, Any]) -> dict[str, Any]:
    artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    if not artifact_id:
        return dict(record)
    with _LLM_REPORT_EXPORT_TOKEN_STATE_LOCK:
        merged = _merge_memory_record(_LLM_REPORT_EXPORT_TOKEN_STATES.get(artifact_id), record)
        _LLM_REPORT_EXPORT_TOKEN_STATES[artifact_id] = dict(merged)
        return dict(merged)


def _replace_memory_state(record: dict[str, Any]) -> dict[str, Any]:
    artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    if not artifact_id:
        return dict(record)
    with _LLM_REPORT_EXPORT_TOKEN_STATE_LOCK:
        _LLM_REPORT_EXPORT_TOKEN_STATES[artifact_id] = dict(record)
        return dict(record)


def _is_prunable_token_state_record(record: dict[str, Any], cutoff: datetime) -> bool:
    if not record.get("used_at") and not record.get("revoked_at"):
        return False
    last_seen_at = _parse_datetime(record.get("last_seen_at"))
    return bool(last_seen_at and last_seen_at < cutoff)


def _prune_memory_token_states(cutoff: datetime, *, dry_run: bool) -> tuple[int, int]:
    with _LLM_REPORT_EXPORT_TOKEN_STATE_LOCK:
        artifact_ids = [
            artifact_id
            for artifact_id, record in _LLM_REPORT_EXPORT_TOKEN_STATES.items()
            if _is_prunable_token_state_record(record, cutoff)
        ]
        if dry_run:
            return len(artifact_ids), 0
        for artifact_id in artifact_ids:
            _LLM_REPORT_EXPORT_TOKEN_STATES.pop(artifact_id, None)
        return len(artifact_ids), len(artifact_ids)


def _row_to_record(row: LlmReportExportTokenState) -> dict[str, Any]:
    payload = _json_safe_payload(row.payload)
    return {
        "contract_version": payload.get("contract_version") or "llm_report.export_token_state.v1",
        "record_source": "llm_report_export_token_state",
        "artifact_id": row.artifact_id,
        "actor_id": row.actor_id,
        "project_key": row.project_key,
        "trace_id": row.trace_id,
        "request_id": row.request_id,
        "job_id": row.job_id,
        "used_at": _isoformat(_parse_datetime(row.used_at)),
        "revoked_at": _isoformat(_parse_datetime(row.revoked_at)),
        "revoke_reason": row.revoke_reason,
        "last_seen_at": _isoformat(_parse_datetime(row.last_seen_at)),
        "payload": payload,
        "created_at": _isoformat(_parse_datetime(row.created_at)),
        "updated_at": _isoformat(_parse_datetime(row.updated_at)),
    }


def _apply_record_to_row(row: LlmReportExportTokenState, record: dict[str, Any]) -> None:
    now = _utcnow()
    row.artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128) or row.artifact_id
    row.actor_id = _as_str_or_none(record.get("actor_id"), max_length=128) or row.actor_id
    row.project_key = _as_str_or_none(record.get("project_key"), max_length=64) or row.project_key
    row.trace_id = _as_str_or_none(record.get("trace_id"), max_length=128) or row.trace_id
    row.request_id = _as_str_or_none(record.get("request_id"), max_length=128) or row.request_id
    row.job_id = _as_int_or_none(record.get("job_id")) if record.get("job_id") is not None else row.job_id
    row.used_at = row.used_at or _parse_datetime(record.get("used_at"))
    row.revoked_at = row.revoked_at or _parse_datetime(record.get("revoked_at"))
    row.revoke_reason = _as_str_or_none(record.get("revoke_reason")) or row.revoke_reason
    row.last_seen_at = _parse_datetime(record.get("last_seen_at")) or now
    row.payload = {
        **_json_safe_payload(row.payload),
        **_json_safe_payload(record.get("payload")),
    }
    row.updated_at = now
    if row.created_at is None:
        row.created_at = now


def _load_database_state(artifact_id: str) -> tuple[dict[str, Any] | None, bool]:
    normalized_artifact_id = _as_str_or_none(artifact_id, max_length=128)
    if not normalized_artifact_id:
        return None, False

    def _operation(session):
        row = session.execute(
            select(LlmReportExportTokenState).where(
                LlmReportExportTokenState.artifact_id == normalized_artifact_id
            )
        ).scalar_one_or_none()
        return _row_to_record(row) if row is not None else None

    try:
        return run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_export_token_state",
                "operation": "load_token_state",
                "artifact_id": normalized_artifact_id,
            },
        ), False
    except Exception:  # noqa: BLE001
        return None, True


def _persist_state(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    if not artifact_id:
        return dict(record), False

    def _operation(session):
        row = session.execute(
            select(LlmReportExportTokenState).where(LlmReportExportTokenState.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if row is None:
            row = LlmReportExportTokenState(artifact_id=artifact_id)
            session.add(row)
        _apply_record_to_row(row, record)
        session.flush()
        return _row_to_record(row)

    try:
        persisted = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_export_token_state",
                "operation": "persist_token_state",
                "artifact_id": artifact_id,
            },
        )
        return persisted, False
    except Exception:  # noqa: BLE001
        return dict(record), True


def _prune_database_token_states(cutoff: datetime, *, dry_run: bool) -> tuple[int, int]:
    def _operation(session):
        rows = (
            session.execute(
                select(LlmReportExportTokenState).where(
                    or_(
                        LlmReportExportTokenState.used_at.is_not(None),
                        LlmReportExportTokenState.revoked_at.is_not(None),
                    ),
                    LlmReportExportTokenState.last_seen_at < cutoff,
                )
            )
            .scalars()
            .all()
        )
        if dry_run:
            return len(rows), 0
        for row in rows:
            session.delete(row)
        session.flush()
        return len(rows), len(rows)

    return run_with_session_retry(
        _operation,
        log_context={
            "component": "llm_report_export_token_state",
            "operation": "prune_token_state",
            "cutoff": _isoformat(cutoff),
            "dry_run": dry_run,
        },
    )


def _with_degraded(record: dict[str, Any] | None, degraded: bool) -> dict[str, Any] | None:
    if record is None:
        return None
    if not degraded:
        return dict(record)
    return {
        **record,
        "token_state_store_degraded": True,
        "degraded": True,
        "degraded_reason": "llm_report_export_token_state_db_unavailable",
    }


def _with_claim_status(record: dict[str, Any], *, claimed: bool) -> dict[str, Any]:
    already_used = bool(record.get("used_at")) and not claimed
    revoked = bool(record.get("revoked_at"))
    return {
        **record,
        "claimed": claimed,
        "already_used": already_used,
        "revoked": revoked,
    }


def _claim_memory_state(record: dict[str, Any]) -> dict[str, Any]:
    artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    if not artifact_id:
        return _with_claim_status(dict(record), claimed=False)

    with _LLM_REPORT_EXPORT_TOKEN_STATE_LOCK:
        current = _LLM_REPORT_EXPORT_TOKEN_STATES.get(artifact_id)
        if current and current.get("used_at"):
            merged = _merge_memory_record(current, record)
            _LLM_REPORT_EXPORT_TOKEN_STATES[artifact_id] = dict(merged)
            return _with_claim_status(dict(merged), claimed=False)
        if current and current.get("revoked_at"):
            merged = _merge_memory_record(current, record)
            _LLM_REPORT_EXPORT_TOKEN_STATES[artifact_id] = dict(merged)
            return _with_claim_status(dict(merged), claimed=False)

        now = _utcnow()
        claimed_record = {
            **record,
            "used_at": _isoformat(now),
            "last_seen_at": _isoformat(now),
        }
        merged = _merge_memory_record(current, claimed_record)
        _LLM_REPORT_EXPORT_TOKEN_STATES[artifact_id] = dict(merged)
        return _with_claim_status(dict(merged), claimed=True)


def _claim_database_state(record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    artifact_id = _as_str_or_none(record.get("artifact_id"), max_length=128)
    if not artifact_id:
        return _with_claim_status(dict(record), claimed=False), False

    def _operation(session):
        row = session.execute(
            select(LlmReportExportTokenState)
            .where(LlmReportExportTokenState.artifact_id == artifact_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            row = LlmReportExportTokenState(artifact_id=artifact_id)
            session.add(row)

        if row.used_at:
            _apply_record_to_row(row, record)
            session.flush()
            return _with_claim_status(_row_to_record(row), claimed=False)
        if row.revoked_at:
            _apply_record_to_row(row, record)
            session.flush()
            return _with_claim_status(_row_to_record(row), claimed=False)

        now = _utcnow()
        claim_record = {
            **record,
            "used_at": _isoformat(now),
            "last_seen_at": _isoformat(now),
        }
        _apply_record_to_row(row, claim_record)
        session.flush()
        return _with_claim_status(_row_to_record(row), claimed=True)

    try:
        claimed_record = run_with_session_retry(
            _operation,
            log_context={
                "component": "llm_report_export_token_state",
                "operation": "claim_token_state",
                "artifact_id": artifact_id,
            },
        )
        return claimed_record, False
    except Exception:  # noqa: BLE001
        recovered, recovery_degraded = _load_database_state(artifact_id)
        if recovered and (recovered.get("used_at") or recovered.get("revoked_at")):
            return _with_claim_status(recovered, claimed=False), recovery_degraded
        return _with_claim_status(dict(record), claimed=False), True


def clear_llm_report_export_token_state_memory() -> None:
    with _LLM_REPORT_EXPORT_TOKEN_STATE_LOCK:
        _LLM_REPORT_EXPORT_TOKEN_STATES.clear()


def prune_llm_report_export_token_states(
    retention_days: int,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict:
    normalized_now = _parse_datetime(now) if now is not None else _utcnow()
    retention_outcome = _validate_retention_days(retention_days)
    if isinstance(retention_outcome, Failure):
        _raise_request_failure(retention_outcome)
    normalized_retention_days = retention_outcome
    cutoff = (normalized_now or _utcnow()) - timedelta(days=normalized_retention_days)

    token_state_store_degraded = False
    database_candidate_count = 0
    database_deleted_count = 0
    try:
        database_candidate_count, database_deleted_count = _prune_database_token_states(cutoff, dry_run=dry_run)
    except Exception:  # noqa: BLE001
        token_state_store_degraded = True

    memory_candidate_count, memory_deleted_count = _prune_memory_token_states(cutoff, dry_run=dry_run)
    candidate_count = memory_candidate_count if token_state_store_degraded else database_candidate_count
    deleted_count = memory_deleted_count if token_state_store_degraded else database_deleted_count
    return {
        "contract_version": "llm_report.export_token_state_retention.v1",
        "retention_days": normalized_retention_days,
        "cutoff": _isoformat(cutoff),
        "dry_run": bool(dry_run),
        "candidate_count": candidate_count,
        "deleted_count": deleted_count,
        "database_candidate_count": database_candidate_count,
        "database_deleted_count": database_deleted_count,
        "memory_candidate_count": memory_candidate_count,
        "memory_deleted_count": memory_deleted_count,
        "token_state_store_degraded": token_state_store_degraded,
    }


def mark_llm_report_export_token_used_persistent(payload: dict) -> dict:
    record = _remember_state(_normalize_record(_json_safe_payload(payload), used=True))
    persisted, degraded = _persist_state(record)
    remembered = _remember_state(persisted)
    return _with_degraded(remembered, degraded) or remembered


def revoke_llm_report_export_token_persistent(
    artifact_id: str,
    *,
    actor_id=None,
    reason=None,
    payload=None,
) -> dict:
    source = _json_safe_payload(payload)
    source["artifact_id"] = _as_str_or_none(artifact_id, max_length=128)
    if actor_id is not None:
        source["actor_id"] = actor_id
    if reason is not None:
        source["revoke_reason"] = reason
    record = _remember_state(_normalize_record(source, revoked=True))
    persisted, degraded = _persist_state(record)
    remembered = _remember_state(persisted)
    return _with_degraded(remembered, degraded) or remembered


def claim_llm_report_export_token_use(payload: dict) -> dict:
    record = _normalize_claim_record(_json_safe_payload(payload))
    claimed_record, degraded = _claim_database_state(record)
    if not degraded:
        return _replace_memory_state(claimed_record)

    remembered = _remember_state(claimed_record)
    memory_claim = _claim_memory_state(remembered)
    return _with_degraded(memory_claim, True) or memory_claim


def get_llm_report_export_token_state(artifact_id: str) -> dict | None:
    normalized_artifact_id = _as_str_or_none(artifact_id, max_length=128)
    if not normalized_artifact_id:
        return None
    database_record, database_degraded = _load_database_state(normalized_artifact_id)
    if database_record is not None:
        remembered = _remember_state(database_record)
        return _with_degraded(remembered, database_degraded)
    memory_record = _LLM_REPORT_EXPORT_TOKEN_STATES.get(normalized_artifact_id)
    return _with_degraded(dict(memory_record), database_degraded) if memory_record is not None else None


def is_llm_report_export_token_used(artifact_id: str) -> bool:
    state = get_llm_report_export_token_state(artifact_id)
    return bool(state and state.get("used_at"))


def is_llm_report_export_token_revoked(artifact_id: str) -> bool:
    state = get_llm_report_export_token_state(artifact_id)
    return bool(state and state.get("revoked_at"))
