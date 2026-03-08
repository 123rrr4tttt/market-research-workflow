from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.collect_runtime.adapters.source_library import SourceLibraryAdapter
from app.services.collect_runtime.contracts import CollectRequest
from app.services.source_library.resolver import list_effective_channels


class SourceLibraryHandlerClusterUnitTestCase(unittest.TestCase):
    def test_list_effective_channels_includes_builtin_handler_cluster_channel(self) -> None:
        channels = list_effective_channels(scope="effective", project_key=None)
        channel_map = {str(ch.get("channel_key") or ""): ch for ch in channels}

        self.assertIn("handler.cluster", channel_map)
        channel = channel_map["handler.cluster"]
        self.assertEqual(channel.get("provider"), "handler")
        self.assertEqual(channel.get("kind"), "cluster")
        self.assertTrue(channel.get("enabled"))

    def test_source_library_adapter_uses_run_item_by_key_for_handler_cluster_items(self) -> None:
        adapter = SourceLibraryAdapter()
        request = CollectRequest(
            channel="source_library",
            project_key="demo_proj",
            item_key="handler.cluster.search_template",
            options={"override_params": {"query_terms": ["Humane AI Pin"]}},
        )
        raw = {
            "item_key": "handler.cluster.search_template",
            "channel_key": "handler.cluster",
            "params": {},
            "result": {"inserted": 1, "updated": 0, "skipped": 0, "errors": []},
        }

        with (
            patch("app.services.collect_runtime.adapters.source_library.start_job", return_value="job-test-1"),
            patch("app.services.collect_runtime.adapters.source_library.complete_job"),
            patch("app.services.collect_runtime.adapters.source_library.fail_job"),
            patch("app.services.source_library.resolver.run_item_by_key", return_value=raw) as mocked_run_item_by_key,
        ):
            result = adapter.run(request)

        mocked_run_item_by_key.assert_called_once_with(
            item_key="handler.cluster.search_template",
            project_key="demo_proj",
            override_params={"query_terms": ["Humane AI Pin"]},
        )
        self.assertEqual(result.inserted, 1)
        self.assertEqual(((result.meta or {}).get("raw") or {}).get("channel_key"), "handler.cluster")


if __name__ == "__main__":
    unittest.main()
