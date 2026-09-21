"""Project-bound session ownership for typed-knowledge live operations."""

from __future__ import annotations

from typing import Any

from ....models.base import SessionLocal
from ...projects import bind_project
from .. import persistence_boundary


def read_live_public_route_contract(*, project_key: str) -> dict[str, Any]:
    with bind_project(project_key), SessionLocal() as session:
        boundary_envelope = persistence_boundary.build_live_db_boundary_envelope(
            session=session,
            project_key=project_key,
            seed_sample=False,
        )
    return persistence_boundary.build_public_api_route_contract_envelope(
        project_key=project_key,
        boundary_envelope=boundary_envelope,
    )


def seed_live_sample(*, project_key: str) -> dict[str, Any]:
    with bind_project(project_key), SessionLocal() as session:
        envelope = persistence_boundary.build_live_db_boundary_envelope(
            session=session,
            project_key=project_key,
            seed_sample=True,
        )
        session.commit()
    return envelope


def read_live_writing_context(*, project_key: str) -> dict[str, Any]:
    with bind_project(project_key), SessionLocal() as session:
        return persistence_boundary.build_live_writing_context_from_repository(
            session=session,
            project_key=project_key,
            seed_sample=False,
        )


def apply_governance_review_state(
    *,
    project_key: str,
    object_type: str,
    object_key: str,
    review_state: str,
    actor_type: str,
    actor_id: str | None,
) -> dict[str, Any]:
    with bind_project(project_key), SessionLocal() as session:
        mutation = persistence_boundary.apply_live_governance_review_state(
            session=session,
            project_key=project_key,
            object_type=object_type,
            object_key=object_key,
            review_state=review_state,
            actor_type=actor_type,
            actor_id=actor_id,
        )
        session.commit()
    return mutation
