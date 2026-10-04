from __future__ import annotations

import ast
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mrw_functorial_kit.core.provider_port_failures import (
    collect_runtime_failures,
    crawler_registry_contract_failures,
    ingest_google_news_failures,
    ingest_policy_failures,
    ingest_reddit_failures,
    resource_pool_http_fetch_failures,
    resource_pool_official_access_failures,
    source_library_crawler_provider_resolution_failures,
)


ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "main/backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

_FAMILIES = {
    family.name: family
    for family in (
        ingest_policy_failures,
        ingest_reddit_failures,
        ingest_google_news_failures,
        resource_pool_http_fetch_failures,
        resource_pool_official_access_failures,
        source_library_crawler_provider_resolution_failures,
        collect_runtime_failures,
        crawler_registry_contract_failures,
    )
}


@pytest.fixture(scope="module", autouse=True)
def _isolate_llm_cache_effect(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """Keep import-time LLM cache initialization inside the test temp root."""
    from app.settings.config import settings
    from langchain_core.globals import get_llm_cache, set_llm_cache

    previous_cache = get_llm_cache()
    previous_env = settings.env
    settings.env = "prod"
    try:
        from app.services.llm import cache as llm_cache
    finally:
        settings.env = previous_env

    previous_cache_file = llm_cache._CACHE_FILE
    llm_cache._CACHE_FILE = (
        tmp_path_factory.mktemp("provider-port-llm-cache") / "langchain-cache.db"
    )
    try:
        llm_cache.setup_cache()
        yield
    finally:
        set_llm_cache(previous_cache)
        llm_cache._CACHE_FILE = previous_cache_file
        settings.env = previous_env


def _parse(relative_path: str) -> ast.Module:
    return ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"missing function: {name}")


