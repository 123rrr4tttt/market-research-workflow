from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Type

from ..services.projects.context import (
    _project_failure,
    _raise_project_failure,
    current_project_key,
)
from .base import SubprojectExtractionAdapter
from .default_adapter import DefaultExtractionAdapter

AdapterType = Type[SubprojectExtractionAdapter]

_EXACT_REGISTRY: Dict[str, AdapterType] = {}
_PREFIX_REGISTRY: Dict[str, AdapterType] = {}
_BOOTSTRAPPED = False


def register_extraction_adapter(project_key: str, adapter_cls: AdapterType) -> None:
    key = (project_key or "").strip().lower()
    if not key:
        _raise_project_failure(
            _project_failure(
                "project_key_required",
                "project_key is required",
                operation="register_extraction_adapter",
                site="app.subprojects.registry.register_extraction_adapter",
                public_exception="ValueError",
            )
        )
    _EXACT_REGISTRY[key] = adapter_cls


def register_extraction_adapter_prefix(prefix: str, adapter_cls: AdapterType) -> None:
    key = (prefix or "").strip().lower()
    if not key:
        _raise_project_failure(
            _project_failure(
                "prefix_required",
                "prefix is required",
                operation="register_extraction_adapter_prefix",
                site="app.subprojects.registry.register_extraction_adapter_prefix",
                public_exception="ValueError",
            )
        )
    _PREFIX_REGISTRY[key] = adapter_cls


def _ensure_builtin_registrations() -> None:
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    package = importlib.import_module(".", __package__)
    for module_info in pkgutil.iter_modules(package.__path__):
        if not module_info.ispkg:
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        adapter_cls = getattr(module, "PROJECT_EXTRACTION_ADAPTER_CLASS", None)
        if adapter_cls is None or not isinstance(adapter_cls, type):
            continue

        project_key = (getattr(module, "PROJECT_KEY", "") or module_info.name).strip().lower()
        if project_key:
            register_extraction_adapter(project_key, adapter_cls)

        for prefix in getattr(module, "PROJECT_KEY_PREFIX_ALIASES", []):
            normalized = (prefix or "").strip().lower()
            if normalized:
                register_extraction_adapter_prefix(normalized, adapter_cls)
    _BOOTSTRAPPED = True


def get_extraction_adapter() -> SubprojectExtractionAdapter:
    _ensure_builtin_registrations()
    key = (current_project_key() or "").strip().lower()
    adapter = _EXACT_REGISTRY.get(key)
    if adapter is not None:
        return adapter()

    for prefix, adapter_cls in _PREFIX_REGISTRY.items():
        if key.startswith(prefix):
            return adapter_cls()

    return DefaultExtractionAdapter()
