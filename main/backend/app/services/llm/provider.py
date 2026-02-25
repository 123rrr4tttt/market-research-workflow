from typing import Any, Optional

from . import cache  # noqa: F401  # ensure cache setup on import
from .adapters import LangChainProviderAdapter
from .ports import ChatModelOptions


_PROVIDER_ADAPTER = LangChainProviderAdapter()


def get_chat_model(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    **kwargs
):
    """获取聊天模型，支持从配置读取参数
    
    Args:
        model: 模型名称，如果为None则使用默认模型
        temperature: 温度参数，如果为None则使用默认值0.2
        max_tokens: 最大token数
        top_p: top_p参数
        presence_penalty: presence_penalty参数
        frequency_penalty: frequency_penalty参数
        **kwargs: 其他参数
    """
    options = ChatModelOptions(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        extra=kwargs or {},
    )
    return _PROVIDER_ADAPTER.get_chat_model(options)


def get_embeddings(model: Optional[str] = None):
    return _PROVIDER_ADAPTER.get_embeddings(model=model)


