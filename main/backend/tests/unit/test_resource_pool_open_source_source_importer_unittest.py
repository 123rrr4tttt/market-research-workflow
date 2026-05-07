from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.resource_pool.open_source_source_importer import import_open_source_preset_pack
from app.services.resource_pool.open_source_source_presets import get_open_source_preset_pack, list_open_source_preset_packs


class OpenSourceSourceImporterUnitTestCase(unittest.TestCase):
    def test_import_open_source_preset_pack_writes_entries(self) -> None:
        seen = []

        def _fake_upsert(**kwargs):
            seen.append(kwargs)
            return {"site_url": kwargs["site_url"], "entry_type": kwargs["entry_type"], "tags": kwargs["tags"]}

        with patch("app.services.resource_pool.open_source_source_importer.upsert_site_entry", side_effect=_fake_upsert):
            result = import_open_source_preset_pack(
                pack_key="business_media_foundation",
                scope="project",
                project_key="demo_proj",
                extra_tags=["seeded"],
            )

        self.assertEqual(result.pack_key, "business_media_foundation")
        self.assertGreaterEqual(len(result.inserted_or_updated), 5)
        self.assertIn("seeded", seen[0]["tags"])
        self.assertIn("open_source_preset", seen[0]["tags"])

    def test_keyword_research_foundation_pack_has_query_and_feed_sources(self) -> None:
        pack = get_open_source_preset_pack("keyword_research_foundation")
        entry_types = {entry.entry_type for entry in pack.entries}
        pack_keys = {row["key"] for row in list_open_source_preset_packs()}

        self.assertIn("keyword_research_foundation", pack_keys)
        self.assertGreaterEqual(len(pack.entries), 8)
        self.assertIn("search_template", entry_types)
        self.assertIn("rss", entry_types)
        self.assertTrue(
            any("keyword_research" in entry.tags for entry in pack.entries),
            "keyword research pack entries should be tagged for filtering and smoke setup",
        )


if __name__ == "__main__":
    unittest.main()
