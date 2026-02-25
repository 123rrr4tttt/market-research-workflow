from __future__ import annotations

from typing import Any, Dict

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from .provider import get_chat_model
from .prompts import POLICY_CLASSIFICATION_PROMPT, POLICY_SUMMARY_PROMPT


class PolicyClassification(BaseModel):
    category: str = Field(description="允许/限制/禁止/不确定 四类之一")
    confidence: float = Field(ge=0.0, le=1.0, description="模型置信度")
    reason: str = Field(description="简短中文理由")


def build_policy_classification_chain() -> Runnable[Dict[str, Any], PolicyClassification]:
    parser = PydanticOutputParser(pydantic_object=PolicyClassification)
    llm = get_chat_model().with_retry()
    return POLICY_CLASSIFICATION_PROMPT | llm | parser


def build_policy_summary_chain() -> Runnable[Dict[str, Any], str]:
    llm = get_chat_model().with_retry()
    return POLICY_SUMMARY_PROMPT | llm


