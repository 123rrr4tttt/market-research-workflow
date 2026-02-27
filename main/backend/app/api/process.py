"""任务进程管理API - 管理Celery任务"""
from __future__ import annotations

import logging
from contextlib import nullcontext
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
import os
from collections import deque
from pydantic import BaseModel
from sqlalchemy import select, func

from ..celery_app import celery_app
from ..models.base import SessionLocal
from ..models.entities import EtlJobRun
from ..services.projects import bind_project

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/process", tags=["process"])


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
) -> TaskListResponse:
    """获取Celery任务列表"""
    try:
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

        return TaskListResponse(
            tasks=tasks,
            stats=stats
        )

    except Exception as e:
        logger.exception("获取任务列表失败")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.get("/stats")
def get_task_stats() -> dict:
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
        
        return {
            'active_tasks': active_count,
            'scheduled_tasks': scheduled_count,
            'reserved_tasks': reserved_count,
            'total_running': active_count + scheduled_count + reserved_count,
            'registered_task_types': len(registered_task_names),
            'workers': len(workers),
            'worker_names': workers,
        }

    except Exception as e:
        logger.exception("获取任务统计信息失败")
        raise HTTPException(status_code=500, detail=f"获取任务统计信息失败: {str(e)}")


@router.get("/history")
def get_task_history(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[str] = Query(None, description="任务状态过滤: completed, failed, running"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    project_key: Optional[str] = Query(None, description="项目标识（用于查询对应项目 schema 的任务历史）"),
) -> dict:
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
                query = query.order_by(EtlJobRun.started_at.desc().nullslast()).limit(limit)
            
                jobs = session.execute(query).scalars().all()
            
            # 转换为字典格式
                history = []
                for job in jobs:
                    duration = None
                    if job.started_at and job.finished_at:
                        duration = (job.finished_at - job.started_at).total_seconds()
                    elif job.started_at:
                        duration = (datetime.now(job.started_at.tzinfo) - job.started_at).total_seconds()

                    history.append({
                        "id": job.id,
                        "job_type": job.job_type,
                        "status": job.status,
                        "params": job.params or {},
                        "display_meta": extract_display_meta_from_params(job.params or {}),
                        "started_at": job.started_at.isoformat() if job.started_at else None,
                        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                        "duration_seconds": duration,
                        "error": job.error,
                    })
            
            # 获取统计信息
                total_query = select(func.count(EtlJobRun.id))
                if status:
                    total_query = total_query.where(EtlJobRun.status == status)
                if job_type:
                    total_query = total_query.where(EtlJobRun.job_type == job_type)
                total = session.execute(total_query).scalar() or 0
            
            # 按状态统计
                status_stats = {}
                status_query = select(
                    EtlJobRun.status,
                    func.count(EtlJobRun.id).label("count")
                )
                if job_type:
                    status_query = status_query.where(EtlJobRun.job_type == job_type)
                status_query = status_query.group_by(EtlJobRun.status)
                for row in session.execute(status_query).all():
                    status_stats[row.status] = row.count

                return {
                    "history": history,
                    "total": total,
                    "status_stats": status_stats,
                    "project_key": project_key,
                }

    except Exception as e:
        logger.exception("获取任务历史记录失败")
        raise HTTPException(status_code=500, detail=f"获取任务历史记录失败: {str(e)}")


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str, terminate: bool = False) -> dict:
    """取消指定任务"""
    try:
        # 撤销任务
        celery_app.control.revoke(task_id, terminate=terminate)
        
        action = "强制终止" if terminate else "取消"
        
        return {
            "success": True,
            "message": f"任务 {task_id} 已{action}",
            "task_id": task_id
        }

    except Exception as e:
        logger.exception(f"取消任务 {task_id} 失败")
        raise HTTPException(status_code=500, detail=f"取消任务失败: {str(e)}")


@router.get("/{task_id}")
def get_task_info(task_id: str) -> dict:
    """获取任务详细信息"""
    try:
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
        
        # 尝试获取任务名称
        try:
            task_info["name"] = result.name
        except:
            task_info["name"] = "unknown"
        
        return task_info

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


@router.get("/{task_id}/logs")
def get_task_logs(task_id: str, tail: int = Query(default=200, ge=1, le=5000)) -> dict:
    """获取指定任务的运行日志（按task_id过滤，默认返回最后200行）。

    在Docker部署下，日志文件默认位于 /var/log/celery/worker.log，
    可通过环境变量 CELERY_LOG_FILE 覆盖。
    """
    try:
        log_file = os.getenv("CELERY_LOG_FILE") or "/var/log/celery/worker.log"
        if not os.path.exists(log_file):
            raise HTTPException(status_code=404, detail="日志文件不存在或未挂载")

        # 为了更大概率匹配到 task_id，先读取较多行再裁剪
        candidate_lines = _tail_file(log_file, max_lines=min(max(2000, tail * 10), 20000))

        # 先按 task_id 过滤；若无匹配，则退化为直接尾部日志
        filtered_lines = [line.rstrip("\n") for line in candidate_lines if task_id in line]
        if filtered_lines:
            used_lines = filtered_lines[-tail:]
            filtered = True
        else:
            used_lines = [line.rstrip("\n") for line in candidate_lines[-tail:]]
            filtered = False

        return {
            "task_id": task_id,
            "tail": tail,
            "filtered": filtered,
            "text": "\n".join(used_lines),
            "log_file": log_file,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("读取任务日志失败")
        raise HTTPException(status_code=500, detail=f"读取任务日志失败: {str(e)}")
