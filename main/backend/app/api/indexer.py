from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.indexer.policy import index_policy_documents
from ..settings.config import settings


router = APIRouter(prefix="/indexer", tags=["indexer"])


class ReindexPolicyRequest(BaseModel):
    document_ids: list[int] | None = Field(default=None)
    state: str | None = Field(default=None)


@router.post("/policy")
def reindex_policy(payload: ReindexPolicyRequest):
    if not settings.openai_api_key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 未配置，无法生成嵌入")
    result = index_policy_documents(
        document_ids=payload.document_ids,
        state=(payload.state.upper() if payload.state else None),
    )
    return result


