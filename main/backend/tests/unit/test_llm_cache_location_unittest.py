"""Cache placement must respect the configured writable resource boundary."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import pytest


pytestmark = pytest.mark.unit
CACHE_SOURCE = Path(__file__).resolve().parents[2] / "app/services/llm/cache.py"


def load_cache(settings):
    cache_module = ModuleType("langchain_community.cache")
    cache_module.SQLiteCache = Mock()
    globals_module = ModuleType("langchain_core.globals")
    globals_module.set_llm_cache = Mock()
    settings_module = ModuleType("app.settings.config")
    settings_module.settings = settings
    namespace = {"__file__": str(CACHE_SOURCE), "__package__": "app.services.llm"}
    with patch.dict(sys.modules, {
        "langchain_community.cache": cache_module,
        "langchain_core.globals": globals_module,
        "app.settings.config": settings_module,
    }):
        exec(compile(CACHE_SOURCE.read_text(), str(CACHE_SOURCE), "exec"), namespace)
    return cache_module.SQLiteCache, globals_module.set_llm_cache


def test_cache_uses_explicit_writable_location(tmp_path):
    target = tmp_path / "owned-cache" / "llm.sqlite"
    constructor, register = load_cache(SimpleNamespace(
        env="dev", llm_cache_enabled=True, llm_cache_path=str(target)))
    assert target.parent.is_dir()
    constructor.assert_called_once_with(database_path=str(target))
    register.assert_called_once_with(constructor.return_value)


@pytest.mark.parametrize("env,enabled", [("prod", True), ("dev", False)])
def test_disabled_cache_does_not_create_resources(tmp_path, env, enabled):
    target = tmp_path / "must-not-exist" / "llm.sqlite"
    constructor, register = load_cache(SimpleNamespace(
        env=env, llm_cache_enabled=enabled, llm_cache_path=str(target)))
    assert not target.parent.exists()
    constructor.assert_not_called()
    register.assert_not_called()
