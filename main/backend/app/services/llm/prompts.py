from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate


POLICY_CLASSIFICATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是一名商业政策分析助手，需要判断输入法案/政策文本对相关商业活动的态度。"
            "请输出 JSON，其中包含 `category`（允许/限制/禁止/不确定）、"
            "`confidence`（0-1 之间的小数）以及 `reason`（中文说明）。",
        ),
        (
            "human",
            "示例：\n某法案允许相关业务开展。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"允许\",\n  \"confidence\": 0.7,\n  \"reason\": \"法案明确允许相关业务\"\n}",
        ),
        (
            "human",
            "示例：\n某法案禁止第三方代理。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"禁止\",\n  \"confidence\": 0.8,\n  \"reason\": \"法案禁止第三方代理\"\n}",
        ),
        (
            "human",
            "示例：\n某法案未提及相关渠道，仅讨论税率。",
        ),
        (
            "assistant",
            "{\n  \"category\": \"不确定\",\n  \"confidence\": 0.4,\n  \"reason\": \"文本与业务主题无关\"\n}",
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
            "请用中文概括输入的政策文本，突出对相关商业活动的影响，输出 3 条要点列表。",
        ),
        (
            "human",
            "法案内容：\n{document}",
        ),
    ]
)


