from __future__ import annotations

import importlib
import sys
import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_LIBRARY_DIR = _ROOT / "app" / "services" / "source_library"
_ADAPTERS_DIR = _SOURCE_LIBRARY_DIR / "adapters"
_SERVICES_DIR = _ROOT / "app" / "services"


def _ensure_package(name: str, path: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    if "." in name:
        parent_name, child_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, child_name, module)


_ensure_package("app", _ROOT / "app")
_ensure_package("app.services", _ROOT / "app" / "services")
_ensure_package("app.services.ingest", _SERVICES_DIR / "ingest")
_ensure_package("app.services.ingest.adapters", _SERVICES_DIR / "ingest" / "adapters")
_ensure_package("app.services.resource_pool", _SERVICES_DIR / "resource_pool")
_ensure_package("app.services.source_library", _SOURCE_LIBRARY_DIR)
_ensure_package("app.services.source_library.adapters", _ADAPTERS_DIR)

# Keep the package shell for direct module loading, but expose the real
# resource_pool public symbols so later tests can patch the compatibility path.
_RESOURCE_POOL_PUBLIC = importlib.import_module("app.services.resource_pool.unified_search")
_RESOURCE_POOL_PACKAGE = sys.modules["app.services.resource_pool"]
setattr(_RESOURCE_POOL_PACKAGE, "unified_search_by_item", _RESOURCE_POOL_PUBLIC.unified_search_by_item)
setattr(
    _RESOURCE_POOL_PACKAGE,
    "unified_search_by_item_payload",
    _RESOURCE_POOL_PUBLIC.unified_search_by_item_payload,
)

_SPEC = spec_from_file_location(
    "app.services.source_library.adapters.generic_web",
    _ADAPTERS_DIR / "generic_web.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
sys.modules["app.services.source_library.adapters"].generic_web = _MODULE

handle_generic_web_search_template = _MODULE.handle_generic_web_search_template
handle_generic_web_rss = _MODULE.handle_generic_web_rss
handle_generic_web_sitemap = _MODULE.handle_generic_web_sitemap


class GenericWebSearchTemplateAdapterUnitTestCase(unittest.TestCase):
    def test_rss_adapter_delegates_to_shared_feed_probe(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_feed_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/rss-item"})()],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 1},
                errors=[],
            )
            result = handle_generic_web_rss(
                {
                    "feed_url": "https://example.com/feed.xml",
                    "query_terms": ["robotics"],
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], ["https://example.com/posts/rss-item"])

    def test_sitemap_adapter_delegates_to_shared_sitemap_probe(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_sitemap_probe") as execute:
            execute.return_value = SimpleNamespace(
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/sitemap-item"})()],
                used_term_fallback=False,
                pages_scanned=1,
                diagnostics={"raw_candidates": 1},
                errors=[],
            )
            result = handle_generic_web_sitemap(
                {
                    "sitemap_url": "https://example.com/sitemap.xml",
                    "query_terms": ["robotics"],
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], ["https://example.com/posts/sitemap-item"])

    def test_search_template_uses_text_matching_and_multi_page_fetch(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?query={{q}}",
                search_urls=[
                    "https://example.com/search?query=Alpha+Beta",
                    "https://example.com/search?query=Alpha+Beta&page=2",
                ],
                pages_scanned=2,
                raw_candidates=[],
                selected_candidates=[
                    type("Decision", (), {"url": "https://example.com/posts/123"})(),
                    type("Decision", (), {"url": "https://example.com/posts/456"})(),
                ],
                used_term_fallback=False,
                errors=[],
                diagnostics={"pages_scanned": 2},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?query={{q}}",
                    "query_terms": ["Alpha", "Beta"],
                    "page": 1,
                    "max_pages": 2,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(
            set(result["candidates"]),
            {
                "https://example.com/posts/123",
                "https://example.com/posts/456",
            },
        )
        self.assertFalse(result["used_term_fallback"])
        self.assertEqual(result["pages_scanned"], 2)

    def test_search_template_returns_empty_when_fallback_disabled_and_no_match(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[],
                used_term_fallback=True,
                errors=[],
                diagnostics={"raw_candidates": 0},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "allow_term_fallback": False,
                },
                project_key=None,
            )

        execute.assert_called_once()
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["used_term_fallback"])
        self.assertEqual(result["pages_scanned"], 1)

    def test_write_to_pool_uses_traceable_source_ref_shape(self) -> None:
        with (
            patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute,
            patch("app.services.source_library.adapters.generic_web.append_url", return_value=True) as append,
        ):
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/robotics-1"})()],
                used_term_fallback=False,
                errors=[],
                diagnostics={"raw_candidates": 1},
            )
            handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "write_to_pool": True,
                    "_source_library_item": {
                        "item_key": "handler.cluster.search_template",
                        "channel_key": "handler.cluster",
                        "item_type": "service_aggregated",
                        "managed_by": "system",
                        "extra": {"expected_entry_type": "search_template"},
                    },
                },
                project_key="demo_proj",
            )

        source_ref = append.call_args.kwargs["source_ref"]
        self.assertEqual(source_ref["tool"], "generic_web_search_template")
        self.assertEqual(source_ref["query_terms"], ["robotics"])
        self.assertEqual(source_ref["locator"], "https://example.com/posts/robotics-1")
        self.assertEqual(source_ref["url"], "https://example.com/posts/robotics-1")
        self.assertEqual(source_ref["domain"], "example.com")
        self.assertEqual(source_ref["entrypoint"], "source_library.generic_web_search_template")
        self.assertEqual(source_ref["source_mode"], "generic_web_search_template")
        self.assertEqual(source_ref["project_key"], "demo_proj")
        self.assertEqual(source_ref["item_key"], "handler.cluster.search_template")
        self.assertEqual(source_ref["channel_key"], "handler.cluster")
        self.assertEqual(source_ref["item_type"], "service_aggregated")
        self.assertEqual(source_ref["managed_by"], "system")
        self.assertEqual(source_ref["entry_type"], "search_template")
        self.assertEqual(source_ref["source_family"], "generic_web")

    def test_search_template_reports_capability_profile_and_taxonomy(self) -> None:
        with patch("app.services.source_library.adapters.generic_web.execute_search_template") as execute:
            execute.return_value = SimpleNamespace(
                template="https://example.com/search?q={{q}}",
                search_urls=["https://example.com/search?q=robotics"],
                pages_scanned=1,
                raw_candidates=[],
                selected_candidates=[type("Decision", (), {"url": "https://example.com/posts/robotics-1"})()],
                used_term_fallback=False,
                errors=[],
                diagnostics={"raw_candidates": 1},
            )
            result = handle_generic_web_search_template(
                {
                    "template": "https://example.com/search?q={{q}}",
                    "query_terms": ["robotics"],
                    "_source_library_item": {
                        "item_key": "handler.cluster.search_template",
                        "item_type": "service_aggregated",
                        "managed_by": "system",
                    },
                },
                project_key="demo_proj",
            )

        self.assertEqual(result["source_mode"], "site_search")
        self.assertEqual(result["capability_profile"]["entry_type"], "search_template")
        self.assertTrue(result["capability_profile"]["supports_pagination"])
        self.assertEqual(result["adapter_taxonomy"]["lane"], "site_search_internal_adapter")
        self.assertTrue(result["adapter_taxonomy"]["internal_adapter_only"])
        self.assertEqual(result["adapter_taxonomy"]["item_type"], "service_aggregated")


if __name__ == "__main__":
    unittest.main()
