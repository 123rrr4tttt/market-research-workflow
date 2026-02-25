"""LLM服务配置API"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.base import SessionLocal, get_db
from ..models.entities import LlmServiceConfig, Project
from ..services.llm.config_service import LlmConfigService
from ..contracts import success_response
from ..services.projects.context import bind_project, bind_schema, _normalize_project_key


router = APIRouter(prefix="/llm-config", tags=["llm-config"])
llm_config_service = LlmConfigService()


class LlmServiceConfigCreate(BaseModel):
    service_name: str
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    enabled: bool = True


class LlmServiceConfigUpdate(BaseModel):
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt_template: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    enabled: Optional[bool] = None


class LlmServiceConfigResponse(BaseModel):
    id: int
    service_name: str
    description: Optional[str]
    system_prompt: Optional[str]
    user_prompt_template: Optional[str]
    model: Optional[str]
    temperature: Optional[float]
    max_tokens: Optional[int]
    top_p: Optional[float]
    presence_penalty: Optional[float]
    frequency_penalty: Optional[float]
    enabled: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True
    
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建响应模型，确保日期时间转换为字符串"""
        data = {
            "id": obj.id,
            "service_name": obj.service_name,
            "description": obj.description,
            "system_prompt": obj.system_prompt,
            "user_prompt_template": obj.user_prompt_template,
            "model": obj.model,
            "temperature": float(obj.temperature) if obj.temperature else None,
            "max_tokens": obj.max_tokens,
            "top_p": float(obj.top_p) if obj.top_p else None,
            "presence_penalty": float(obj.presence_penalty) if obj.presence_penalty else None,
            "frequency_penalty": float(obj.frequency_penalty) if obj.frequency_penalty else None,
            "enabled": obj.enabled,
            "created_at": obj.created_at.isoformat() if obj.created_at else "",
            "updated_at": obj.updated_at.isoformat() if obj.updated_at else "",
        }
        return cls(**data)


class CopyLlmConfigsRequest(BaseModel):
    source_project_key: str
    overwrite: bool = False


def _assert_project_exists(project_key: str) -> str:
    normalized = _normalize_project_key(project_key)
    with bind_schema("public"):
        with SessionLocal() as session:
            project = session.execute(
                select(Project).where(Project.project_key == normalized, Project.enabled == True)  # noqa: E712
            ).scalar_one_or_none()
            if project is None:
                raise HTTPException(status_code=404, detail=f"项目 '{normalized}' 不存在或已禁用")
    return normalized


def _serialize_configs(configs: list[LlmServiceConfig]) -> list[dict]:
    return [LlmServiceConfigResponse.from_orm(c).model_dump() for c in configs]


def _copy_configs_between_projects(
    source_project_key: str,
    target_project_key: str,
    overwrite: bool,
) -> dict:
    source = _assert_project_exists(source_project_key)
    target = _assert_project_exists(target_project_key)
    if source == target:
        raise HTTPException(status_code=400, detail="源项目与目标项目不能相同")

    copied = 0
    skipped = 0
    with bind_project(source):
        with SessionLocal() as source_db:
            source_configs = llm_config_service.list_configs(source_db)

    with bind_project(target):
        with SessionLocal() as target_db:
            for item in source_configs:
                payload = {
                    "description": item.description,
                    "system_prompt": item.system_prompt,
                    "user_prompt_template": item.user_prompt_template,
                    "model": item.model,
                    "temperature": float(item.temperature) if item.temperature is not None else None,
                    "max_tokens": item.max_tokens,
                    "top_p": float(item.top_p) if item.top_p is not None else None,
                    "presence_penalty": float(item.presence_penalty) if item.presence_penalty is not None else None,
                    "frequency_penalty": float(item.frequency_penalty) if item.frequency_penalty is not None else None,
                    "enabled": item.enabled,
                }
                existing = llm_config_service.get_config(target_db, item.service_name)
                if existing and not overwrite:
                    skipped += 1
                    continue
                llm_config_service.upsert_config(target_db, item.service_name, payload)
                copied += 1

    return {
        "source_project_key": source,
        "target_project_key": target,
        "copied": copied,
        "skipped": skipped,
        "overwrite": overwrite,
    }


@router.get("")
def list_llm_configs(db: Session = Depends(get_db)):
    """获取所有LLM服务配置"""
    configs = llm_config_service.list_configs(db)
    return success_response([LlmServiceConfigResponse.from_orm(c).model_dump() for c in configs])


@router.get("/service/{service_name}")
def get_llm_config(service_name: str, db: Session = Depends(get_db)):
    """获取指定服务配置"""
    config = llm_config_service.get_config(db, service_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"服务配置 '{service_name}' 不存在")
    return success_response(LlmServiceConfigResponse.from_orm(config).model_dump())