def _constant_raises(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    messages: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
            continue
        if not node.exc.args:
            continue
        literal = node.exc.args[0]
        if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
            messages.add(literal.value)
    return messages


def test_INVARIANT__provider_port_failure_families_match_registry() -> None:
    entries = json.loads((ROOT / "registries/failures.json").read_text(encoding="utf-8"))[
        "entries"
    ]
    registered = {entry["name"]: tuple(entry["codes"]) for entry in entries}
    assert set(registered) >= set(_FAMILIES)
    for name, family in _FAMILIES.items():
        assert registered[name] == family.codes


def test_FAILURE_PRESERVED__provider_port_failure_families_are_closed() -> None:
    for family in _FAMILIES.values():
        for code in family.codes:
            failure = family.fail(code, f"closed member {code}")
            assert family.matches(failure)
        with pytest.raises(ValueError, match="unknown code"):
            family.fail("unregistered", "not an observable failure")


def test_FAILURE_PRESERVED__ingest_provider_adapters_fail_closed_by_boundary() -> None:
    from app.services.ingest import provider_ports

    boundaries = (
        ("_POLICY_ADAPTER_RESOLVER", "get_policy_adapter", "policy adapter provider"),
        ("_REDDIT_ADAPTER_FACTORY", "get_reddit_adapter", "Reddit adapter provider"),
        (
            "_GOOGLE_NEWS_ADAPTER_FACTORY",
            "get_google_news_adapter",
            "Google News adapter provider",
        ),
    )
    original = {attribute: getattr(provider_ports, attribute) for attribute, _, _ in boundaries}
    try:
        for attribute, accessor, message in boundaries:
            setattr(provider_ports, attribute, None)
            with pytest.raises(RuntimeError, match=message):
                if accessor == "get_policy_adapter":
                    getattr(provider_ports, accessor)("CA")
                else:
                    getattr(provider_ports, accessor)()
    finally:
        for attribute, value in original.items():
            setattr(provider_ports, attribute, value)


def _assert_lazy_iteration_precedes_job_start(
    relative_path: str,
    function_name: str,
    iteration_expression: str,
    job_expression: str,
) -> None:
    function = _function(_parse(relative_path), function_name)
    source = ast.unparse(function)
    assert iteration_expression in source
    assert job_expression in source
    assert source.index(iteration_expression) < source.index(job_expression)


def test_FAILURE_PRESERVED__policy_lazy_iteration_remains_observable() -> None:
    _assert_lazy_iteration_precedes_job_start(
        "main/backend/app/services/ingest/policy.py",
        "ingest_policy_documents",
        "materialize_policy_documents(adapter.fetch_documents()",
        "start_job('ingest_policy', {'state': state})",
    )


class _ExplodingIterable:
    def __iter__(self):
        raise RuntimeError("provider iteration failed")


def _unexpected_job_start(*_args: Any, **_kwargs: Any) -> None:
    raise AssertionError("job started before provider iteration completed")


def test_FAILURE_PRESERVED__policy_iteration_failure_precedes_job_and_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.ingest import policy

    class _Adapter:
        @staticmethod
        def fetch_documents() -> _ExplodingIterable:
            return _ExplodingIterable()

    monkeypatch.setattr(policy, "get_policy_adapter", lambda *_args, **_kwargs: _Adapter())
    monkeypatch.setattr(policy, "start_job", _unexpected_job_start)

    with pytest.raises(RuntimeError, match="provider iteration failed"):
        policy.ingest_policy_documents("CA")


def test_FAILURE_PRESERVED__reddit_business_methods_are_best_effort_total() -> None:
    from app.services.ingest.adapters.social_reddit import RedditAdapter

    def fail_fetch(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("external fetch failed")

    adapter = RedditAdapter()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.ingest.adapters.social_reddit.fetch_html", fail_fetch
        )
        monkeypatch.setattr("time.sleep", lambda *_args: None)
        assert list(adapter.fetch_posts("stocks", ["ai"], 2)) == []
        assert list(adapter.search_multiple_subreddits(["stocks"], ["ai"], 2)) == []
        assert set(
            adapter.discover_subreddits(keywords=["ai"], max_results=3, min_subscribers=1)
        ) == {"ai", "Ai", "ais"}


def test_FAILURE_PRESERVED__google_news_business_methods_are_best_effort_total() -> None:
    from app.services.ingest.adapters.news_google import GoogleNewsAdapter

    def fail_fetch(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("external fetch failed")

    adapter = GoogleNewsAdapter()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.services.ingest.adapters.news_google.fetch_html", fail_fetch
        )
        assert list(adapter.search("ai", 2)) == []
        assert list(adapter.search_multiple_keywords(["ai"], 2)) == []


def test_FAILURE_PRESERVED__collect_registration_contracts_fail_closed() -> None:
    from app.services.collect_runtime import runtime

    original_registry = dict(runtime._SKILL_REGISTRY)
    original_projector = runtime._SOURCE_LIBRARY_COMPAT_PROJECTOR

    class _Adapter:
        @staticmethod
        def run(_request: object) -> object:
            return object()

    try:
        with pytest.raises(ValueError, match="skill_id is required"):
            runtime.register_collect_skill("", _Adapter())
        with pytest.raises(TypeError, match="collect adapter must provide run"):
            runtime.register_collect_skill("bad", object())
        with pytest.raises(TypeError, match="projector must be callable"):
            runtime.register_source_library_compat_projector(object())
    finally:
        runtime._SKILL_REGISTRY.clear()
        runtime._SKILL_REGISTRY.update(original_registry)
        runtime._SOURCE_LIBRARY_COMPAT_PROJECTOR = original_projector


def test_INVARIANT__runtime_failure_literals_are_bounded_by_source() -> None:
    provider_tree = _parse("main/backend/app/services/ingest/provider_ports.py")
    expected_provider_messages = {
        "policy adapter provider is not configured",
        "Reddit adapter provider is not configured",
        "Google News adapter provider is not configured",
    }
    actual_provider_messages = {
        message
        for name in (
            "get_policy_adapter",
            "get_reddit_adapter",
            "get_google_news_adapter",
        )
        for message in _constant_raises(_function(provider_tree, name))
    }
    assert actual_provider_messages == expected_provider_messages

    collect_tree = _parse("main/backend/app/services/collect_runtime/runtime.py")
    for function_name in (
        "register_collect_skill",
        "register_source_library_compat_projector",
    ):
        assert _constant_raises(_function(collect_tree, function_name)) == set()

    collect_failure_source = ast.unparse(_function(collect_tree, "_collect_contract_failure"))
    assert "collect_runtime_failures.fail" in collect_failure_source
    assert {
        "skill_id_required",
        "collect_adapter_contract_invalid",
        "compat_projector_contract_invalid",
    } <= set(collect_runtime_failures.codes)
