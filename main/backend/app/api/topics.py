from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..models.base import SessionLocal
from ..models.entities import Topic


router = APIRouter(prefix="/topics", tags=["topics"])


class TopicPayload(BaseModel):
    topic_name: str = Field(..., min_length=1, max_length=128)
    domains: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=lambda: ["zh", "en"])
    keywords_seed: list[str] = Field(default_factory=list)
    subreddits: list[str] = Field(default_factory=list)
    enabled: bool = True
    description: Optional[str] = None


@router.get("")
def list_topics(enabled: Optional[bool] = Query(default=None)) -> dict:
    with SessionLocal() as session:
        stmt = select(Topic).order_by(Topic.id.asc())
        if enabled is not None:
            stmt = stmt.where(Topic.enabled == enabled)
        rows = session.execute(stmt).scalars().all()
        return {
            "items": [
                {
                    "id": row.id,
                    "topic_name": row.topic_name,
                    "domains": row.domains or [],
                    "languages": row.languages or [],
                    "keywords_seed": row.keywords_seed or [],
                    "subreddits": row.subreddits or [],
                    "enabled": row.enabled,
                    "description": row.description,
                }
                for row in rows
            ]
        }


@router.post("")
def create_topic(payload: TopicPayload) -> dict:
    with SessionLocal() as session:
        existed = session.execute(
            select(Topic).where(Topic.topic_name == payload.topic_name.strip())
        ).scalar_one_or_none()
        if existed:
            raise HTTPException(status_code=409, detail="topic_name already exists")

        row = Topic(
            topic_name=payload.topic_name.strip(),
            domains=payload.domains,
            languages=payload.languages,
            keywords_seed=payload.keywords_seed,
            subreddits=payload.subreddits,
            enabled=payload.enabled,
            description=payload.description,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"id": row.id}


@router.put("/{topic_id}")
def update_topic(topic_id: int, payload: TopicPayload) -> dict:
    with SessionLocal() as session:
        row = session.get(Topic, topic_id)
        if row is None:
            raise HTTPException(status_code=404, detail="topic not found")

        conflict = session.execute(
            select(Topic).where(Topic.topic_name == payload.topic_name.strip(), Topic.id != topic_id)
        ).scalar_one_or_none()
        if conflict:
            raise HTTPException(status_code=409, detail="topic_name already exists")

        row.topic_name = payload.topic_name.strip()
        row.domains = payload.domains
        row.languages = payload.languages
        row.keywords_seed = payload.keywords_seed
        row.subreddits = payload.subreddits
        row.enabled = payload.enabled
        row.description = payload.description
        session.commit()
        return {"updated": topic_id}


@router.delete("/{topic_id}")
def delete_topic(topic_id: int) -> dict:
    with SessionLocal() as session:
        row = session.get(Topic, topic_id)
        if row is None:
            raise HTTPException(status_code=404, detail="topic not found")
        session.delete(row)
        session.commit()
        return {"deleted": topic_id}
