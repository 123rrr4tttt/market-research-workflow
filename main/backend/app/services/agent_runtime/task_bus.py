from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

ACTIVE_TASK_STATUSES = frozenset({"claimed", "in_progress"})
FINAL_TASK_STATUSES = frozenset({"completed", "failed", "canceled", "expired"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_string_list(values: Any) -> list[str]:
    out: list[str] = []
    for value in values or []:
        item = str(value or "").strip()
        if item and item not in out:
            out.append(item)
    return out


def find_unresolved_dependencies(task: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    status_by_id = {str(item.get("task_id") or ""): str(item.get("status") or "") for item in tasks}
    unresolved: list[str] = []
    for dep in list(task.get("blocked_by") or []):
        if status_by_id.get(str(dep), "") != "completed":
            unresolved.append(str(dep))
    return unresolved


def assert_no_write_conflict(tasks: list[dict[str, Any]], task_id: str, write_set: list[str]) -> None:
    if not write_set:
        return
    target = set(_normalize_string_list(write_set))
    for task in tasks:
        if str(task.get("task_id") or "") == str(task_id):
            continue
        if str(task.get("status") or "") not in ACTIVE_TASK_STATUSES:
            continue
        other = set(_normalize_string_list(task.get("write_set")))
        if target.intersection(other):
            raise RuntimeError("write_set_conflict")


def collect_expired_task_ids(tasks: list[dict[str, Any]], *, now: datetime | None = None) -> list[str]:
    current = now or _utcnow()
    expired: list[str] = []
    for task in tasks:
        if str(task.get("status") or "") not in ACTIVE_TASK_STATUSES:
            continue
        lease_until = task.get("lease_until")
        if not lease_until:
            continue
        if isinstance(lease_until, str):
            try:
                lease_dt = datetime.fromisoformat(lease_until.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            lease_dt = lease_until
        if lease_dt.tzinfo is None:
            lease_dt = lease_dt.replace(tzinfo=timezone.utc)
        if lease_dt <= current:
            expired.append(str(task.get("task_id") or ""))
    return [item for item in expired if item]


def resolve_session_status(tasks: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not tasks:
        return "pending", None
    active = [task for task in tasks if task.get("status") in ACTIVE_TASK_STATUSES]
    pending = [task for task in tasks if task.get("status") == "pending"]
    blocked = [task for task in tasks if task.get("status") == "blocked"]
    failed = [task for task in tasks if task.get("status") == "failed"]
    canceled = [task for task in tasks if task.get("status") == "canceled"]
    completed = [task for task in tasks if task.get("status") == "completed"]
    waiting_on_approval = [
        task
        for task in tasks
        if str(task.get("task_type") or "").strip().lower() == "approval_wait"
        and str(task.get("status") or "") in {"pending", "claimed", "in_progress", "blocked"}
    ]

    if failed:
        status = "failed"
    elif len(canceled) == len(tasks):
        status = "canceled"
    elif len(completed) == len(tasks):
        status = "completed"
    elif waiting_on_approval:
        status = "blocked"
    elif active:
        status = "active"
    elif blocked and not pending:
        status = "blocked"
    else:
        status = "pending"

    current_phase = None
    for bucket in (waiting_on_approval, active, pending, blocked):
        if bucket:
            current_phase = str(bucket[0].get("phase") or "")
            break
    if status == "completed":
        current_phase = "verification"
    return status, current_phase
