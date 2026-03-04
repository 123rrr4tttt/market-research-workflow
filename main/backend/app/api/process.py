"""任务进程管理API - 管理Celery任务"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import List, Optional, Dict, Any
from datetime import datetime
import json
from fastapi import APIRouter, HTTPException, Query
import os
from collections import deque
from pydantic import BaseModel
from sqlalchemy import select, func

from ..celery_app import celery_app
from ..contracts.responses import ok
from ..models.base import SessionLocal
from ..models.entities import EtlJobRun
from ..services.projects import bind_project
from ..services.ingest.meaningful_gate import normalize_reason_code

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])
_DB_JOB_PREFIX = "db-job-"
_DEBUG_LOG_PATH = "/Users/wangyiliang/market-research-workflow/.cursor/debug-14c8b9.log"
_DEBUG_SESSION_ID = "14c8b9"


def _debug_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any] | None = None) -> None:
    try:
        payload = {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(datetime.now().timestamp() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _coerce_int(value: Any) -> int | None:
    try:
        iv = int(value)
    except Exception:
        return None
    return iv if iv >= 0 else None


def _as_non_empty_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _extract_handler_used(*payloads: Any) -> str | None:
    for payload in payloads:
        item = _as_dict(payload)
        direct = _as_non_empty_str(item.get("handler_used"))
        if direct:
            return direct
        alloc = _as_dict(item.get("handler_allocation"))
        nested = _as_non_empty_str(alloc.get("handler_used"))
        if nested:
            return nested
    return None


def _extract_skip_reason(*payloads: Any) -> str | None:
    candidates: list[str] = []
    for payload in payloads:
        item = _as_dict(payload)
        direct = _as_non_empty_str(item.get("skip_reason"))
        if direct:
            return normalize_reason_code(direct)
        for key in ("page_gate", "pre_write_content_gate", "pre_fetch_url_gate", "provenance_gate"):
            nested = _as_dict(item.get(key))
            reason = _as_non_empty_str(nested.get("reason"))
            if reason:
                return normalize_reason_code(reason)
        rb = item.get("rejection_breakdown")
        if isinstance(rb, dict):
            for k, v in rb.items():
                name = _as_non_empty_str(k)
                count = _coerce_int(v)
                if name and count and count > 0:
                    candidates.append(normalize_reason_code(name))
    if not candidates:
        return None
    # Deterministic fallback when only rejection breakdown is available.
    counts: Dict[str, int] = {}
    for name in candidates:
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _extract_error_code(*payloads: Any, status: Any = None, error: Any = None) -> str | None:
    for payload in payloads:
        item = _as_dict(payload)
        direct = _as_non_empty_str(item.get("error_code"))
        if direct:
            return direct
        nested_error = _as_dict(item.get("error"))
        nested_code = _as_non_empty_str(nested_error.get("code"))
        if nested_code:
            return nested_code
    status_text = str(status or "").strip().lower()
    if status_text == "failed" or _as_non_empty_str(error):
        return "TASK_FAILED"
    if status_text in {"completed", "success"}:
        return "OK"
    return None


def _extract_quality_fields(*payloads: Any) -> Dict[str, Any]:
    data = [_as_dict(p) for p in payloads]
    inserted_valid: int | None = None
    rejected_count: int | None = None
    rejection_breakdown: Dict[str, int] = {}
    degradation_flags: list[str] = []
    quality_score: float | None = None

    for item in data:
        if inserted_valid is None:
            inserted_valid = _coerce_int(item.get("inserted_valid"))
        if rejected_count is None:
            rejected_count = _coerce_int(item.get("rejected_count"))
        rb = item.get("rejection_breakdown")
        if isinstance(rb, dict):
            for k, v in rb.items():
                key = normalize_reason_code(k)
                val = _coerce_int(v)
                if not key or val is None:
                    continue
                rejection_breakdown[key] = rejection_breakdown.get(key, 0) + val
        flags = item.get("degradation_flags")
        if isinstance(flags, list):
            for flag in flags:
                name = str(flag or "").strip()
                if name and name not in degradation_flags:
                    degradation_flags.append(name)
        if quality_score is None:
            try:
                qv = float(item.get("quality_score"))
            except Exception:
                qv = None
            if qv is not None and qv >= 0:
                quality_score = qv

    if rejected_count is None and rejection_breakdown:
        rejected_count = sum(rejection_breakdown.values())
    if rejected_count is None:
        rejected_count = 0

    out: Dict[str, Any] = {
        "rejected_count": rejected_count,
        "rejection_breakdown": rejection_breakdown,
        "degradation_flags": degradation_flags,
    }
    if inserted_valid is not None:
        out["inserted_valid"] = inserted_valid
    if quality_score is not None:
        out["quality_score"] = quality_score
    return out


def _extract_search_observability_fields(*payloads: Any) -> Dict[str, Any]:
    def _normalize_search_results(value: Any) -> Dict[str, Any]:
        item = _as_dict(value)
        if not item:
            return {}
        out: Dict[str, Any] = {}
        rc = _coerce_int(item.get("result_count"))
        if rc is not None:
            out["result_count"] = rc
        fb = item.get("fallback_used")
        if isinstance(fb, bool):
            out["fallback_used"] = fb
        elif fb is not None:
            out["fallback_used"] = bool(fb)
        return out

    def _normalize_search_expand(value: Any) -> Dict[str, Any]:
        item = _as_dict(value)
        if not item:
            return {}
        out: Dict[str, Any] = {}
        enabled = item.get("enabled")
        if isinstance(enabled, bool):
            out["enabled"] = enabled
        elif enabled is not None:
            out["enabled"] = bool(enabled)
        ec = _coerce_int(item.get("expanded_count"))
        if ec is not None:
            out["expanded_count"] = ec
        return out

    for payload in payloads:
        item = _as_dict(payload)
        sr = _normalize_search_results(item.get("search_results"))
        se = _normalize_search_expand(item.get("search_expand"))
        if sr or se:
            return {"search_results": sr, "search_expand": se}
    return {"search_results": {}, "search_expand": {}}


class TaskInfo(BaseModel):
    """任务信息模型"""
    task_id: str
    name: str
    status: str
    args: List[Any]
    kwargs: Dict[str, Any]
    worker: Optional[str] = None
    started_at: Optional[str] = None
    display_meta: Optional[Dict[str, Any]] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskInfo]
    stats: dict


@router.get("/list")
def list_tasks(
    status_filter: Optional[str] = None,
    limit: int = 100,
    project_key: Optional[str] = None,
) -> dict[str, Any]:
    """获取Celery任务列表"""
    try:
        run_id = f"list_tasks:{int(datetime.now().timestamp() * 1000)}"
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H1",
            location="api/process.py:list_tasks:entry",
            message="list_tasks entry",
            data={"status_filter": status_filter, "limit": limit, "project_key": project_key},
        )
        # endregion
        from ..services.collect_runtime import infer_display_meta_from_celery_task, extract_display_meta_from_params
        inspect = celery_app.control.inspect()
        tasks = []
        
        # 获取活跃任务
        active_tasks = inspect.active() or {}
        # 获取已调度任务
        scheduled_tasks = inspect.scheduled() or {}
        # 获取保留任务
        reserved_tasks = inspect.reserved() or {}
        # 获取已注册任务（用于统计）
        registered_tasks = inspect.registered() or {}
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H2",
            location="api/process.py:list_tasks:inspect",
            message="inspect snapshot",
            data={
                "active_workers": len(active_tasks),
                "scheduled_workers": len(scheduled_tasks),
                "reserved_workers": len(reserved_tasks),
                "registered_workers": len(registered_tasks),
            },
        )
        # endregion
        
        total_tasks = 0
        active_count = 0
        pending_count = 0
        
        # 处理活跃任务
        for worker_name, worker_tasks in active_tasks.items():
            for task in worker_tasks:
                total_tasks += 1
                active_count += 1
                
                if status_filter and status_filter != 'active':
                    continue
                
                task_info = TaskInfo(
                    task_id=task.get('id', 'unknown'),
                    name=task.get('name', 'unknown'),
                    status='active',
                    args=task.get('args', []),
                    kwargs=task.get('kwargs', {}),
                    worker=worker_name,
                    started_at=datetime.fromtimestamp(task.get('time_start', 0)).isoformat() if task.get('time_start') else None,
                    display_meta=infer_display_meta_from_celery_task(task.get('name', 'unknown'), task.get('args', []), task.get('kwargs', {})),
                )
                tasks.append(task_info)
        
        # 处理已调度任务
        for worker_name, worker_tasks in scheduled_tasks.items():
            for task in worker_tasks:
                total_tasks += 1
                pending_count += 1
                
                if status_filter and status_filter != 'pending':
                    continue
                
                task_info = TaskInfo(
                    task_id=task.get('request', {}).get('id', 'unknown'),
                    name=task.get('request', {}).get('task', 'unknown'),
                    status='pending',
                    args=task.get('request', {}).get('args', []),
                    kwargs=task.get('request', {}).get('kwargs', {}),
                    worker=worker_name,
                    display_meta=infer_display_meta_from_celery_task(
                        task.get('request', {}).get('task', 'unknown'),
                        task.get('request', {}).get('args', []),
                        task.get('request', {}).get('kwargs', {}),
                    ),
                )
                tasks.append(task_info)
        
        # 处理保留任务
        for worker_name, worker_tasks in reserved_tasks.items():
            for task in worker_tasks:
                total_tasks += 1
                pending_count += 1
                
                if status_filter and status_filter not in ['pending', 'reserved']:
                    continue
                
                task_info = TaskInfo(
                    task_id=task.get('id', 'unknown'),
                    name=task.get('name', 'unknown'),
                    status='reserved',
                    args=task.get('args', []),
                    kwargs=task.get('kwargs', {}),
                    worker=worker_name,
                    display_meta=infer_display_meta_from_celery_task(task.get('name', 'unknown'), task.get('args', []), task.get('kwargs', {})),
                )
                tasks.append(task_info)
        
        # 回填数据库中的 running 任务（用于同步执行链路或 worker 重启后仍在执行窗口内的任务展示）
        if not status_filter or status_filter in {"active", "running"}:
            ctx = bind_project(project_key) if project_key else nullcontext()
            with ctx:
                with SessionLocal() as session:
                    q = (
                        select(EtlJobRun)
                        .where(EtlJobRun.status == "running")
                        .order_by(EtlJobRun.started_at.desc().nullslast())
                        .limit(max(1, min(limit, 300)))
                    )
                    running_jobs = session.execute(q).scalars().all()
            # region agent log
            _debug_log(
                run_id=run_id,
                hypothesis_id="H3",
                location="api/process.py:list_tasks:db_running_jobs",
                message="db running jobs loaded",
                data={"project_key": project_key, "running_jobs": len(running_jobs)},
            )
            # endregion
            existing_ids = {str(t.task_id) for t in tasks}
            for job in running_jobs:
                pseudo_id = f"db-job-{job.id}"
                if pseudo_id in existing_ids:
                    continue
                params = dict(job.params or {})
                display_meta = extract_display_meta_from_params(params)
                task_name = (
                    str(params.get("job_type_full") or "").strip()
                    or str(job.job_type or "").strip()
                    or "db_running_job"
                )
                task_info = TaskInfo(
                    task_id=pseudo_id,
                    name=task_name,
                    status="active",
                    args=[],
                    kwargs=params,
                    worker="db-running",
                    started_at=job.started_at.isoformat() if job.started_at else None,
                    display_meta=display_meta,
                )
                tasks.append(task_info)
                total_tasks += 1
                active_count += 1

        # 限制返回数量
        tasks = tasks[:limit]
        
        # 获取已注册的任务类型
        registered_task_names = set()
        for worker_name, task_list in registered_tasks.items():
            registered_task_names.update(task_list)
        
        stats = {
            'total_tasks': total_tasks,
            'active_tasks': active_count,
            'pending_tasks': pending_count,
            'registered_task_types': len(registered_task_names),
            'workers': len(set(list(active_tasks.keys()) + list(registered_tasks.keys()))),
        }

        return ok(
            {
                "tasks": tasks,
                "stats": stats,
            }
        )

    except Exception as e:
        # region agent log
        _debug_log(
            run_id=f"list_tasks:error:{int(datetime.now().timestamp() * 1000)}",
            hypothesis_id="H4",
            location="api/process.py:list_tasks:exception",
            message="list_tasks exception",
            data={"error_type": type(e).__name__, "error": str(e)},
        )
        # endregion
        logger.exception("获取任务列表失败")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.get("/stats")
def get_task_stats() -> dict[str, Any]:
    """获取任务统计信息"""
    try:
        inspect = celery_app.control.inspect()
        
        # 获取活跃任务
        active_tasks = inspect.active() or {}
        # 获取已注册任务
        registered_tasks = inspect.registered() or {}
        # 获取已调度任务
        scheduled_tasks = inspect.scheduled() or {}
        # 获取保留任务
        reserved_tasks = inspect.reserved() or {}
        
        active_count = sum(len(tasks) for tasks in active_tasks.values())
        scheduled_count = sum(len(tasks) for tasks in scheduled_tasks.values())
        reserved_count = sum(len(tasks) for tasks in reserved_tasks.values())
        
        # 获取已注册的任务类型
        registered_task_names = set()
        for worker_name, task_list in registered_tasks.items():
            registered_task_names.update(task_list)
        
        # 获取worker信息
        workers = list(set(list(active_tasks.keys()) + list(registered_tasks.keys())))
        
        return ok(
            {
                'active_tasks': active_count,
                'scheduled_tasks': scheduled_count,
                'reserved_tasks': reserved_count,
                'total_running': active_count + scheduled_count + reserved_count,
                'registered_task_types': len(registered_task_names),
                'workers': len(workers),
                'worker_names': workers,
            }
        )

    except Exception as e:
        logger.exception("获取任务统计信息失败")
        raise HTTPException(status_code=500, detail=f"获取任务统计信息失败: {str(e)}")


@router.get("/history")
def get_task_history(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(None, description="任务状态过滤: completed, failed, running"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的任务历史）"),
    trace_id: Optional[str] = Query(None, description="按 trace_id 过滤（EtlJobRun.params.trace_id）"),
) -> dict[str, Any]:
    """获取任务历史记录"""
    try:
        from ..services.collect_runtime import extract_display_meta_from_params
        ctx = bind_project(project_key) if project_key else nullcontext()
        with ctx:
            with SessionLocal() as session:
                query = select(EtlJobRun)
            
            # 应用过滤器
                if status:
                    query = query.where(EtlJobRun.status == status)
                if job_type:
                    query = query.where(EtlJobRun.job_type == job_type)
            
            # 按开始时间倒序排列
                query = query.order_by(EtlJobRun.started_at.desc().nullslast())
            
                jobs = session.execute(query).scalars().all()

            trace_text = str(trace_id or "").strip()
            if trace_text:
                jobs = [job for job in jobs if str((job.params or {}).get("trace_id") or "").strip() == trace_text]
            jobs = jobs[:limit]
            
            # 转换为字典格式
            history = []
            for job in jobs:
                duration = None
                if job.started_at and job.finished_at:
                    duration = (job.finished_at - job.started_at).total_seconds()
                elif job.started_at:
                    duration = (datetime.now(job.started_at.tzinfo) - job.started_at).total_seconds()
                params = dict(job.params or {})
                quality_fields = _extract_quality_fields(
                    params,
                    params.get("result"),
                    params.get("progress"),
                )
                handler_used = _extract_handler_used(params, params.get("result"), params.get("progress"))
                skip_reason = _extract_skip_reason(params, params.get("result"), params.get("progress"))
                error_code = _extract_error_code(
                    params,
                    params.get("result"),
                    params.get("progress"),
                    status=job.status,
                    error=job.error,
                )
                search_fields = _extract_search_observability_fields(
                    params,
                    params.get("result"),
                    params.get("progress"),
                )

                history.append({
                    "id": job.id,
                    "job_type": job.job_type,
                    "status": job.status,
                    "external_provider": getattr(job, "external_provider", None),
                    "external_job_id": getattr(job, "external_job_id", None),
                    "retry_count": getattr(job, "retry_count", None),
                    "params": params,
                    "display_meta": extract_display_meta_from_params(params),
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                    "duration_seconds": duration,
                    "error": job.error,
                    "inserted_valid": quality_fields.get("inserted_valid"),
                    "rejected_count": quality_fields.get("rejected_count"),
                    "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
                    "degradation_flags": quality_fields.get("degradation_flags") or [],
                    "quality_score": quality_fields.get("quality_score"),
                    "error_code": error_code,
                    "handler_used": handler_used,
                    "skip_reason": skip_reason,
                    "search_results": search_fields.get("search_results") or {},
                    "search_expand": search_fields.get("search_expand") or {},
                })
            
            # 获取统计信息
            if trace_text:
                total = len(jobs)
            else:
                total_query = select(func.count(EtlJobRun.id))
                if status:
                    total_query = total_query.where(EtlJobRun.status == status)
                if job_type:
                    total_query = total_query.where(EtlJobRun.job_type == job_type)
                total = session.execute(total_query).scalar() or 0

            # 按状态统计
            status_stats = {}
            if trace_text:
                for row in history:
                    st = str(row.get("status") or "")
                    if not st:
                        continue
                    status_stats[st] = int(status_stats.get(st) or 0) + 1
            else:
                status_query = select(
                    EtlJobRun.status,
                    func.count(EtlJobRun.id).label("count")
                )
                if job_type:
                    status_query = status_query.where(EtlJobRun.job_type == job_type)
                status_query = status_query.group_by(EtlJobRun.status)
                for row in session.execute(status_query).all():
                    status_stats[row.status] = row.count

            return ok(
                {
                    "history": history,
                    "total": total,
                    "status_stats": status_stats,
                    "project_key": project_key,
                    "trace_id": trace_text or None,
                }
            )

    except Exception as e:
        logger.exception("获取任务历史记录失败")
        raise HTTPException(status_code=500, detail=f"获取任务历史记录失败: {str(e)}")


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, terminate: bool = False) -> dict[str, Any]:
    """取消指定任务"""
    try:
        # 撤销任务
        celery_app.control.revoke(task_id, terminate=terminate)
        
        action = "强制终止" if terminate else "取消"
        
        return ok(
            {
                "success": True,
                "message": f"任务 {task_id} 已{action}",
                "task_id": task_id,
            }
        )

    except Exception as e:
        logger.exception(f"取消任务 {task_id} 失败")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")


def _parse_db_job_id(task_id: str) -> int | None:
    if not str(task_id or "").startswith(_DB_JOB_PREFIX):
        return None
    suffix = str(task_id)[len(_DB_JOB_PREFIX):].strip()
    if not suffix.isdigit():
        return None
    return int(suffix)


def _resolve_db_job(task_id: str) -> EtlJobRun | None:
    job_id = _parse_db_job_id(task_id)
    if job_id is None:
        return None
    with SessionLocal() as session:
        return session.get(EtlJobRun, job_id)


def _db_job_to_task_info(task_id: str, job: EtlJobRun) -> dict[str, Any]:
    status_raw = str(job.status or "running").strip().lower()
    ready = status_raw in {"completed", "failed", "cancelled", "canceled"}
    is_external = bool(str(job.external_provider or "").strip())
    params_payload = dict(job.params or {})
    result_payload = None
    if ready:
        result_payload = dict(params_payload)
        if is_external:
            result_payload.setdefault(
                "external_log_hint",
                "External provider task is tracked in DB; live worker logs are unavailable.",
            )
    progress_payload = None
    if not ready:
        progress_payload = dict(params_payload)
        if is_external:
            progress_payload.setdefault("external_provider", job.external_provider)
            progress_payload.setdefault("external_job_id", job.external_job_id)
    # Avoid double counting when running jobs mirror params into progress payload.
    if ready:
        quality_fields = _extract_quality_fields(result_payload or params_payload)
    else:
        quality_fields = _extract_quality_fields(progress_payload or params_payload)
    handler_used = _extract_handler_used(params_payload, result_payload, progress_payload)
    skip_reason = _extract_skip_reason(params_payload, result_payload, progress_payload)
    error_code = _extract_error_code(
        params_payload,
        result_payload,
        progress_payload,
        status=job.status,
        error=job.error,
    )
    search_fields = _extract_search_observability_fields(
        params_payload,
        result_payload,
        progress_payload,
    )
    return {
        "task_id": task_id,
        "name": str(params_payload.get("job_type_full") or job.job_type or "db_job"),
        "status": str(job.status or "running").upper(),
        "ready": ready,
        "successful": ready and status_raw == "completed",
        "failed": ready and status_raw == "failed",
        "result": result_payload,
        "progress": progress_payload,
        "traceback": job.error if status_raw == "failed" else None,
        "worker": "external-provider" if is_external else "db-running",
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "external_provider": job.external_provider,
        "external_job_id": job.external_job_id,
        "retry_count": job.retry_count,
        "source": "db",
        "inserted_valid": quality_fields.get("inserted_valid"),
        "rejected_count": quality_fields.get("rejected_count"),
        "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
        "degradation_flags": quality_fields.get("degradation_flags") or [],
        "quality_score": quality_fields.get("quality_score"),
        "error_code": error_code,
        "handler_used": handler_used,
        "skip_reason": skip_reason,
        "search_results": search_fields.get("search_results") or {},
        "search_expand": search_fields.get("search_expand") or {},
    }


@router.get("/{task_id}")
def get_task_info(task_id: str) -> dict[str, Any]:
    """获取任务详细信息"""
    try:
        db_job = _resolve_db_job(task_id)
        if db_job is not None:
            return ok(_db_job_to_task_info(task_id, db_job))

        result = celery_app.AsyncResult(task_id)
        
        task_info = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None,
            "result": result.result if result.ready() else None,
            "progress": result.info if not result.ready() and isinstance(getattr(result, "info", None), dict) else None,
            "traceback": result.traceback if result.failed() else None,
        }
        quality_fields = _extract_quality_fields(task_info.get("result"), task_info.get("progress"))
        handler_used = _extract_handler_used(task_info.get("result"), task_info.get("progress"))
        skip_reason = _extract_skip_reason(task_info.get("result"), task_info.get("progress"))
        error_code = _extract_error_code(
            task_info.get("result"),
            task_info.get("progress"),
            status=task_info.get("status"),
            error=task_info.get("traceback"),
        )
        search_fields = _extract_search_observability_fields(
            task_info.get("result"),
            task_info.get("progress"),
        )
        task_info.update(
            {
                "inserted_valid": quality_fields.get("inserted_valid"),
                "rejected_count": quality_fields.get("rejected_count"),
                "rejection_breakdown": quality_fields.get("rejection_breakdown") or {},
                "degradation_flags": quality_fields.get("degradation_flags") or [],
                "quality_score": quality_fields.get("quality_score"),
                "error_code": error_code,
                "handler_used": handler_used,
                "skip_reason": skip_reason,
                "search_results": search_fields.get("search_results") or {},
                "search_expand": search_fields.get("search_expand") or {},
            }
        )
        
        # 尝试获取任务名称
        try:
            task_info["name"] = result.name
        except:
            task_info["name"] = "unknown"
        
        return ok(task_info)

    except Exception as e:
        logger.exception(f"获取任务信息失败: {task_id}")
        raise HTTPException(status_code=500, detail=f"获取任务信息失败: {str(e)}")



def _tail_file(path: str, max_lines: int) -> list[str]:
    """读取文件末尾的若干行，容错忽略编码错误。"""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            dq = deque(f, maxlen=max_lines)
            return list(dq)
    except FileNotFoundError:
        return []


def _merge_ranges(ranges: list[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    """合并并裁剪行号范围。"""
    if not ranges:
        return []
    normalized = sorted((max(0, s), min(total, e)) for s, e in ranges if s < e)
    if not normalized:
        return []
    merged: list[tuple[int, int]] = [normalized[0]]
    for start, end in normalized[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _extract_context_lines(lines: list[str], task_id: str, context: int = 20) -> list[str]:
    """提取包含 task_id 的命中行及其上下文，减少误过滤导致的“日志不更新”问题。"""
    if not lines:
        return []
    hit_indexes = [idx for idx, line in enumerate(lines) if task_id in line]
    if not hit_indexes:
        return []
    ranges = _merge_ranges([(idx - context, idx + context + 1) for idx in hit_indexes], total=len(lines))
    out: list[str] = []
    for start, end in ranges:
        out.extend(lines[start:end])
    return [line.rstrip("\n") for line in out]


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, tail: int = Query(default=200, ge=1, le=5000)) -> dict[str, Any]:
    """获取指定任务的运行日志（按task_id过滤，默认返回最后200行）。

    在Docker部署下，日志文件默认位于 /var/log/celery/worker.log，
    可通过环境变量 CELERY_LOG_FILE 覆盖。
    """
    try:
        run_id = f"task_logs:{int(datetime.now().timestamp() * 1000)}"
        # region agent log
        _debug_log(
            run_id=run_id,
            hypothesis_id="H6",
            location="api/process.py:get_task_logs:entry",
            message="task_logs entry",
            data={"task_id": task_id, "tail": tail},
        )
        # endregion
        db_job = _resolve_db_job(task_id)
        if db_job is not None:
            is_external = bool(str(db_job.external_provider or "").strip())
            summary_lines = [
                f"task_id={task_id}",
                f"status={db_job.status or 'running'}",
                f"external_provider={db_job.external_provider or '-'}",
                f"external_job_id={db_job.external_job_id or '-'}",
                f"retry_count={db_job.retry_count if db_job.retry_count is not None else '-'}",
            ]
            if db_job.error:
                summary_lines.append(f"error={db_job.error}")
            if is_external:
                summary_lines.append(
                    "logs=External provider task is DB-tracked; Celery worker log stream is not available."
                )
            else:
                summary_lines.append(
                    "logs=DB pseudo task id has no direct Celery log stream; check ETL job params/history."
                )
            return ok(
                {
                    "task_id": task_id,
                    "tail": tail,
                    "filtered": True,
                    "text": "\n".join(summary_lines[-tail:]),
                    "log_file": "db://etl_job_runs",
                    "source": "db",
                }
            )

        log_file = os.getenv("CELERY_LOG_FILE") or "/var/log/celery/worker.log"
        if not os.path.exists(log_file):
            # region agent log
            _debug_log(
                run_id=run_id,
                hypothesis_id="H6",
                location="api/process.py:get_task_logs:missing_log_file",
                message="celery log file not found",
                data={"task_id": task_id, "log_file": log_file},
            )
            # endregion
            state = str(celery_app.AsyncResult(task_id).status or "").upper() or "UNKNOWN"
            summary_lines = [
                f"task_id={task_id}",
                f"status={state}",
                f"log_file={log_file}",
                "logs=Celery worker log file is unavailable in current runtime; configure CELERY_LOG_FILE or check centralized logging.",
            ]
            return ok(
                {
                    "task_id": task_id,
                    "tail": tail,
                    "filtered": False,
                    "text": "\n".join(summary_lines[-tail:]),
                    "log_file": log_file,
                    "source": "unavailable",
                }
            )

        # 为了更大概率匹配到 task_id，先读取较多行再裁剪
        candidate_lines = _tail_file(log_file, max_lines=min(max(2000, tail * 10), 20000))

        # 优先返回 task_id 命中行及其上下文；若无匹配则退化为尾部日志。
        contextual_lines = _extract_context_lines(candidate_lines, task_id, context=20)
        plain_tail_lines = [line.rstrip("\n") for line in candidate_lines[-tail:]]
        if contextual_lines:
            # 对进行中的任务，拼接最新尾部日志，确保页面能持续看到增量变化。
            state = str(celery_app.AsyncResult(task_id).status or "").upper()
            if state in {"PENDING", "STARTED", "RETRY"}:
                merged_lines = (contextual_lines + plain_tail_lines)[-tail:]
                seen = set()
                used_lines = []
                for line in merged_lines:
                    if line in seen:
                        continue
                    seen.add(line)
                    used_lines.append(line)
                used_lines = used_lines[-tail:]
            else:
                used_lines = contextual_lines[-tail:]
            filtered = True
        else:
            used_lines = plain_tail_lines
            filtered = False
        # region agent log
        _debug_log(
            run_id=f"task_logs:{int(datetime.now().timestamp() * 1000)}",
            hypothesis_id="H5",
            location="api/process.py:get_task_logs:filter",
            message="task log selection",
            data={
                "task_id": task_id,
                "tail": tail,
                "filtered": filtered,
                "candidate_lines": len(candidate_lines),
                "contextual_lines": len(contextual_lines),
                "returned_lines": len(used_lines),
            },
        )
        # endregion

        return ok(
            {
                "task_id": task_id,
                "tail": tail,
                "filtered": filtered,
                "text": "\n".join(used_lines),
                "log_file": log_file,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("读取任务日志失败")
        raise HTTPException(status_code=500, detail=f"读取任务日志失败: {str(e)}")
