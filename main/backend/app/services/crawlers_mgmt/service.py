from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from functools import lru_cache
from typing import Any

from sqlalchemy import func, select

from ...models.base import SessionLocal
from ...models.entities import CrawlerDeployRun, CrawlerProject
from ..llm.provider import get_chat_model
from ..projects import bind_schema


class CrawlerProjectNotFoundError(ValueError):
    pass


_CORE_TASKS: list[dict[str, str]] = [
    {"id": "T00", "title": "Validate import payload"},
    {"id": "T01", "title": "Resolve project identity"},
    {"id": "T02", "title": "Normalize crawler manifest"},
    {"id": "T03", "title": "Check provider compatibility"},
    {"id": "T04", "title": "Prepare runtime defaults"},
    {"id": "T05", "title": "Build source inventory"},
    {"id": "T06", "title": "Map spider entrypoints"},
    {"id": "T07", "title": "Estimate execution cost"},
    {"id": "T08", "title": "Generate deployment diff"},
    {"id": "T09", "title": "Generate rollback anchor"},
    {"id": "T10", "title": "Validate credentials refs"},
    {"id": "T11", "title": "Apply safety guardrails"},
    {"id": "T12", "title": "Assemble deploy plan"},
    {"id": "T13", "title": "Assemble rollback plan"},
    {"id": "T14", "title": "Create runbook summary"},
    {"id": "T15", "title": "Persist project snapshot"},
    {"id": "T16", "title": "Persist analysis metadata"},
    {"id": "T17", "title": "Prepare deploy run tracking"},
    {"id": "T18", "title": "Prepare post-check hooks"},
    {"id": "T19", "title": "Mark MVP-ready state"},
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    s = (value or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "crawler_project"


def _version_from_payload(payload: dict[str, Any]) -> str:
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    return f"v{digest}"


def _extract_text_from_llm_output(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                txt = item.get("text")
                if isinstance(txt, str):
                    parts.append(txt)
        return "\n".join(parts)
    return str(raw)


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    if "```" not in text:
        return None

    for part in text.split("```"):
        candidate = part.strip()
        if not candidate:
            continue
        if candidate.startswith("json"):
            candidate = candidate[4:].strip()
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _heuristic_plan(import_payload: dict[str, Any]) -> dict[str, Any]:
    source_type = str(import_payload.get("source_type") or "manual")
    source_uri = str(import_payload.get("source_uri") or "")
    tasks = []
    for item in _CORE_TASKS:
        tasks.append(
            {
                "id": item["id"],
                "title": item["title"],
                "status": "planned",
            }
        )

    return {
        "planner_mode": "heuristic",
        "summary": f"Heuristic planner generated MVP steps for source_type={source_type}.",
        "signals": {
            "source_type": source_type,
            "source_uri_present": bool(source_uri),
            "has_manifest": isinstance(import_payload.get("manifest"), dict),
        },
        "tasks": tasks,
    }


def _normalize_plan(candidate: dict[str, Any], fallback: dict[str, Any], *, mode: str) -> dict[str, Any]:
    tasks_raw = candidate.get("tasks") if isinstance(candidate, dict) else None
    tasks: list[dict[str, Any]] = []
    if isinstance(tasks_raw, list):
        for i, task in enumerate(tasks_raw):
            if not isinstance(task, dict):
                continue
            task_id = str(task.get("id") or f"T{i:02d}").strip() or f"T{i:02d}"
            tasks.append(
                {
                    "id": task_id,
                    "title": str(task.get("title") or "Unnamed task"),
                    "status": str(task.get("status") or "planned"),
                    "notes": task.get("notes"),
                }
            )
    if not tasks:
        return fallback

    return {
        "planner_mode": mode,
        "summary": str(candidate.get("summary") or fallback.get("summary") or ""),
        "signals": candidate.get("signals") or fallback.get("signals") or {},
        "tasks": tasks,
    }


def analyze_import_plan(import_payload: dict[str, Any]) -> dict[str, Any]:
    fallback = _heuristic_plan(import_payload)
    try:
        model = get_chat_model(temperature=0.1, max_tokens=1200).with_retry()
        prompt = (
            "Generate an MVP crawler management plan as JSON.\n"
            "Constraints:\n"
            "1) Return only JSON object with keys: summary, signals, tasks.\n"
            "2) tasks must be array of objects with id/title/status/notes.\n"
            "3) Prefer T00-T19 identifiers for atomic tasks.\n"
            "Payload:\n"
            f"{json.dumps(import_payload, ensure_ascii=False)}"
        )
        raw = model.invoke(prompt)
        parsed = _parse_json_object(_extract_text_from_llm_output(raw))
        if not parsed:
            return fallback
        return _normalize_plan(parsed, fallback, mode="llm")
    except Exception:
        return fallback


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
    analysis_plan = analyze_import_plan(payload)
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


def _get_project_model(session, project_id: int | None = None, project_key: str | None = None) -> CrawlerProject:
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
) -> dict[str, Any]:
    with bind_schema("public"):
        with SessionLocal() as session:
            project = _get_project_model(session, project_id=project_id, project_key=project_key)
            target_version = (requested_version or project.current_version or "").strip()
            if not target_version:
                raise ValueError("requested_version is required when current_version is empty")

            run = CrawlerDeployRun(
                crawler_project_id=project.id,
                action="deploy",
                status="queued" if async_mode else "running",
                requested_version=requested_version,
                from_version=project.deployed_version,
                to_version=target_version,
                planner_mode=(planner_mode or (project.analysis_plan or {}).get("planner_mode", "heuristic")),
                plan=project.analysis_plan,
                external_provider=project.provider,
                started_at=_utcnow(),
            )
            session.add(run)

            project.previous_version = project.deployed_version
            project.deployed_version = target_version
            project.status = "deploy_queued" if async_mode else "deployed"

            session.commit()
            session.refresh(run)
            session.refresh(project)
            task_id: str | None = None

            if async_mode:
                import_payload = dict(project.import_payload or {})
                manifest = dict(import_payload.get("manifest") or {})
                metadata = {
                    "crawler_project_id": int(project.id),
                    "crawler_project_key": project.project_key,
                    **dict(import_payload.get("metadata") or {}),
                }
                try:
                    task = _tasks_module().task_orchestrate_crawler_deploy.delay(
                        project_key=project.project_key,
                        scrapy_project=str(
                            import_payload.get("scrapy_project")
                            or manifest.get("scrapy_project")
                            or project.project_key
                        ),
                        spider=str(import_payload.get("spider") or manifest.get("spider") or "default"),
                        channel_key=str(import_payload.get("channel_key") or f"crawler.{project.project_key}"),
                        item_key=str(import_payload.get("item_key") or f"crawler.{project.project_key}.default"),
                        version=target_version,
                        egg_file_path=import_payload.get("egg_file_path"),
                        egg_content_b64=import_payload.get("egg_content_b64"),
                        base_url=import_payload.get("scrapyd_base_url"),
                        metadata=metadata,
                        channel_name=import_payload.get("channel_name"),
                        item_name=import_payload.get("item_name"),
                        description=project.description,
                        arguments=import_payload.get("arguments"),
                        settings=import_payload.get("settings"),
                        enabled=bool(import_payload.get("enable_now", True)),
                    )
                    task_id = str(task.id)
                    run.external_job_id = task_id
                    session.add(run)
                    session.commit()
                    session.refresh(run)
                except Exception as exc:  # noqa: BLE001
                    run.status = "failed"
                    run.error = str(exc)
                    run.finished_at = _utcnow()
                    project.status = "deploy_failed"
                    session.add(run)
                    session.add(project)
                    session.commit()
                    session.refresh(run)
                    session.refresh(project)
            else:
                run.status = "succeeded"
                run.finished_at = _utcnow()
                session.add(run)
                session.commit()
                session.refresh(run)
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
) -> dict[str, Any]:
    with bind_schema("public"):
        with SessionLocal() as session:
            project = _get_project_model(session, project_id=project_id, project_key=project_key)
            rollback_target = (target_version or project.previous_version or project.current_version or "").strip()
            if not rollback_target:
                raise ValueError("target_version is required when no previous/current version exists")

            run = CrawlerDeployRun(
                crawler_project_id=project.id,
                action="rollback",
                status="queued" if async_mode else "running",
                requested_version=target_version,
                from_version=project.deployed_version,
                to_version=rollback_target,
                planner_mode=(planner_mode or (project.analysis_plan or {}).get("planner_mode", "heuristic")),
                plan=project.analysis_plan,
                external_provider=project.provider,
                started_at=_utcnow(),
            )
            session.add(run)

            project.deployed_version = rollback_target
            project.status = "rollback_queued" if async_mode else "rolled_back"

            session.commit()
            session.refresh(run)
            session.refresh(project)
            task_id: str | None = None

            if async_mode:
                import_payload = dict(project.import_payload or {})
                manifest = dict(import_payload.get("manifest") or {})
                try:
                    task = _tasks_module().task_orchestrate_crawler_rollback.delay(
                        project_key=project.project_key,
                        scrapy_project=str(
                            import_payload.get("scrapy_project")
                            or manifest.get("scrapy_project")
                            or project.project_key
                        ),
                        channel_key=str(import_payload.get("channel_key") or f"crawler.{project.project_key}"),
                        item_key=str(import_payload.get("item_key") or f"crawler.{project.project_key}.default"),
                        version=rollback_target,
                        base_url=import_payload.get("scrapyd_base_url"),
                        disable_provider_type_to_native=True,
                        keep_item_enabled=True,
                    )
                    task_id = str(task.id)
                    run.external_job_id = task_id
                    session.add(run)
                    session.commit()
                    session.refresh(run)
                except Exception as exc:  # noqa: BLE001
                    run.status = "failed"
                    run.error = str(exc)
                    run.finished_at = _utcnow()
                    project.status = "rollback_failed"
                    session.add(run)
                    session.add(project)
                    session.commit()
                    session.refresh(run)
                    session.refresh(project)
            else:
                run.status = "succeeded"
                run.finished_at = _utcnow()
                session.add(run)
                session.commit()
                session.refresh(run)
            return {
                "project": _serialize_project(project),
                "run": _serialize_run(run),
                "task_id": task_id,
            }


def get_deploy_run(run_id: int) -> dict[str, Any] | None:
    with bind_schema("public"):
        with SessionLocal() as session:
            row = session.execute(
                select(CrawlerDeployRun).where(CrawlerDeployRun.id == run_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return _serialize_run(row)


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
