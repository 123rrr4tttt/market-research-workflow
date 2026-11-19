"""LLM配置加载服务"""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ...models.base import SessionLocal
from ...models.entities import LlmServiceConfig


class LlmRuntimeConfig(TypedDict):
    service_name: str
    system_prompt: str | None
    user_prompt_template: str | None
    model: str | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    presence_penalty: float | None
    frequency_penalty: float | None


def _optional_nonzero_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if parsed else None


def get_llm_config(service_name: str) -> LlmRuntimeConfig | None:
    """从数据库获取LLM服务配置"""
    try:
        with SessionLocal() as db:
            stmt = select(LlmServiceConfig).where(
                LlmServiceConfig.service_name == service_name, LlmServiceConfig.enabled == True
            )
            config = db.execute(stmt).scalar_one_or_none()
            if not config:
                return None

            return {
                "service_name": config.service_name,
                "system_prompt": config.system_prompt,
                "user_prompt_template": config.user_prompt_template,
                "model": config.model,
                "temperature": _optional_nonzero_float(config.temperature),
                "max_tokens": config.max_tokens,
                "top_p": _optional_nonzero_float(config.top_p),
                "presence_penalty": _optional_nonzero_float(config.presence_penalty),
                "frequency_penalty": _optional_nonzero_float(config.frequency_penalty),
            }
    except SQLAlchemyError:
        # table missing / schema not initialized / transient DB issues: fall back to defaults
        return None


def format_prompt_template(prompt_template: str, /, **kwargs: object) -> str:
    """格式化提示词模板，支持变量替换

    模板中使用 {variable} 进行变量替换，使用 {{ 和 }} 来转义大括号
    例如：模板 "谓词必须在 {{regulates, affects}} 中，文本：{text}"
    会被格式化为 "谓词必须在 {regulates, affects} 中，文本：实际文本内容"
    """
    try:
        # Python的format方法会自动处理{{和}}转义
        return prompt_template.format(**kwargs)
    except KeyError as e:
        # 如果缺少变量，保留原始占位符
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"format_prompt_template: missing variable {e}, keeping template as-is")
        return prompt_template
    except Exception as e:
        # 其他错误也返回原始模板
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"format_prompt_template: error {e}, keeping template as-is")
        return prompt_template
