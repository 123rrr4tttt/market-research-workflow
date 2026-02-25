from __future__ import annotations

from typing import Any, Dict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .provider import get_chat_model
from .prompts import POLICY_CLASSIFICATION_PROMPT, POLICY_SUMMARY_PROMPT
from .config_loader import get_llm_config, format_prompt_template


class PolicyClassification(BaseModel):
    category: str = Field(description="允许/限制/禁止/不确定 四类之一")
    confidence: float = Field(ge=0.0, le=1.0, description="模型置信度")
    reason: str = Field(description="简短中文理由")


def build_policy_classification_chain() -> Runnable[Dict[str, Any], PolicyClassification]:
    parser = PydanticOutputParser(pydantic_object=PolicyClassification)
    
    # 尝试从数据库读取配置
    config = get_llm_config("policy_classification")
    if config and config.get("system_prompt") and config.get("user_prompt_template"):
        # 使用配置的提示词
        prompt = ChatPromptTemplate.from_messages([
            ("system", config["system_prompt"]),
            ("human", config["user_prompt_template"]),
        ])
        llm = get_chat_model(
            model=config.get("model"),
            temperature=config.get("temperature"),
            max_tokens=config.get("max_tokens"),
            top_p=config.get("top_p"),
            presence_penalty=config.get("presence_penalty"),
            frequency_penalty=config.get("frequency_penalty"),
        ).with_retry()
    else:
        # 使用默认提示词（向后兼容）
        prompt = POLICY_CLASSIFICATION_PROMPT
        llm = get_chat_model().with_retry()
    
    return prompt | llm | parser


def build_policy_summary_chain() -> Runnable[Dict[str, Any], str]:
    # 尝试从数据库读取配置
    config = get_llm_config("policy_summary")
    if config and config.get("system_prompt") and config.get("user_prompt_template"):
        # 使用配置的提示词
        prompt = ChatPromptTemplate.from_messages([
            ("system", config["system_prompt"]),
            ("human", config["user_prompt_template"]),
        ])
        llm = get_chat_model(
            model=config.get("model"),
            temperature=config.get("temperature"),
            max_tokens=config.get("max_tokens"),
            top_p=config.get("top_p"),
            presence_penalty=config.get("presence_penalty"),
            frequency_penalty=config.get("frequency_penalty"),
        ).with_retry()
    else:
        # 使用默认提示词（向后兼容）
        prompt = POLICY_SUMMARY_PROMPT
        llm = get_chat_model().with_retry()
    
    return prompt | llm


