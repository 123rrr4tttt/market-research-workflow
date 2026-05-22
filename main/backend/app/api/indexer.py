from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..contracts import ApiEnvelope, ErrorCode, error_response, map_exception_to_error
from ..contracts.responses import ok
from ..services.indexer.policy import index_policy_documents
from ..settings.config import settings


router = APIRouter(prefix="/indexer", tags=["indexer"])
IndexerEnvelope = ApiEnvelope[dict[str, Any]]


def _raise_config_error(message: str) -> None:
    raise HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.CONFIG_ERROR,
            message,
        ),
    )


def _raise_indexer_error(code: ErrorCode, message: str, *, details: dict | None = None) -> None:
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
            details=details,
        ),
    )


class ReindexPolicyRequest(BaseModel):
    document_ids: list[int] | None = Field(default=None)
    state: str | None = Field(default=None)


@router.post("/policy", response_model=IndexerEnvelope)
def reindex_policy(payload: ReindexPolicyRequest):
    if not settings.openai_api_key:
        _raise_config_error("OPENAI_API_KEY 未配置，无法生成嵌入")
    try:
        result = index_policy_documents(
            document_ids=payload.document_ids,
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
