from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from .defaults import DefaultProjectCustomization
from .interfaces import ProjectCustomization

CustomizationFactory = Callable[[], ProjectCustomization]

_REGISTRY: Dict[str, CustomizationFactory] = {}
_PREFIX_REGISTRY: List[Tuple[str, CustomizationFactory]] = []


def _normalize_project_key(project_key: str | None) -> str:
    key = (project_key or "").strip().lower()
    return key


def register_project_customization(project_key: str, factory: CustomizationFactory) -> None:
    normalized = _normalize_project_key(project_key)
    if not normalized:
        raise ValueError("project_key is required")
    _REGISTRY[normalized] = factory


def register_project_customization_prefix(prefix: str, factory: CustomizationFactory) -> None:
    normalized = _normalize_project_key(prefix)
    if not normalized:
        raise ValueError("prefix is required")
    _PREFIX_REGISTRY.append((normalized, factory))
    _PREFIX_REGISTRY.sort(key=lambda item: len(item[0]), reverse=True)


def get_project_customization_factory(project_key: str | None) -> CustomizationFactory:
    normalized = _normalize_project_key(project_key)
    if normalized in _REGISTRY:
        return _REGISTRY[normalized]
    for prefix, factory in _PREFIX_REGISTRY:
        if normalized.startswith(prefix):
            return factory
    return DefaultProjectCustomization
