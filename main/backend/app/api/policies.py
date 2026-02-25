from fastapi import APIRouter, Query


router = APIRouter(prefix="/policies", tags=["policies"])


@router.get("")
def list_policies(
    state: str = Query(..., description="州，如 CA"),
    start: str | None = None,
    end: str | None = None,
):
    """Placeholder: 返回政策概要列表（MVP 后续接数据库/ES）。"""
    return {
        "state": state,
        "range": {"start": start, "end": end},
        "items": [],
    }


