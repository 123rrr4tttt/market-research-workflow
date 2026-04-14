from __future__ import annotations

from typing import Any

CONCURRENCY_CLASSES = frozenset({"read_only", "write_shared", "write_external", "privileged"})


def resolve_task_concurrency_class(task: dict[str, Any]) -> str:
    metadata = dict(task.get("metadata") or {})
    candidate = str(
        metadata.get("concurrency_class")
        or dict(task.get("task_spec") or {}).get("concurrency_class")
        or ("write_shared" if list(task.get("write_set") or []) else "read_only")
    ).strip().lower()
    if candidate not in CONCURRENCY_CLASSES:
        return "read_only"
    return candidate


def requires_approval_for_task(task: dict[str, Any]) -> bool:
    return resolve_task_concurrency_class(task) in {"write_external", "privileged"}