@router.post("")
def create_llm_config(config: LlmServiceConfigCreate, db: Session = Depends(get_db)):
    """创建新的LLM服务配置"""
    # 检查是否已存在
    existing = llm_config_service.get_config(db, config.service_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"服务配置 '{config.service_name}' 已存在")
    db_config = llm_config_service.create_config(db, config.model_dump())
    return success_response(LlmServiceConfigResponse.from_orm(db_config).model_dump())


@router.put("/service/{service_name}")
def update_llm_config(
    service_name: str,
    config: LlmServiceConfigUpdate,
    db: Session = Depends(get_db)
):
    """更新LLM服务配置"""
    db_config = llm_config_service.get_config(db, service_name)
    if not db_config:
        raise HTTPException(status_code=404, detail=f"服务配置 '{service_name}' 不存在")
    update_data = config.model_dump(exclude_unset=True)
    db_config = llm_config_service.update_config(db, db_config, update_data)
    return success_response(LlmServiceConfigResponse.from_orm(db_config).model_dump())


@router.delete("/service/{service_name}")
def delete_llm_config(service_name: str, db: Session = Depends(get_db)):
    """删除LLM服务配置"""
    db_config = llm_config_service.get_config(db, service_name)
    if not db_config:
        raise HTTPException(status_code=404, detail=f"服务配置 '{service_name}' 不存在")
    llm_config_service.delete_config(db, db_config)
    return success_response({"message": f"服务配置 '{service_name}' 已删除"})


@router.get("/projects/{project_key}")
def list_llm_configs_by_project(project_key: str):
    normalized = _assert_project_exists(project_key)
    with bind_project(normalized):
        with SessionLocal() as db:
            configs = llm_config_service.list_configs(db)
            return success_response(
                {
                    "project_key": normalized,
                    "items": _serialize_configs(configs),
                }
            )


@router.get("/projects/{project_key}/{service_name}")
def get_llm_config_by_project(project_key: str, service_name: str):
    normalized = _assert_project_exists(project_key)
    with bind_project(normalized):
        with SessionLocal() as db:
            config = llm_config_service.get_config(db, service_name)
            if not config:
                raise HTTPException(status_code=404, detail=f"项目 '{normalized}' 下服务配置 '{service_name}' 不存在")
            return success_response(
                {
                    "project_key": normalized,
                    "item": LlmServiceConfigResponse.from_orm(config).model_dump(),
                }
            )


@router.post("/projects/{project_key}")
def create_llm_config_by_project(project_key: str, config: LlmServiceConfigCreate):
    normalized = _assert_project_exists(project_key)
    with bind_project(normalized):
        with SessionLocal() as db:
            existing = llm_config_service.get_config(db, config.service_name)
            if existing:
                raise HTTPException(status_code=400, detail=f"项目 '{normalized}' 下服务配置 '{config.service_name}' 已存在")
            created = llm_config_service.create_config(db, config.model_dump())
            return success_response(
                {
                    "project_key": normalized,
                    "item": LlmServiceConfigResponse.from_orm(created).model_dump(),
                }
            )


@router.put("/projects/{project_key}/{service_name}")
def upsert_llm_config_by_project(project_key: str, service_name: str, config: LlmServiceConfigUpdate):
    normalized = _assert_project_exists(project_key)
    with bind_project(normalized):
        with SessionLocal() as db:
            item = llm_config_service.upsert_config(db, service_name, config.model_dump(exclude_unset=True))
            return success_response(
                {
                    "project_key": normalized,
                    "item": LlmServiceConfigResponse.from_orm(item).model_dump(),
                }
            )


@router.delete("/projects/{project_key}/{service_name}")
def delete_llm_config_by_project(project_key: str, service_name: str):
    normalized = _assert_project_exists(project_key)
    with bind_project(normalized):
        with SessionLocal() as db:
            config = llm_config_service.get_config(db, service_name)
            if not config:
                raise HTTPException(status_code=404, detail=f"项目 '{normalized}' 下服务配置 '{service_name}' 不存在")
            llm_config_service.delete_config(db, config)
            return success_response(
                {
                    "project_key": normalized,
                    "message": f"项目 '{normalized}' 的服务配置 '{service_name}' 已删除",
                }
            )


@router.post("/projects/{project_key}/copy-from")
def copy_llm_configs_to_project(project_key: str, payload: CopyLlmConfigsRequest):
    result = _copy_configs_between_projects(
        source_project_key=payload.source_project_key,
        target_project_key=project_key,
        overwrite=payload.overwrite,
    )
    return success_response(result)


# Backward-compatible aliases for legacy endpoints
@router.get("/{service_name}")
def get_llm_config_legacy(service_name: str, db: Session = Depends(get_db)):
    return get_llm_config(service_name=service_name, db=db)


@router.put("/{service_name}")
def update_llm_config_legacy(service_name: str, config: LlmServiceConfigUpdate, db: Session = Depends(get_db)):
    return update_llm_config(service_name=service_name, config=config, db=db)


@router.delete("/{service_name}")
def delete_llm_config_legacy(service_name: str, db: Session = Depends(get_db)):
    return delete_llm_config(service_name=service_name, db=db)

