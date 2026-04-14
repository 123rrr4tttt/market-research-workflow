from __future__ import annotations

from typing import Any


def build_summary_label(task: dict[str, Any]) -> str:
    result_summary = str(task.get("result_summary") or "").strip()
    if result_summary:
        compact = " ".join(result_summary.split())
        return compact[:120]
    subject = str(task.get("subject") or task.get("task_type") or "task").strip()
    status = str(task.get("status") or "pending").strip()
    return f"{subject} [{status}]"


def build_task_progress_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_use_count": int(task.get("tool_use_count") or 0),
        "token_usage": int(task.get("token_usage") or 0),
        "last_activity": task.get("last_activity"),
        "recent_activities": list(task.get("recent_activities") or []),
        "summary_label": task.get("summary_label"),
        "started_at": task.get("started_at"),
        "updated_at": task.get("updated_at"),
    }
