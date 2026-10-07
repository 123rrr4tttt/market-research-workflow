from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest
from functorial_kit import Failure
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.models.entities import Document
from app.services.document_queries import (
    DOCUMENT_QUERY_CONTRACT_VERSION,
    DocumentQueryFilter,
    DocumentQuerySort,
    apply_document_query_to_statement,
    build_document_query,
    build_document_query_statement,
    build_document_query_result_envelope,
    compile_document_query_statement,
    document_query_to_statement,
    query_hybrid_document_envelope,
    query_hybrid_document_rows,
    query_source_library_material_envelope,
    query_source_library_material_rows,
    rows_for_document_views,
    try_build_document_query,
    try_validate_document_query_result_envelope,
    validate_document_query_result_envelope,
)
from app.services.document_queries.identity import (
    canonical_material_identity,
    document_identity,
    material_identity,
)
from app.services.document_views import build_keyword_card_from_hybrid_row, build_keyword_card_from_material_item


class DocumentQueriesContractUnitTestCase(unittest.TestCase):
    def test_canonical_material_identity_accepts_canonical_or_legacy_address(self) -> None:
        canonical = material_identity("demo_proj", 42)
        legacy = document_identity("demo_proj", 42)

        self.assertEqual(canonical_material_identity("demo_proj", canonical), canonical)
        self.assertEqual(canonical_material_identity("demo_proj", legacy), canonical)
        self.assertIsNone(canonical_material_identity("other_proj", canonical))
        self.assertIsNone(canonical_material_identity("demo_proj", {**canonical, "extra": "forged"}))
        self.assertIsNone(
            canonical_material_identity(
                "demo_proj",
                {**canonical, "module_id": "documents"},
            )
        )

    def test_material_and_legacy_sources_share_query_and_sql_identity(self) -> None:
        legacy = build_document_query("robotics", sources=("document",))
        material = build_document_query("robotics", sources=("material",))
        self.assertEqual(legacy.query_id, material.query_id)
        self.assertEqual(compile_document_query_statement(legacy), compile_document_query_statement(material))
        envelope = build_document_query_result_envelope(material, [{"material_id": 42}], source="test")
        self.assertEqual(envelope["data"]["results"][0]["document_id"], 42)
        envelope["data"]["contract_version"] = "document_queries.v1"
        envelope["data"]["query"]["contract_version"] = "document_queries.v1"
        envelope["data"]["results"][0].pop("material_id")
        envelope["data"]["results"][0]["source_type"] = "document"
        self.assertEqual(rows_for_document_views(envelope)[0]["material_id"], 42)
        self.assertEqual(rows_for_document_views(envelope)[0]["source_type"], "material")

    def test_query_object_normalizes_filter_sort_and_bounds(self) -> None:
        query = build_document_query(
            "  Robotics   Policy  ",
            project_key=" demo_proj ",
            consumer=" writing.search ",
            sources=(" document ", "resource", ""),
            filters=(
                {"field": "state", "op": "eq", "value": "CA"},
                DocumentQueryFilter("policy.effective_date", "gte", "2026-01-01"),
            ),
            sort=(
                DocumentQuerySort("published_at", "DESC"),
                {"field": "title", "direction": "asc"},
            ),
            limit=999,
            offset=-1,
        )

        payload = query.to_dict()

        self.assertEqual(payload["contract_version"], DOCUMENT_QUERY_CONTRACT_VERSION)
        self.assertEqual(payload["query"], "Robotics Policy")
        self.assertEqual(payload["normalized_query"], "robotics policy")
        self.assertEqual(payload["project_key"], "demo_proj")
        self.assertEqual(payload["consumer"], "writing.search")
        self.assertEqual(payload["sources"], ["material", "resource"])
        self.assertEqual(payload["filters"][0], {"field": "state", "op": "eq", "value": "CA"})
        self.assertEqual(payload["sort"][0], {"field": "published_at", "direction": "desc"})
        self.assertEqual(payload["limit"], 100)
        self.assertEqual(payload["offset"], 0)
        self.assertRegex(payload["query_id"], r"^[0-9a-f]{16}$")

    def test_result_envelope_can_feed_document_view_cards(self) -> None:
        query = build_document_query(
            "robotics",
            consumer="writing.keyword_cards",
            sources=("document",),
            limit=2,
        )
        envelope = build_document_query_result_envelope(
            query,
            [
                {
                    "id": "doc-1",
                    "document_id": 42,
                    "title": "Robotics adoption",
                    "summary": "Industrial robotics pilot evidence.",
                    "url": "https://example.org/robotics",
                    "score": "0.91",
                    "backend": "hybrid",
                }
            ],
            source="search.hybrid",
            result_source_type="document",
        )

        validate_document_query_result_envelope(envelope)
        rows = rows_for_document_views(envelope)
        card = build_keyword_card_from_hybrid_row(rows[0], normalized_query="robotics")

        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["data"]["query"]["consumer"], "writing.keyword_cards")
        self.assertEqual(envelope["meta"]["source"], "search.hybrid")
        self.assertEqual(rows[0]["source_type"], "material")
        self.assertEqual(rows[0]["material_id"], rows[0]["document_id"])
        self.assertEqual(rows[0]["document_id"], 42)
        self.assertEqual(card.source_type, "material")
        self.assertEqual(card.extra["backend"], "hybrid")
        self.assertEqual(card.extra["material_id"], 42)
        self.assertNotIn("document_id", card.extra)

    def test_non_json_filter_value_returns_failure_and_legacy_shape(self) -> None:
        result = try_build_document_query(
            "",
            filters=({"field": "state", "op": "eq", "value": object()},),
        )

        self.assertIsInstance(result, Failure)
        assert isinstance(result, Failure)
        self.assertTrue(result.failure)
        self.assertEqual(result.code, "filter_invalid")
        self.assertEqual(result.message, "document query JSON value must be str, int, float, bool, null, array, or object")
        self.assertEqual(result.context["owner"], "document_queries.contracts.json")
        with self.assertRaisesRegex(ValueError, "document query JSON value"):
            build_document_query("", filters=({"field": "state", "op": "eq", "value": object()},))

    def test_non_json_result_row_is_rejected_without_field_erasure(self) -> None:
        query = build_document_query("robotics", limit=2)

        with self.assertRaisesRegex(ValueError, "document query JSON value"):
            build_document_query_result_envelope(
                query,
                [{"document_id": 7, "bad": object()}],
                source="search.hybrid",
            )

    def test_invalid_result_envelope_status_preserves_failure_shape(self) -> None:
        result = try_validate_document_query_result_envelope(
            {
                "status": "error",
                "data": {},
                "error": None,
                "meta": {},
            }
        )

        self.assertIsInstance(result, Failure)
        assert isinstance(result, Failure)
        self.assertTrue(result.failure)
        self.assertEqual(result.code, "result_envelope_invalid")
        self.assertEqual(result.message, "document query result envelope status must be ok")
        with self.assertRaisesRegex(ValueError, "document query result envelope status must be ok"):
            validate_document_query_result_envelope(
                {
                    "status": "error",
                    "data": {},
                    "error": None,
                    "meta": {},
                }
            )

    def test_writing_hybrid_query_uses_contract_envelope_before_legacy_rows(self) -> None:
        with patch(
            "app.services.document_queries.writing_material_queries.hybrid_search",
            return_value=[
                {
                    "id": "doc-7",
                    "document_id": 7,
                    "title": "Robot market note",
                    "snippet": "robotics market",
                    "score": 0.77,
                    "backend": "pgvector",
                }
            ],
        ) as hybrid_search:
            envelope = query_hybrid_document_envelope("robot", limit=3)
            rows = query_hybrid_document_rows("robot", limit=3)

        hybrid_search.assert_called_with("robot", state=None, top_k=3, mode="hybrid")
        self.assertEqual(envelope["data"]["query"]["sources"], ["material"])
        self.assertEqual(envelope["data"]["pagination"]["limit"], 3)
        self.assertEqual(envelope["data"]["results"][0]["backend"], "pgvector")
        self.assertEqual(rows[0]["title"], "Robot market note")
        self.assertEqual(rows[0]["rank"], 1)

    def test_source_library_envelope_can_feed_material_card_view(self) -> None:
        with patch(
            "app.services.document_queries.writing_material_queries.list_effective_items",
            return_value=[
                {"item_key": "ignored", "name": "Other", "description": "unrelated", "channel_key": "market"},
                {
                    "item_key": "robotics_feed",
                    "name": "Robotics Feed",
                    "description": "robotics source",
                    "channel_key": "market",
                },
            ],
        ):
            envelope = query_source_library_material_envelope("demo_proj", query="robotics", limit=5)
            legacy_rows = query_source_library_material_rows("demo_proj", query="robotics")

        validate_document_query_result_envelope(envelope)
        rows = rows_for_document_views(envelope)
        card = build_keyword_card_from_material_item(legacy_rows[0], normalized_query="robotics")

        self.assertEqual(envelope["data"]["query"]["filters"][0]["field"], "project_key")
        self.assertEqual(envelope["data"]["pagination"]["total"], 1)
        self.assertEqual(rows[0]["source_type"], "resource")
        self.assertEqual(rows[0]["raw"]["item_key"], "robotics_feed")
        self.assertEqual(legacy_rows[0]["item_key"], "robotics_feed")
        self.assertEqual(card.source_type, "resource")
        self.assertEqual(card.extra["item_key"], "robotics_feed")

    def test_document_query_builds_sqlalchemy_statement_with_filters_sort_and_pagination(self) -> None:
        query = build_document_query(
            "robotics policy",
            project_key="demo_proj",
            consumer="structured.service",
            sources=("document",),
            filters=(
                {"field": "state", "op": "eq", "value": "CA"},
                {"field": "doc_type", "op": "in", "value": ["policy", "news"]},
                {"field": "extracted_data.policy.policy_type", "op": "contains", "value": "grant"},
            ),
            sort=({"field": "published_at", "direction": "desc"},),
            limit=7,
            offset=3,
        )

        statement = build_document_query_statement(query)
        compiled = compile_document_query_statement(statement)
        alias_compiled = compile_document_query_statement(document_query_to_statement(query))

        self.assertIn("FROM documents", alias_compiled)
        self.assertIn("FROM documents", compiled)
        self.assertIn("documents.state = 'CA'", compiled)
        self.assertIn("documents.doc_type IN ('policy', 'news')", compiled)
        self.assertIn("project_key", compiled)
        self.assertIn("policy_type", compiled)
        self.assertIn("ORDER BY documents.publish_date DESC NULLS LAST", compiled)
        self.assertIn("LIMIT 7 OFFSET 3", compiled)

    def test_document_query_statement_adapter_extends_existing_statement(self) -> None:
        query = build_document_query(
            "",
            filters=({"field": "summary", "op": "contains", "value": "robotics"},),
            sort=({"field": "title", "direction": "asc"},),
            limit=2,
        )

        statement = apply_document_query_to_statement(
            query,
            select(Document).where(Document.status == "active"),
        )
        compiled = compile_document_query_statement(statement)

        self.assertIn("documents.status = 'active'", compiled)
        self.assertIn("documents.summary ILIKE", compiled)
        self.assertIn("ORDER BY documents.title ASC NULLS LAST", compiled)
        self.assertIn("LIMIT 2", compiled)

    def test_document_query_statement_applies_non_document_sources_as_doc_type_scope(self) -> None:
        query = build_document_query(
            "",
            sources=("documents", "policy", "news"),
            limit=4,
        )

        compiled = compile_document_query_statement(query)

        self.assertIn("documents.doc_type IN ('news', 'policy')", compiled)
        self.assertIn("LIMIT 4", compiled)

    def test_document_query_statement_builder_rejects_unsupported_fields(self) -> None:
        query = build_document_query(
            "",
            filters=({"field": "raw_sql;drop_table", "op": "eq", "value": "bad"},),
        )

        with self.assertRaisesRegex(ValueError, "unsupported document query field"):
            build_document_query_statement(query)


if __name__ == "__main__":
    unittest.main()
