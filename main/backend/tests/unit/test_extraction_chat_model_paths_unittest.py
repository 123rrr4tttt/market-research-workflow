from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from app.services.extraction import extract as extract_module
from app.services.extraction.models import PolicyExtracted
from app.services.llm.codex_cli import CodexCliChatModel
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.caches import InMemoryCache
from langchain_core.globals import get_llm_cache, set_llm_cache
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel

pytestmark = pytest.mark.unit


@pytest.fixture
def isolated_llm_cache() -> Iterator[None]:
    previous_cache = get_llm_cache()
    set_llm_cache(InMemoryCache())
    try:
        yield
    finally:
        set_llm_cache(previous_cache)


class _StructuredPolicyChat(BaseChatModel):
    structured_schema: object | None = None
    structured_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "structured-policy-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        raise AssertionError("native structured output should handle the invocation")  # noqa: TRY003

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **_kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        assert include_raw is False
        self.structured_schema = schema

        def _invoke(_prompt: LanguageModelInput) -> dict[str, Any]:
            self.structured_calls += 1
            return {
                "state": "CA",
                "effective_date": "2026-01-02",
                "policy_type": "regulation",
                "key_points": ["Native structured result"],
            }

        return RunnableLambda(_invoke)


class _CodexJsonChat(CodexCliChatModel):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def invoke(self, prompt: Any) -> SimpleNamespace:
        self.prompts.append(str(prompt))
        return SimpleNamespace(
            content=(
                '{"state":"NY","effective_date":null,'
                '"policy_type":"bill","key_points":["JSON fallback result"]}'
            )
        )


class _MalformedStructuredPolicyChat(BaseChatModel):
    structured_calls: int = 0
    fallback_calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "malformed-structured-policy-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        self.fallback_calls += 1
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=(
                            '{"state":"WA","effective_date":null,'
                            '"policy_type":"rule","key_points":["Fallback accepted"]}'
                        )
                    )
                )
            ]
        )

    def with_structured_output(
        self,
        schema: dict[str, Any] | type,
        *,
        include_raw: bool = False,
        **_kwargs: Any,
    ) -> Runnable[LanguageModelInput, dict[str, Any] | BaseModel]:
        assert schema is PolicyExtracted
        assert include_raw is False

        def _invoke(_prompt: LanguageModelInput) -> dict[str, Any]:
            self.structured_calls += 1
            return {"effective_date": object()}

        return RunnableLambda(_invoke)


def _no_config(_name: str) -> None:
    return None


def test_policy_extraction_uses_native_base_chat_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _StructuredPolicyChat()
    monkeypatch.setattr(extract_module, "get_llm_config", _no_config)
    monkeypatch.setattr(extract_module, "get_chat_model", lambda: model)

    result = extract_module.extract_policy_info("Policy text. " * 10)

    assert model.structured_schema is PolicyExtracted
    assert model.structured_calls == 1
    assert result == {
        "state": "CA",
        "effective_date": "2026-01-02",
        "policy_type": "regulation",
        "key_points": ["Native structured result"],
    }


def test_policy_extraction_keeps_codex_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _CodexJsonChat()
    monkeypatch.setattr(extract_module, "get_llm_config", _no_config)
    monkeypatch.setattr(extract_module, "get_chat_model", lambda: model)

    result = extract_module.extract_policy_info("Policy text. " * 10)

    assert len(model.prompts) == 1
    assert "JSON" in model.prompts[0]
    assert result == {
        "state": "NY",
        "effective_date": None,
        "policy_type": "bill",
        "key_points": ["JSON fallback result"],
    }


@pytest.mark.usefixtures("isolated_llm_cache")
def test_policy_extraction_rejects_malformed_structured_result_then_uses_json_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _MalformedStructuredPolicyChat()
    monkeypatch.setattr(extract_module, "get_llm_config", _no_config)
    monkeypatch.setattr(extract_module, "get_chat_model", lambda: model)

    result = extract_module.extract_policy_info("Policy text. " * 10)

    assert model.structured_calls == 1
    assert model.fallback_calls == 1
    assert result == {
        "state": "WA",
        "effective_date": None,
        "policy_type": "rule",
        "key_points": ["Fallback accepted"],
    }
