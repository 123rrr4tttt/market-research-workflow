from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.contract

_TARGET_MODULE_OPERATIONS = {
    "indexer.py": frozenset((("POST", "/api/v1/indexer/policy"),)),
    "search.py": frozenset(
        (
            ("GET", "/api/v1/search/runs/{retrieval_run_id}"),
            ("GET", "/api/v1/search"),
            ("POST", "/api/v1/search/_init"),
        )
    ),
    "writing.py": frozenset(
        (
            ("GET", "/api/v1/writing/documents"),
            ("POST", "/api/v1/writing/documents"),
            ("DELETE", "/api/v1/writing/documents/{doc_id}"),
            ("GET", "/api/v1/writing/documents/{doc_id}"),
            ("PATCH", "/api/v1/writing/documents/{doc_id}"),
            ("POST", "/api/v1/writing/documents/{doc_id}/draft"),
            ("GET", "/api/v1/writing/documents/{doc_id}/citations"),
            ("POST", "/api/v1/writing/documents/{doc_id}/citations"),
            ("GET", "/api/v1/writing/templates"),
            ("POST", "/api/v1/writing/templates/validate"),
            ("POST", "/api/v1/writing/keyword-cards"),
            ("POST", "/api/v1/writing/keyword-cards/preview"),
            ("GET", "/api/v1/writing/cards/{card_id}"),
            ("GET", "/api/v1/writing/suggest"),
            ("POST", "/api/v1/writing/export/markdown"),
        )
    ),
}
_TARGET_MODULE_COUNTS = {
    module: len(operations) for module, operations in _TARGET_MODULE_OPERATIONS.items()
}

try:
    from app.api.indexer import ReindexPolicyRequest
    from app.api.search import SEARCH_RESULTS_CONTRACT_VERSION, _canonical_search_result
    from app.api.writing import _handle_conflict
    from app.contracts.schemas.writing import (
        WritingCitationData,
        WritingCitationUpsertItem,
        WritingDocumentData,
    )
    from app.services.document_queries import (
        MATERIAL_QUERY_CONTRACT_VERSION,
        build_search_endpoint_material_query_envelope,
    )
    from app.services.writing import WritingVersionConflictError
    from app.main import app as backend_app
    from scripts.generate_api_schema_inventory import build_inventory

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class ApiSchemaWritingSearchSmallContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"writing/search/small schema tests require backend dependencies: {_IMPORT_ERROR}")

    def _target_operations(self) -> list[dict]:
        inventory = build_inventory(backend_app)
        return [
            operation
            for operation in inventory["operations"]
            if operation["source_module"] in _TARGET_MODULE_OPERATIONS
        ]

    def test_target_modules_have_expected_operation_coverage(self):
        counts = {module: 0 for module in _TARGET_MODULE_COUNTS}
        for operation in self._target_operations():
            counts[operation["source_module"]] += 1

        self.assertEqual(counts, _TARGET_MODULE_COUNTS)
        self.assertEqual(sum(counts.values()), 19)
        actual_operations = {
            module: {
                (operation["method"], operation["path"])
                for operation in self._target_operations()
                if operation["source_module"] == module
            }
            for module in _TARGET_MODULE_OPERATIONS
        }
        self.assertEqual(
            actual_operations,
            {module: set(operations) for module, operations in _TARGET_MODULE_OPERATIONS.items()},
        )

    def test_target_operations_have_no_untyped_200_schemas(self):
        untyped = [
            f"{operation['source_module']} {operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_200_schema"] == "untyped"
        ]
        self.assertEqual(untyped, [])

    def test_json_target_operations_have_response_models(self):
        missing_response_model = [
            f"{operation['source_module']} {operation['method']} {operation['path']}"
            for operation in self._target_operations()
            if operation["response_model"] == "none"
            and operation["path"] != "/api/v1/writing/export/markdown"
        ]
        self.assertEqual(missing_response_model, [])

    def test_markdown_export_keeps_explicit_non_json_schema(self):
        operations = {
            (operation["method"], operation["path"]): operation
            for operation in self._target_operations()
        }
        markdown_export = operations[("POST", "/api/v1/writing/export/markdown")]

        self.assertEqual(markdown_export["response_model"], "none")
        self.assertEqual(markdown_export["response_200_schema"], "non-json")

    def test_writing_contracts_use_distinct_document_and_material_identifiers(self):
        self.assertIn("doc_id", WritingDocumentData.model_fields)
        self.assertNotIn("id", WritingDocumentData.model_fields)
        self.assertIn("source_material_id", WritingCitationData.model_fields)
        self.assertNotIn("source_doc_id", WritingCitationData.model_fields)

        with self.assertRaises(ValidationError):
            WritingCitationUpsertItem.model_validate({"source_doc_id": 42})
        citation = WritingCitationUpsertItem.model_validate({"source_material_id": 42})
        self.assertEqual(citation.source_material_id, 42)

        conflict = _handle_conflict(
            WritingVersionConflictError(
                expected_version=1,
                current_version=2,
                server_snapshot={
                    "conflict_code": "VERSION_CONFLICT",
                    "server_snapshot": {"id": 17, "title": "Draft"},
                },
            )
        )
        server_snapshot = conflict.detail["error"]["details"]["server_snapshot"]
        self.assertEqual(server_snapshot["doc_id"], 17)
        self.assertNotIn("id", server_snapshot)

    def test_search_results_v2_exposes_only_material_identity(self):
        result = _canonical_search_result(
            {
                "material_id": "material-1",
                "score": 0.9,
                "source_type": "material",
            }
        )

        self.assertEqual(SEARCH_RESULTS_CONTRACT_VERSION, "search.results.v2")
        self.assertEqual(result["material_id"], "material-1")
        self.assertEqual(result["source_type"], "material")
        self.assertNotIn("id", result)
        self.assertNotIn("document_id", result)
        self.assertNotIn("doc_id", result)

        with self.assertRaisesRegex(ValueError, "retired identity fields"):
            _canonical_search_result({"document_id": "legacy-document-id"})

    def test_search_material_query_envelope_exposes_only_material_identity(self):
        envelope = build_search_endpoint_material_query_envelope(
            query="market trend",
            top_k=1,
            results=[{"material_id": 7, "title": "Material 7"}],
        )
        result = envelope["data"]["results"][0]

        self.assertEqual(envelope["data"]["contract_version"], MATERIAL_QUERY_CONTRACT_VERSION)
        self.assertEqual(result["material_id"], 7)
        self.assertTrue({"id", "document_id", "doc_id"}.isdisjoint(result))

    def test_indexer_rejects_retired_document_ids(self):
        with self.assertRaises(ValidationError):
            ReindexPolicyRequest.model_validate({"document_ids": [1]})
        request = ReindexPolicyRequest.model_validate({"material_ids": [1]})
        self.assertEqual(request.material_ids, [1])


if __name__ == "__main__":
    unittest.main()
