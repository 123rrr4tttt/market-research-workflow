"""LLM配置加载服务"""
from __future__ import annotations

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...models.base import SessionLocal
from ...models.entities import LlmServiceConfig
from ...settings.config import settings


def get_llm_config(service_name: str) -> Optional[Dict[str, Any]]:
    """从数据库获取LLM服务配置"""
    try:
        with SessionLocal() as db:
            stmt = select(LlmServiceConfig).where(
                LlmServiceConfig.service_name == service_name,
                LlmServiceConfig.enabled == True
            )
            config = db.execute(stmt).scalar_one_or_none()
            if not config:
                return None
            
            return {
                "service_name": config.service_name,
                "system_prompt": config.system_prompt,
                "user_prompt_template": config.user_prompt_template,
                "model": config.model,
                "temperature": float(config.temperature) if config.temperature else None,
                "max_tokens": config.max_tokens,
                "top_p": float(config.top_p) if config.top_p else None,
                "presence_penalty": float(config.presence_penalty) if config.presence_penalty else None,
                "frequency_penalty": float(config.frequency_penalty) if config.frequency_penalty else None,
            }
    except SQLAlchemyError:
        # table missing / schema not initialized / transient DB issues: fall back to defaults
        return None


def format_prompt_template(template: str, **kwargs) -> str:
    """格式化提示词模板，支持变量替换
    
    模板中使用 {variable} 进行变量替换，使用 {{ 和 }} 来转义大括号
    例如：模板 "谓词必须在 {{regulates, affects}} 中，文本：{text}"
    会被格式化为 "谓词必须在 {regulates, affects} 中，文本：实际文本内容"
    """
    try:
        # Python的format方法会自动处理{{和}}转义
        return template.format(**kwargs)
    except KeyError as e:
        # 如果缺少变量，保留原始占位符
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"format_prompt_template: missing variable {e}, keeping template as-is")
        return template
    except Exception as e:
        # 其他错误也返回原始模板
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"format_prompt_template: error {e}, keeping template as-is")
        return template


def ensure_prompt_has_guidelines(service_name: str, template: Optional[str], guidelines: str) -> Optional[str]:
    """确保指定服务的提示词包含指南文本。

    如果数据库中已存储的提示词缺少指南，则自动追加并返回更新后的内容，
    同时保证多次调用不会重复追加。
    """
    if not guidelines:
        return template

    guidelines_stripped = guidelines.strip()
    if not guidelines_stripped:
        return template

    current_template = template or ""
    if guidelines_stripped in current_template:
        return current_template

    with SessionLocal() as db:
        stmt = select(LlmServiceConfig).where(
            LlmServiceConfig.service_name == service_name,
            LlmServiceConfig.enabled == True,  # noqa: E712
        )
        config = db.execute(stmt).scalar_one_or_none()

        if not config:
            if current_template:
                return f"{current_template.rstrip()}\n\n{guidelines_stripped}"
            return guidelines_stripped

        stored_template = config.user_prompt_template or ""
        if guidelines_stripped in stored_template:
            return stored_template

        if stored_template.strip():
            new_template = f"{stored_template.rstrip()}\n\n{guidelines_stripped}"
        else:
            new_template = guidelines_stripped

        config.user_prompt_template = new_template
        db.add(config)
        db.commit()

        return new_template

