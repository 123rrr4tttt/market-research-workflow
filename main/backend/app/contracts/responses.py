from __future__ import annotations

from typing import Any, Generic, TypeVar

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
    return ApiEnvelope[T](
        status="ok",
        data=data,
        error=None,
        meta=meta or ApiMetaModel(),
    ).model_dump(by_alias=True)


def fail(
    code: ErrorCode,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    meta: ApiMetaModel | None = None,
) -> dict[str, Any]:
    return ApiEnvelope[Any](
        status="error",
        data=None,
        error=ApiErrorModel(code=code.value, message=message, details=details or {}),
        meta=meta or ApiMetaModel(),
    ).model_dump(by_alias=True)


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

