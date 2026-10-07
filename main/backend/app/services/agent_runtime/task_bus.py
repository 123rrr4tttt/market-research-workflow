from __future__ import annotations

from typing import Any

ACTIVE_TASK_STATUSES = frozenset({"claimed", "in_progress"})


def find_unresolved_dependencies(task: dict[str, Any], tasks: list[dict[str, Any]]) -> list[str]:
    status_by_id = {str(item.get("task_id") or ""): str(item.get("status") or "") for item in tasks}
    unresolved: list[str] = []
    for dep in list(task.get("blocked_by") or []):
        if status_by_id.get(str(dep), "") != "completed":
            unresolved.append(str(dep))
    return unresolved


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
