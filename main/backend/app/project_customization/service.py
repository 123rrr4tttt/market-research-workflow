from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable

from ..services.projects.context import current_project_key
from .interfaces import ProjectCustomization
from .registry import (
    get_project_customization_factory,
    register_project_customization,
    register_project_customization_prefix,
)

_bootstrapped = False
_INVALID_CUSTOMIZATION_CLASS = "project customization class does not implement ProjectCustomization"


def _ensure_builtin_customizations() -> None:
    global _bootstrapped
    if _bootstrapped:
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
                raw_project_key = _factory_for(customization_cls)().project_key
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
    _bootstrapped = True


def _factory_for(customization_cls: type[object]) -> Callable[[], ProjectCustomization]:
    def _build() -> ProjectCustomization:
        customization = customization_cls()
        if not isinstance(customization, ProjectCustomization):
            # kit:boundary owner=project_customization.service.factory class=PROGRAMMER_DEFECT failure_family=none witness=test:test_project_customization_factory_rejects_invalid_plugin
            raise TypeError(_INVALID_CUSTOMIZATION_CLASS)
        return customization

    return _build


def get_project_customization(project_key: str | None = None) -> ProjectCustomization:
    _ensure_builtin_customizations()
    key = project_key or current_project_key()
    factory = get_project_customization_factory(key)
    customization = factory()
    if not customization.project_key:
        customization.project_key = (key or "").strip().lower()
    return customization
