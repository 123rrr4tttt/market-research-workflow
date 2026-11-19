from __future__ import annotations

from typing import Annotated, Any

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from .codex_cli import CodexCliChatModel
from .provider import get_chat_model
from .prompts import POLICY_CLASSIFICATION_PROMPT, POLICY_SUMMARY_PROMPT
from .config_loader import get_llm_config


class PolicyClassification(BaseModel):
    category: str = Field(description="允许/限制/禁止/不确定 四类之一")
    confidence: float = Field(ge=0.0, le=1.0, description="模型置信度")
    reason: str = Field(description="简短中文理由")


def _retrying_chat_runnable(
    model: BaseChatModel | CodexCliChatModel,
) -> Runnable[LanguageModelInput, BaseMessage | str]:
    if isinstance(model, CodexCliChatModel):

        def invoke_codex(prompt: LanguageModelInput) -> str:
            return str(model.invoke(prompt).content)

        return RunnableLambda(invoke_codex).with_retry()
    return model.with_retry()


def build_policy_classification_chain() -> Annotated[
    Runnable[dict[str, Any], PolicyClassification],
    "kit:prepared-command effect_boundary=llm.chains witness=test:test_derived_service_annotations_match_fact_sources",
]:
    parser = PydanticOutputParser(pydantic_object=PolicyClassification)

    # 尝试从数据库读取配置
    config = get_llm_config("policy_classification")
    system_prompt = config.get("system_prompt") if config else None
    user_prompt_template = config.get("user_prompt_template") if config else None
    if config and system_prompt and user_prompt_template:
        # 使用配置的提示词
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", user_prompt_template),
            ]
        )
        llm = _retrying_chat_runnable(
            get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        )
    else:
        # 使用默认提示词（向后兼容）
        prompt = POLICY_CLASSIFICATION_PROMPT
        llm = _retrying_chat_runnable(get_chat_model())

    return prompt | llm | parser


def build_policy_summary_chain() -> Annotated[
    Runnable[dict[str, Any], str],
    "kit:prepared-command effect_boundary=llm.chains witness=test:test_derived_service_annotations_match_fact_sources",
]:
    # 尝试从数据库读取配置
    config = get_llm_config("policy_summary")
    system_prompt = config.get("system_prompt") if config else None
    user_prompt_template = config.get("user_prompt_template") if config else None
    if config and system_prompt and user_prompt_template:
        # 使用配置的提示词
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", user_prompt_template),
            ]
        )
        llm = _retrying_chat_runnable(
            get_chat_model(
                model=config.get("model"),
                temperature=config.get("temperature"),
                max_tokens=config.get("max_tokens"),
                top_p=config.get("top_p"),
                presence_penalty=config.get("presence_penalty"),
                frequency_penalty=config.get("frequency_penalty"),
            )
        )
    else:
        # 使用默认提示词（向后兼容）
        prompt = POLICY_SUMMARY_PROMPT
        llm = _retrying_chat_runnable(get_chat_model())

    return prompt | llm | StrOutputParser()
