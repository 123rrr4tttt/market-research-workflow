from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pytest

from app.models.entities import Document
from app.services.agent_runtime.structured_data_quality import detect_structured_record_noise
from app.services.agent_runtime.structured_data_search import (
    _normalize_datasets,
    _normalize_query,
    _parse_structured_data_read_ref,
    _query_model,
    _record,
    read_project_structured_data_item,
    read_project_structured_data_items,
)

pytestmark = pytest.mark.unit


class _FakeCount:
    def __init__(self, value: int) -> None:
        self.value = value

    def scalar(self) -> int:
        return self.value


class _FakeRows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self) -> "_FakeRows":
        return self

    def all(self) -> list[object]:
        return self.rows


class StructuredDataSearchUnitTest(unittest.TestCase):
    def test_legacy_document_dataset_and_read_handles_normalize_to_materials(self):
        self.assertEqual(_normalize_datasets(["documents", "materials"]), ["materials"])
        for ref in (
            {"dataset": "documents", "record_id": "42"},
            {"item_id": "structured:documents:42"},
            {"resource_uri": "project://structured/demo/documents/42"},
        ):
            parsed = _parse_structured_data_read_ref(
                project_key="demo", **{"dataset": None, "record_id": None, "item_id": None, "resource_uri": None, **ref}
            )
            self.assertEqual(parsed["dataset"], "materials")
            self.assertEqual(parsed["record_id"], "42")

    def test_structured_resource_uri_preserves_project_scope(self):
        parsed = _parse_structured_data_read_ref(
            project_key="project-a",
            dataset=None,
            record_id=None,
            item_id=None,
            resource_uri="project://structured/project-b/documents/42",
        )
        self.assertEqual(parsed["project_key"], "project-a")
        self.assertEqual(parsed["scope_error"], "cross_project_reference")
        result = read_project_structured_data_item(
            project_key="project-a",
            resource_uri="project://structured/project-b/documents/42",
        )
        self.assertEqual(result["item"], None)
        self.assertEqual(result["errors"][0]["type"], "cross_project_reference")
        batch = read_project_structured_data_items(
            project_key="project-a",
            items=[{"project_key": "project-b", "dataset": "documents", "record_id": "42"}],
        )
        self.assertEqual(batch["total_returned"], 0)
        self.assertEqual(batch["errors"][0]["type"], "cross_project_reference")

    def test_targeted_search_skips_dataset_count_query(self):
        session = Mock()
        row = SimpleNamespace(title="Robot market note")
        session.execute.return_value = _FakeRows([row])

        items, total_rows = _query_model(
            session,
            Document,
            dataset="documents",
            query="robot",
            limit=3,
            mapper=lambda item: {"title": item.title},
            search_columns=(),
        )

        self.assertIsNone(total_rows)
        self.assertEqual(items, [{"title": "Robot market note", "dataset": "documents"}])
        self.assertEqual(session.execute.call_count, 1)

    def test_targeted_search_filters_matches_without_visible_query_evidence(self):
        session = Mock()
        rows = [
            SimpleNamespace(title="NBC4 news", summary="", fields={}),
            SimpleNamespace(title="Robot market adoption", summary="robotics adoption notes", fields={}),
        ]
        session.execute.return_value = _FakeRows(rows)

        items, total_rows = _query_model(
            session,
            Document,
            dataset="documents",
            query="robot",
            limit=3,
            mapper=lambda item: {"title": item.title, "summary": getattr(item, "summary", ""), "fields": getattr(item, "fields", {})},
            search_columns=(),
        )

        self.assertIsNone(total_rows)
        self.assertEqual([item["title"] for item in items], ["Robot market adoption"])
        self.assertEqual(session.execute.call_count, 1)

    def test_inventory_query_keeps_total_row_count(self):
        session = Mock()
        row = SimpleNamespace(title="Inventory note")
        session.execute.side_effect = [_FakeCount(42), _FakeRows([row])]

        items, total_rows = _query_model(
            session,
            Document,
            dataset="documents",
            query="",
            limit=3,
            mapper=lambda item: {"title": item.title},
            search_columns=(),
        )

        self.assertEqual(total_rows, 42)
        self.assertEqual(items, [{"title": "Inventory note", "dataset": "documents"}])
        self.assertEqual(session.execute.call_count, 2)

    def test_record_omits_web_script_noise_from_display_summary(self):
        item = _record(
            "documents",
            1,
            "NBC4 Los Angeles - Southern California news",
            "if (typeof adInstance !== 'undefined') { window.googletag.display(slot); } robotics market",
            {"uri": "https://example.com/noisy-page"},
        )

        self.assertEqual(item["summary"], "")
        self.assertEqual(item["fields"]["quality_flags"]["display_summary_omitted"], True)
        self.assertEqual(item["fields"]["quality_flags"]["display_summary_omit_reason"], "web_script_or_navigation_noise")

    def test_record_omits_css_noise_from_display_summary(self):
        item = _record(
            "documents",
            2,
            "CalMatters article",
            "Citing Iran crisis, Trump orders pipeline restart. .entry-content{grid-template-rows: repeat(14,auto);}",
            {"uri": "https://example.com/noisy-css"},
        )

        self.assertEqual(item["summary"], "")
        self.assertEqual(item["fields"]["quality_flags"]["display_summary_omitted"], True)

    def test_normalize_query_extracts_topic_from_natural_language_request(self):
        self.assertEqual(
            _normalize_query("基于项目里已有的机器人相关数据，帮我总结三点，并说明用了哪些本地数据。"),
            "机器人",
        )

    def test_quality_audit_detector_flags_web_shell_noise(self):
        result = detect_structured_record_noise(
            "if (typeof adInstance !== 'undefined') { window.googletag.display(slot); } .entry-content{grid-template-rows: repeat(14,auto);}"
        )

        self.assertTrue(result["is_noisy"])
        self.assertIn("script_branch", result["noise_reasons"])
        self.assertIn("javascript_global", result["noise_reasons"])
        self.assertIn("css_block", result["noise_reasons"])


if __name__ == "__main__":
    unittest.main()
