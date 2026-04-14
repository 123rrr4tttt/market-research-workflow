from __future__ import annotations

from typing import Any, Generic, TypeVar
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from .errors import ErrorCode

T = TypeVar("T")


class ApiErrorModel(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PaginationMetaModel(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class ApiMetaModel(BaseModel):
    trace_id: str | None = None
    pagination: PaginationMetaModel | None = None
    project_key: str | None = None
    deprecated: str | None = None


class ApiEnvelope(BaseModel, Generic[T]):
    status: str
    data: T | None
    error: ApiErrorModel | None
    meta: ApiMetaModel = Field(default_factory=ApiMetaModel)


class TaskResultData(BaseModel):
    task_id: str | None = None
    async_mode: bool = Field(alias="async")
    status: str
    result: Any = None
    params: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


def ok(data: T = None, *, meta: ApiMetaModel | None = None) -> dict[str, Any]:
    envelope = ApiEnvelope[T](
        status="ok",
        data=data,
        error=None,
        meta=meta or ApiMetaModel(),
    ).model_dump(by_alias=True)
    _emit_contracts_governance_snapshot(envelope, event="ok")
    return envelope


def fail(
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    meta: ApiMetaModel | None = None,
) -> dict[str, Any]:
    envelope = ApiEnvelope[Any](
        status="error",
        data=None,
        error=ApiErrorModel(code=code.value, message=message, details=details or {}),
        meta=meta or ApiMetaModel(),
    ).model_dump(by_alias=True)
    _emit_contracts_governance_snapshot(envelope, event="error")
    return envelope


def ok_page(
    data: T,
    *,
    page: int,
    page_size: int,
    total: int,
    total_pages: int,
    meta: ApiMetaModel | None = None,
) -> dict[str, Any]:
    merged_meta = (meta or ApiMetaModel()).model_copy(
        update={
            "pagination": PaginationMetaModel(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            )
        }
    )
    return ok(data, meta=merged_meta)


def _emit_contracts_governance_snapshot(envelope: dict[str, Any], *, event: str) -> None:
    """
    Non-intrusive governance hook.

    When `CONTRACT_GOVERNANCE_DIR` is set, writes a lightweight JSON snapshot
    of contract envelopes to that directory. This runs in "observe" mode and
    never raises; it is safe for production and tests.

    To enable in CI observation lanes:
        export CONTRACT_GOVERNANCE_DIR=main/backend/.artifacts/contracts-governance

    Future policy can flip to required by evaluating generated artifacts.
    """
    try:
        out_dir = os.getenv("CONTRACT_GOVERNANCE_DIR") or os.getenv("CONTRACTS_GOVERNANCE_DIR")
        if not out_dir:
            return
        path = Path(out_dir)
        path.mkdir(parents=True, exist_ok=True)
        payload = {
            "event": event,
            "schema": "contract-envelope@v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "envelope": envelope,
        }
        fname = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex}.json"
        (path / fname).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception:
        # Governance hook must never impact runtime behavior.
        return
