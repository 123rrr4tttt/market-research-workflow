from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


POLICY_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名美国彩票政策分析助手，需要判断输入法案文本对线上彩票 "
            "与代购的态度。请输出 JSON，其中包含 `category`（允许/限制/禁止/不确定）、"
            "`confidence`（0-1 之间的小数）以及 `reason`（中文说明）。",
        ),
        (
            "human",
            "示例：\n《AB 123》允许线上销售。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"允许\",\n  \"confidence\": 0.7,\n  \"reason\": \"法案明确允许线上销售\"\n}",
        ),
        (
            "human",
            "示例：\n《SB 456》禁止第三方代购。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"禁止\",\n  \"confidence\": 0.8,\n  \"reason\": \"法案禁止第三方代购\"\n}",
        ),
        (
            "human",
            "示例：\n《HB 789》未提及线上渠道，仅讨论税率。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"不确定\",\n  \"confidence\": 0.4,\n  \"reason\": \"文本与线上彩票无关\"\n}",
        ),
        (
            "human",
            "当前文本：\n{document}",
        ),
    ]
)


POLICY_SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "请用中文概括输入的政策文本，突出线上彩票与代购的影响，输出 3 条要点列表。",
        ),
        (
            "human",
            "法案内容：\n{document}",
        ),
    ]
)


