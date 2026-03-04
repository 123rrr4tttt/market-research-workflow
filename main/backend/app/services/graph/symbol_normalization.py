"""Extensible symbol normalization rule engine."""
from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

_WHITESPACE_RE = re.compile(r"\s+")


class SymbolRule(Protocol):
    """Protocol for a symbol normalization rule."""

    rule_id: str

    def apply(self, value: str, context: Mapping[str, Any] | None = None) -> str:
        """Transform the input symbol and return normalized output."""


class BaseSymbolRule(ABC):
    """Base class for concrete symbol normalization rules."""

    rule_id: str = ""

    @abstractmethod
    def apply(self, value: str, context: Mapping[str, Any] | None = None) -> str:
        raise NotImplementedError


class TrimCasefoldRule(BaseSymbolRule):
    """Trim surrounding spaces and normalize case."""

    rule_id = "trim_casefold"

    def apply(self, value: str, context: Mapping[str, Any] | None = None) -> str:
        normalized = unicodedata.normalize("NFKC", value or "")
        normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
        return normalized.casefold()


class PunctuationNormalizeRule(BaseSymbolRule):
    """Normalize punctuation variants to ASCII-friendly forms."""

    rule_id = "punctuation_normalize"
    _TRANSLATION = str.maketrans(
        {
            "，": ",",
            "。": ".",
            "：": ":",
            "；": ";",
            "（": "(",
            "）": ")",
            "【": "[",
            "】": "]",
            "、": ",",
            "！": "!",
            "？": "?",
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "－": "-",
            "—": "-",
            "–": "-",
            "／": "/",
            "·": ".",
        }
    )

    def apply(self, value: str, context: Mapping[str, Any] | None = None) -> str:
        normalized = unicodedata.normalize("NFKC", value or "")
        return normalized.translate(self._TRANSLATION)


@dataclass
class RuleRegistry:
    """Registry that maps rule IDs to factories."""

    _factories: dict[str, Callable[[], SymbolRule]] = field(default_factory=dict)

    def register(self, rule_id: str, factory: Callable[[], SymbolRule], *, overwrite: bool = False) -> None:
        key = str(rule_id or "").strip()
        if not key:
            raise ValueError("rule_id must not be empty")
        if key in self._factories and not overwrite:
            raise ValueError(f"rule already registered: {key}")
        self._factories[key] = factory

    def create(self, rule_id: str) -> SymbolRule:
        try:
            return self._factories[rule_id]()
        except KeyError as exc:
            raise KeyError(f"unknown symbol rule id: {rule_id}") from exc

    def has(self, rule_id: str) -> bool:
        return rule_id in self._factories

    def available_rule_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories.keys()))


def default_rule_registry() -> RuleRegistry:
    registry = RuleRegistry()
    registry.register(TrimCasefoldRule.rule_id, TrimCasefoldRule)
    registry.register(PunctuationNormalizeRule.rule_id, PunctuationNormalizeRule)
    return registry


@dataclass
class SymbolRuleExecutorConfig:
    """Config for symbol rule chain execution."""

    default_rule_ids: list[str] = field(default_factory=lambda: ["trim_casefold", "punctuation_normalize"])


class SymbolRuleExecutor:
    """Apply configured symbol normalization rules sequentially."""

    def __init__(
        self,
        config: SymbolRuleExecutorConfig | None = None,
        registry: RuleRegistry | None = None,
    ) -> None:
        self._config = config or SymbolRuleExecutorConfig()
        self._registry = registry or default_rule_registry()

    @property
    def registry(self) -> RuleRegistry:
        return self._registry

    def normalize(
        self,
        value: str | None,
        *,
        rule_ids: list[str] | tuple[str, ...] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> str:
        current = "" if value is None else str(value)
        chain = list(rule_ids) if rule_ids is not None else list(self._config.default_rule_ids)
        for rule_id in chain:
            rule = self._registry.create(rule_id)
            current = rule.apply(current, context=context)
        return current


def normalize_symbol(
    value: str | None,
    *,
    config: SymbolRuleExecutorConfig | None = None,
    registry: RuleRegistry | None = None,
    rule_ids: list[str] | tuple[str, ...] | None = None,
    context: Mapping[str, Any] | None = None,
) -> str:
    """Convenience API for one-off symbol normalization."""
    executor = SymbolRuleExecutor(config=config, registry=registry)
    return executor.normalize(value, rule_ids=rule_ids, context=context)
