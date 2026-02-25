from __future__ import annotations

from typing import Any


def task_result_response(
    *,
    task_id: str | None,
    async_mode: bool,
    result: Any = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "task_id": task_id,
        "async": async_mode,
        "status": "queued" if async_mode else "finished",
        "result": result,
    }
    if params:
        payload["params"] = params
    return payload
