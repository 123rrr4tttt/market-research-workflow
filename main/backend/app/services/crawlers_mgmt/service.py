from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Literal, TypeGuard, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models.base import SessionLocal
from ...models.entities import CrawlerDeployRun, CrawlerProject
from ..projects import bind_schema
from .orchestration import SCRAPYD_ROLLBACK_UNAVAILABLE


class CrawlerProjectNotFoundError(ValueError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _is_string_object_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict) and all(
        isinstance(key, str) for key in cast(dict[object, object], value)
    )


def _object_view(value: object) -> dict[str, object]:
    return dict(value) if _is_string_object_dict(value) else {}


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _slugify(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "crawler_project"


def _version_from_payload(payload: dict[str, Any]) -> str:
    digest = hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()[:10]
    return f"v{digest}"


def _describe_import(source_type: str, source_uri: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "planner_mode": "heuristic",
        "summary": "Import metadata only; deployment is a separate operation.",
        "signals": {
            "source_type": source_type,
            "source_uri_present": bool(source_uri),
            "has_manifest": isinstance(payload.get("manifest"), dict),
        },
    }


def _serialize_project(project: CrawlerProject) -> dict[str, Any]:
    return {
        "id": int(project.id),
        "project_key": project.project_key,
        "name": project.name,
        "description": project.description,
        "source_type": project.source_type,
        "source_uri": project.source_uri,
        "provider": project.provider,
        "status": project.status,
        "current_version": project.current_version,
        "deployed_version": project.deployed_version,
        "previous_version": project.previous_version,
        "analysis_plan": project.analysis_plan,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _serialize_run(run: CrawlerDeployRun) -> dict[str, Any]:
    return {
        "id": int(run.id),
        "crawler_project_id": int(run.crawler_project_id),
        "action": run.action,
        "status": run.status,
        "requested_version": run.requested_version,
        "from_version": run.from_version,
        "to_version": run.to_version,
        "planner_mode": run.planner_mode,
        "plan": run.plan,
        "external_provider": run.external_provider,
        "external_job_id": run.external_job_id,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@lru_cache(maxsize=1)
def _tasks_module():
    from .. import tasks as tasks_module

    return tasks_module


def import_project(payload: dict[str, Any]) -> dict[str, Any]:
    source_uri = (
        str(payload.get("source_uri") or "").strip()
        or str(payload.get("repo_url") or "").strip()
        or None
    )
    source_type = str(payload.get("source_type") or "git").strip() or "git"
    provider_hint = str(payload.get("provider_hint") or "").strip().lower()
    provider = str(payload.get("provider") or provider_hint or "scrapyd").strip() or "scrapyd"

    name = str(payload.get("name") or "").strip()
    if not name:
        if payload.get("project_key"):
            name = str(payload.get("project_key")).strip()
        elif source_uri:
            name = source_uri.rstrip("/").rsplit("/", 1)[-1].replace(".git", "") or "crawler_project"
        else:
            raise ValueError("name is required")

    project_key = _slugify(str(payload.get("project_key") or name))
    description = payload.get("description")
    analysis_plan = _describe_import(source_type, source_uri, payload)
    version = str(payload.get("version") or _version_from_payload(payload))

    with bind_schema("public"):
        with SessionLocal() as session:
            existing = session.execute(
                select(CrawlerProject).where(CrawlerProject.project_key == project_key)
            ).scalar_one_or_none()

            if existing is None:
                existing = CrawlerProject(
                    project_key=project_key,
                    name=name,
                    description=description,
                    source_type=source_type,
                    source_uri=source_uri,
                    provider=provider,
                    status="imported",
                    current_version=version,
                    import_payload=payload,
                    analysis_plan=analysis_plan,
                )
                session.add(existing)
            else:
                existing.name = name
                existing.description = description
                existing.source_type = source_type
                existing.source_uri = source_uri
                existing.provider = provider
                existing.status = "imported"
                existing.current_version = version
                existing.import_payload = payload
                existing.analysis_plan = analysis_plan

            session.commit()
            session.refresh(existing)
            return _serialize_project(existing)


def list_projects(*, page: int = 1, page_size: int = 20) -> tuple[list[dict[str, Any]], int]:
    offset = (max(page, 1) - 1) * page_size
    with bind_schema("public"):
        with SessionLocal() as session:
            total = int(session.execute(select(func.count(CrawlerProject.id))).scalar_one())
            rows = session.execute(
                select(CrawlerProject)
                .order_by(CrawlerProject.updated_at.desc(), CrawlerProject.id.desc())
                .offset(offset)
                .limit(page_size)
            ).scalars().all()
            return ([_serialize_project(x) for x in rows], total)


def get_project(project_id: int | None = None, project_key: str | None = None) -> dict[str, Any] | None:
    key = str(project_key or "").strip()
    with bind_schema("public"):
        with SessionLocal() as session:
            if key:
                row = session.execute(
                    select(CrawlerProject).where(CrawlerProject.project_key == key)
                ).scalar_one_or_none()
            elif project_id is not None:
                row = session.execute(
                    select(CrawlerProject).where(CrawlerProject.id == project_id)
                ).scalar_one_or_none()
            else:
                row = None
            if row is None:
                return None
            return _serialize_project(row)


def _get_project_model(
    session: Session,
    project_id: int | None = None,
    project_key: str | None = None,
) -> CrawlerProject:
    key = str(project_key or "").strip()
    if key:
        row = session.execute(
            select(CrawlerProject).where(CrawlerProject.project_key == key)
        ).scalar_one_or_none()
    else:
        row = session.execute(
            select(CrawlerProject).where(CrawlerProject.id == project_id)
        ).scalar_one_or_none()
    if row is None:
        hint = key or str(project_id)
        raise CrawlerProjectNotFoundError(f"crawler project not found: {hint}")
    return row


def deploy_project(
    project_id: int | None = None,
    *,
    project_key: str | None = None,
    requested_version: str | None = None,
    planner_mode: str | None = None,
    async_mode: bool = False,
    registration_project_key: str | None = None,
) -> dict[str, Any]:
    with bind_schema("public"):
        with SessionLocal() as session:
            project = _get_project_model(session, project_id=project_id, project_key=project_key)
            target_version = (requested_version or project.current_version or "").strip()
            if not target_version:
                raise ValueError("requested_version is required when current_version is empty")

            if not async_mode:
                message = "Synchronous crawler deployment is unavailable; use async_mode=true."
                raise ValueError(message)
            if project.provider.lower() not in {"scrapyd", "scrapy"}:
                message = f"No crawler deployment executor is bound for provider: {project.provider}"
                raise ValueError(message)

            run = CrawlerDeployRun(
                crawler_project_id=project.id,
                action="deploy",
                status="queued",
                requested_version=requested_version,
                from_version=project.deployed_version,
                to_version=target_version,
                planner_mode=(planner_mode or (project.analysis_plan or {}).get("planner_mode", "heuristic")),
                plan=project.analysis_plan,
                external_provider=project.provider,
                started_at=_utcnow(),
            )
            session.add(run)

            project.status = "deploy_queued"
            session.commit()

            import_payload = _object_view(project.import_payload)
            manifest = _object_view(import_payload.get("manifest"))
            registration_key = str(registration_project_key or "").strip() or project.project_key
            metadata = {
                "crawler_project_id": int(project.id),
                "crawler_project_key": project.project_key,
                "registration_project_key": registration_key,
                **_object_view(import_payload.get("metadata")),
            }
            try:
                task = _tasks_module().task_orchestrate_crawler_deploy.delay(
                    deploy_run_id=int(run.id),
                    project_key=registration_key,
                    scrapy_project=str(
                        import_payload.get("scrapy_project")
                        or manifest.get("scrapy_project")
                        or project.project_key
                    ),
                    spider=str(import_payload.get("spider") or manifest.get("spider") or "default"),
                    channel_key=str(import_payload.get("channel_key") or f"crawler.{project.project_key}"),
                    item_key=str(import_payload.get("item_key") or f"crawler.{project.project_key}.default"),
                    version=target_version,
                    egg_file_path=_optional_text(import_payload.get("egg_file_path")),
                    egg_content_b64=_optional_text(import_payload.get("egg_content_b64")),
                    base_url=_optional_text(import_payload.get("scrapyd_base_url")),
                    metadata=metadata,
                    channel_name=_optional_text(import_payload.get("channel_name")),
                    item_name=_optional_text(import_payload.get("item_name")),
                    description=project.description,
                    arguments=_object_view(import_payload.get("arguments")) or None,
                    settings=_object_view(import_payload.get("settings")) or None,
                    enabled=bool(import_payload.get("enable_now", True)),
                )
            except Exception as exc:
                finalize_deploy_run(int(run.id), status="failed", error=str(exc))
                task_id = None
            else:
                task_id = str(task.id)
                run.external_job_id = task_id
                session.commit()

            # The worker may have already produced a terminal receipt.
            session.refresh(run)
            session.refresh(project)
            return {
                "project": _serialize_project(project),
                "run": _serialize_run(run),
                "task_id": task_id,
            }


def rollback_project(
    project_id: int | None = None,
    *,
    project_key: str | None = None,
    target_version: str | None = None,
    planner_mode: str | None = None,
    async_mode: bool = False,
    registration_project_key: str | None = None,
) -> dict[str, Any]:
    with bind_schema("public"):
        with SessionLocal() as session:
            _get_project_model(session, project_id=project_id, project_key=project_key)
            raise ValueError(SCRAPYD_ROLLBACK_UNAVAILABLE)


def get_deploy_run(run_id: int) -> dict[str, Any] | None:
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(CrawlerDeployRun).where(CrawlerDeployRun.id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _serialize_run(row)


def finalize_deploy_run(
    run_id: int,
    *,
    status: Literal["succeeded", "registered", "failed"],
    error: str | None = None,
) -> dict[str, Any]:
    """Persist the terminal state owned by the original crawler deploy run."""
    terminal_statuses = {"succeeded", "registered", "failed"}
    if status not in terminal_statuses:
        raise ValueError(f"unsupported crawler deploy terminal status: {status}")
    with bind_schema("public"):
        with SessionLocal() as session:
            run = session.execute(
                select(CrawlerDeployRun).where(CrawlerDeployRun.id == int(run_id)).with_for_update()
            ).scalar_one_or_none()
            if run is None:
                raise ValueError(f"crawler deploy run not found: {run_id}")
            if run.status in terminal_statuses:
                return _serialize_run(run)

            project = session.execute(
                select(CrawlerProject).where(CrawlerProject.id == run.crawler_project_id).with_for_update()
            ).scalar_one()
            run.status = status
            run.error = str(error or "").strip() or None
            run.finished_at = _utcnow()
            if status == "succeeded":
                if run.action != "deploy" or not run.to_version:
                    message = "No supported crawler deployment version to record."
                    raise ValueError(message)
                if project.deployed_version != run.to_version:
                    project.previous_version = project.deployed_version
                    project.deployed_version = run.to_version
                project.status = "deployed"
            elif status == "registered":
                if run.action != "deploy":
                    message = "Registration is only a crawler deployment outcome."
                    raise ValueError(message)
                project.status = "registered"
            else:
                project.status = "rollback_failed" if run.action == "rollback" else "deploy_failed"
            session.add(run)
            session.add(project)
            session.commit()
            session.refresh(run)
            return _serialize_run(run)


def list_deploy_runs(
    *,
    project_key: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    size = max(1, min(200, int(limit)))
    key = str(project_key or "").strip()
    with bind_schema("public"):
        with SessionLocal() as session:
            stmt = select(CrawlerDeployRun).order_by(CrawlerDeployRun.created_at.desc(), CrawlerDeployRun.id.desc()).limit(size)
            if key:
                project = session.execute(
                    select(CrawlerProject).where(CrawlerProject.project_key == key)
                ).scalar_one_or_none()
                if project is None:
                    return []
                stmt = (
                    select(CrawlerDeployRun)
                    .where(CrawlerDeployRun.crawler_project_id == project.id)
                    .order_by(CrawlerDeployRun.created_at.desc(), CrawlerDeployRun.id.desc())
                    .limit(size)
                )
            rows = session.execute(stmt).scalars().all()
            return [_serialize_run(row) for row in rows]
