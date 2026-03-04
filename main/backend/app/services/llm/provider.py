from typing import Any, Optional, Dict
from types import SimpleNamespace

from . import cache  # noqa: F401  # ensure cache setup on import
from .adapters import LangChainProviderAdapter
from .ports import ChatModelOptions
from ...settings.config import settings

# Lazy imports used by the LiteLLM (OpenAI-compatible) path
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


# Provider adapter selection:
# - If llm_provider == 'litellm', use inline LiteLLM (OpenAI-compatible) branch.
# - Otherwise, keep using LangChainProviderAdapter for openai/azure/ollama.
_PROVIDER_ADAPTER = (
    None if (settings.llm_provider or "").lower() == "litellm" else LangChainProviderAdapter()
)


def get_chat_model(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    **kwargs: Any,
):
    """获取聊天模型；当 provider 为 'litellm' 时静态绑定到 OpenAI 兼容端点。

    - litellm: 直接返回 `langchain_openai.ChatOpenAI`，使用
      `base_url=settings.litellm_api_base`、`api_key=settings.litellm_api_key or ''`。
    - 其他(openai/azure/ollama): 透传到 `LangChainProviderAdapter` 以保持最小改动。
    """
    provider = (settings.llm_provider or "").lower()

    # Build common model params
    default_temperature = 0.2 if temperature is None else temperature
    model_params: Dict[str, Any] = {"temperature": default_temperature}
    if max_tokens is not None:
        model_params["max_tokens"] = max_tokens
    if top_p is not None:
        model_params["top_p"] = top_p
    if presence_penalty is not None:
        model_params["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        model_params["frequency_penalty"] = frequency_penalty
    if kwargs:
        model_params.update(kwargs)

    if provider == "litellm":
        # Use OpenAI-compatible endpoint served by LiteLLM
        base_url = getattr(settings, "litellm_api_base", None)
        api_key = getattr(settings, "litellm_api_key", "") or ""
        return ChatOpenAI(
            model=model or "gpt-4o-mini",
            base_url=base_url or None,
            api_key=api_key,
            **model_params,
        )

    # Fallback to existing adapter paths (openai/azure/ollama)
    options = ChatModelOptions(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        extra=kwargs or {},
    )
    # _PROVIDER_ADAPTER is guaranteed non-None on non-litellm providers
    return _PROVIDER_ADAPTER.get_chat_model(options)  # type: ignore[union-attr]


def get_embeddings(model: Optional[str] = None):
    provider = (settings.llm_provider or "").lower()
    if provider == "litellm":
        base_url = getattr(settings, "litellm_api_base", None)
        api_key = getattr(settings, "litellm_api_key", "") or ""
        return OpenAIEmbeddings(
            model=model or settings.embedding_model,
            base_url=base_url or None,
            api_key=api_key,
        )
    # Other providers via adapter
    return _PROVIDER_ADAPTER.get_embeddings(model=model)  # type: ignore[union-attr]


def get_local_fallback_chat(
    model: Optional[str] = None,
    temperature: float = 0.0,
    **kwargs: Any,
):
    """返回轻量本地兜底 Chat 对象。

    - 具备 `.invoke(prompt) -> SimpleNamespace(content=...)`
    - 具备 `.with_retry() -> self`
    - 不参与 chains 组合，业务可直接按需调用
    """
    provider = (settings.llm_provider or "").lower()

    if provider == "litellm":
        base_url = getattr(settings, "litellm_api_base", None)
        api_key = getattr(settings, "litellm_api_key", "") or ""
        inner = ChatOpenAI(
            model=model or "gpt-4o-mini",
            base_url=base_url or None,
            api_key=api_key,
            temperature=temperature,
            **kwargs,
        )
    else:
        options = ChatModelOptions(
            model=model,
            temperature=temperature,
            extra=kwargs or {},
        )
        inner = _PROVIDER_ADAPTER.get_chat_model(options)  # type: ignore[union-attr]

    class _LightChat:
        def __init__(self, chat: Any):
            self._chat = chat

        def with_retry(self):
            return self

        def invoke(self, prompt: Any):
            resp = self._chat.invoke(prompt)
            content = getattr(resp, "content", None)
            if content is None:
                if isinstance(resp, dict) and "content" in resp:
                    content = resp["content"]
                else:
                    content = str(resp)
            return SimpleNamespace(content=content)

    return _LightChat(inner)

