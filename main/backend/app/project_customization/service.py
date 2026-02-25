from __future__ import annotations

import importlib
import pkgutil
from typing import Type

from ..services.projects.context import current_project_key
from .interfaces import ProjectCustomization
from .registry import (
    get_project_customization_factory,
    register_project_customization,
    register_project_customization_prefix,
)

_BOOTSTRAPPED = False


def _ensure_builtin_customizations() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    package = importlib.import_module(".projects", __package__)
    for module_info in pkgutil.iter_modules(package.__path__):
        if not module_info.ispkg:
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        customization_cls = getattr(module, "PROJECT_CUSTOMIZATION_CLASS", None)
        if customization_cls is None or not isinstance(customization_cls, type):
            continue

        raw_project_key = getattr(module, "PROJECT_KEY", None)
        if not raw_project_key:
            try:
                raw_project_key = getattr(customization_cls(), "project_key", "")
            except Exception:
                raw_project_key = ""
        project_key = (str(raw_project_key or "") or module_info.name).strip().lower()
        if not project_key:
            continue
        register_project_customization(project_key, _factory_for(customization_cls))

        for prefix in getattr(module, "PROJECT_KEY_PREFIX_ALIASES", []):
            normalized = (prefix or "").strip().lower()
            if normalized:
                register_project_customization_prefix(normalized, _factory_for(customization_cls))
    _BOOTSTRAPPED = True


def _factory_for(customization_cls: Type[ProjectCustomization]):
    def _build() -> ProjectCustomization:
        return customization_cls()

    return _build


def get_project_customization(project_key: str | None = None) -> ProjectCustomization:
    _ensure_builtin_customizations()
    key = project_key or current_project_key()
    factory = get_project_customization_factory(key)
    customization = factory()
    if not getattr(customization, "project_key", ""):
        customization.project_key = (key or "").strip().lower()  # type: ignore[attr-defined]
    return customization
