from __future__ import annotations

from collections.abc import Mapping
from typing import Any, NoReturn

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from ..contracts import ApiEnvelope, ErrorCode, error_response, map_exception_to_error
from ..contracts.responses import ok
from ..services.indexer.policy import index_policy_documents


router = APIRouter(prefix="/indexer", tags=["indexer"])
IndexerEnvelope = ApiEnvelope[dict[str, Any]]


def _raise_indexer_error(
    code: ErrorCode,
    message: str,
    *,
    details: Mapping[str, object] | None = None,
) -> NoReturn:
    status_code = 500
    if code == ErrorCode.CONFIG_ERROR:
        status_code = 400
    elif code == ErrorCode.INVALID_INPUT:
        status_code = 400
    elif code == ErrorCode.UPSTREAM_ERROR:
        status_code = 503
    raise HTTPException(
        status_code=status_code,
        detail=error_response(
            code,
            message,
            details=None if details is None else dict(details),
        ),
    )


class ReindexPolicyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_ids: list[int] | None = Field(default=None)
    state: str | None = Field(default=None)


@router.post("/policy", response_model=IndexerEnvelope)
def reindex_policy(payload: ReindexPolicyRequest):
    try:
        result = index_policy_documents(
            material_ids=payload.material_ids,
            state=(payload.state.upper() if payload.state else None),
        )
    except ValueError as exc:
        _raise_indexer_error(
            ErrorCode.INVALID_INPUT,
            str(exc),
        )
    except Exception as exc:
        code, message, details = map_exception_to_error(exc)
        _raise_indexer_error(code, message, details=details)
    return ok(result)
