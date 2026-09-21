import copy
import importlib.util
import inspect
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from typing import Annotated, get_args, get_origin, get_type_hints


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.services.typed_knowledge import contracts  # noqa: E402
from app.services.typed_knowledge import persistence_boundary as boundary  # noqa: E402


def _load_typed_knowledge_api_module():
    package_name = "app.api"
    if package_name not in sys.modules:
        api_package = types.ModuleType(package_name)
        api_package.__path__ = [str(ROOT / "app" / "api")]
        sys.modules[package_name] = api_package

    module_name = "app.api.typed_knowledge"
    existing_module = sys.modules.get(module_name)
    if existing_module is not None:
        return existing_module
    module_path = ROOT / "app" / "api" / "typed_knowledge.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load typed knowledge API module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _return_metadata(function):
    return_hint = get_type_hints(function, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated  # type: ignore[comparison-overlap]
    metadata = get_args(return_hint)[1]
    assert isinstance(metadata, str)
    assert function.__name__ in inspect.getsource(function)
    return metadata


class _LiveRepositoryStub:
    def __init__(self, records=()):
        self.records = tuple(records)
        self.upsert_calls = 0
        self.repository_ref = boundary.LIVE_DB_REPOSITORY_REF
        self.logical_table = boundary.DEFAULT_LOGICAL_TABLE
        self.persistence_mode = boundary.LIVE_DB_PERSISTENCE_MODE
        self.live_db_write = True
        self.governance_ui_available = True
        self.migration_backfill_executed = True

    def upsert_record(self, *args, **kwargs):
        self.upsert_calls += 1
        raise AssertionError("live read projection must not seed")

    def list_records(self, *, project_key=None):
        normalized_project_key = str(project_key or "").strip() or None
        if normalized_project_key is None:
            return self.records
        return tuple(record for record in self.records if record.project_key == normalized_project_key)

    def list_writes(self):
        return ()


class TypedKnowledgePersistenceBoundaryTests(unittest.TestCase):
    def test_boundary_error_exposes_stable_failure_code(self):
        error = boundary.TypedKnowledgePersistenceBoundaryError(
            "governance_review_record_not_found:demo_proj:knowledge_item:missing"
        )

        self.assertEqual(
            error.failure_code,
            boundary.TYPED_KNOWLEDGE_PERSISTENCE_BOUNDARY_FAILURE,
        )

    def test_persistence_boundary_record_view_metadata(self):
        self.assertEqual(
            _return_metadata(boundary.build_persistence_boundary_record),
            (
                "kit:non-authoritative derived_as=view "
                "fact_source=typed_knowledge_canonical_inputs "
                "witness=test:test_persistence_boundary_record_view_metadata"
            ),
        )

    def test_persistence_api_envelope_view_metadata(self):
        self.assertEqual(
            _return_metadata(boundary.build_persistence_api_envelope),
            (
                "kit:non-authoritative derived_as=view "
                "fact_source=typed_knowledge_repository_records "
                "witness=test:test_persistence_api_envelope_view_metadata"
            ),
        )

    def test_sample_boundary_envelope_preserves_identity_visibility_lifecycle_and_handoff_refs(self):
        envelope = boundary.build_sample_boundary_envelope()
        repeated = boundary.build_sample_boundary_envelope()

        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(
            envelope["data"]["contract_version"],
            boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
        )
        self.assertEqual(len(envelope["data"]["records"]), 4)
        self.assertEqual(
            boundary.boundary_fingerprint(envelope),
            boundary.boundary_fingerprint(repeated),
        )
        self.assertEqual(envelope["data"]["repository"]["persistence_mode"], "in_memory_contract")
        self.assertFalse(envelope["data"]["repository"]["live_db_write"])
        self.assertTrue(all(write["live_db_write"] is False for write in envelope["data"]["writes"]))

        records_by_type = {record["object_type"]: record for record in envelope["data"]["records"]}
        item_record = records_by_type["knowledge_item"]
        self.assertEqual(item_record["identity_ref"], "demo_proj:knowledge_item:ki:robotics-policy")
        self.assertEqual(item_record["visibility_scope"], contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertEqual(item_record["lifecycle_state"], boundary.LIFECYCLE_STATE_ACTIVE)
        self.assertEqual(item_record["governance"]["review_state"], contracts.REVIEW_STATE_HUMAN_CONFIRMED)
        self.assertEqual(
            item_record["writing_handoff_refs"],
            [
                {
                    "contract_version": contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
                    "knowledge_item_key": "ki:robotics-policy",
                    "consumer": "writing.keyword_card",
                    "card_source_type": "resource",
                    "selection_hash": "selection:robotics",
                    "selection_text": "robotics investment",
                }
            ],
        )

        readiness = envelope["meta"]["readiness"]
        self.assertTrue(readiness["repository_contract"])
        self.assertTrue(readiness["api_envelope"])
        self.assertTrue(readiness["writing_handoff_refs"])
        self.assertFalse(readiness["live_db_persistence"])
        self.assertFalse(readiness["public_api_route"])
        self.assertFalse(readiness["governance_ui"])
        self.assertIn(
            "live_db_persistence_not_implemented",
            envelope["meta"]["remaining_live_gaps"],
        )

    def test_in_memory_repository_readback_records_status_before_without_claiming_live_db(self):
        item = contracts.KnowledgeItem(
            key="ki:boundary",
            project_key="demo_proj",
            canonical_statement="A governed knowledge item starts as a draft candidate.",
            primary_type_node_key="type:signal",
            evidence_refs=("doc:1",),
            review_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
        )
        revised = contracts.KnowledgeItem(
            key=item.key,
            project_key=item.project_key,
            canonical_statement="A governed knowledge item can become active after review.",
            primary_type_node_key=item.primary_type_node_key,
            evidence_refs=item.evidence_refs,
            review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        )
        repository = boundary.InMemoryTypedKnowledgeRepository(repository_ref="memory://unit-test")
        draft_record = boundary.build_persistence_boundary_record(item)
        active_record = boundary.build_persistence_boundary_record(revised)

        first = repository.upsert_record(draft_record, write_time="2026-05-22T00:00:00Z")
        second = repository.upsert_record(active_record, write_time="2026-05-22T00:01:00Z")
        stored = repository.get_record(active_record.identity_ref)

        self.assertIsNotNone(stored)
        self.assertEqual(first.status_before, None)
        self.assertEqual(first.status_after, boundary.LIFECYCLE_STATE_PROPOSED)
        self.assertEqual(second.status_before, boundary.LIFECYCLE_STATE_PROPOSED)
        self.assertEqual(second.status_after, boundary.LIFECYCLE_STATE_ACTIVE)
        self.assertEqual(stored.visibility_scope, contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY)
        self.assertFalse(second.live_db_write)

    def test_repository_keeps_same_object_key_writes_project_scoped(self):
        item_a = contracts.KnowledgeItem(
            key="ki:shared",
            project_key="alpha_proj",
            canonical_statement="Alpha project owns its scoped knowledge item.",
            primary_type_node_key="type:signal",
            evidence_refs=("doc:alpha",),
            review_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
        )
        item_b = contracts.KnowledgeItem(
            key=item_a.key,
            project_key="beta_proj",
            canonical_statement="Beta project owns a separate item with the same object key.",
            primary_type_node_key=item_a.primary_type_node_key,
            evidence_refs=("doc:beta",),
            review_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        )
        repository = boundary.InMemoryTypedKnowledgeRepository(repository_ref="memory://project-boundary")
        record_a = boundary.build_persistence_boundary_record(item_a)
        record_b = boundary.build_persistence_boundary_record(item_b)

        write_a = repository.upsert_record(record_a, write_time="2026-05-22T00:00:00Z")
        write_b = repository.upsert_record(record_b, write_time="2026-05-22T00:01:00Z")

        alpha_records = repository.list_records(project_key="alpha_proj")
        beta_records = repository.list_records(project_key="beta_proj")
        self.assertEqual(len(repository.list_records()), 2)
        self.assertEqual(len(alpha_records), 1)
        self.assertEqual(len(beta_records), 1)
        self.assertEqual(alpha_records[0].identity_ref, "alpha_proj:knowledge_item:ki:shared")
        self.assertEqual(beta_records[0].identity_ref, "beta_proj:knowledge_item:ki:shared")
        self.assertIsNotNone(repository.get_record("alpha_proj:knowledge_item:ki:shared"))
        self.assertIsNotNone(repository.get_record("beta_proj:knowledge_item:ki:shared"))
        self.assertEqual(write_a.status_before, None)
        self.assertEqual(write_b.status_before, None)

    def test_jsonl_repository_survives_reopen_without_claiming_live_db(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = boundary.JsonlTypedKnowledgeRepository(
                storage_dir=tmp_dir,
                repository_ref="jsonl://unit-test-typed-knowledge-readback",
            )
            envelope = boundary.build_sample_boundary_envelope()
            records = tuple(
                boundary.deserialize_persistence_boundary_record(record)
                for record in envelope["data"]["records"]
            )
            for record in records:
                repository.upsert_record(record, write_time="2026-05-22T00:00:00Z")

            reopened = repository.reopen()
            readback = boundary.build_persistence_api_envelope(repository=reopened, project_key="demo_proj")

        self.assertEqual(
            readback["data"]["repository"]["persistence_mode"],
            "jsonl_durable_contract",
        )
        self.assertFalse(readback["data"]["repository"]["live_db_write"])
        self.assertEqual(len(readback["data"]["records"]), 4)
        self.assertEqual(len(readback["data"]["writes"]), 0)
        self.assertEqual(len(reopened.list_writes()), 4)
        self.assertTrue(all(write.live_db_write is False for write in reopened.list_writes()))
        self.assertEqual(
            sorted(record["identity_ref"] for record in readback["data"]["records"]),
            sorted(record.identity_ref for record in records),
        )

    def test_api_envelope_rejects_live_db_or_ui_completion_overclaim(self):
        envelope = boundary.build_sample_boundary_envelope()
        envelope["meta"]["readiness"]["live_db_persistence"] = True

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persistence_api_envelope_overclaims_live_completion",
        ):
            boundary.validate_persistence_api_envelope(envelope)

        envelope = boundary.build_sample_boundary_envelope()
        envelope["data"]["writes"][0]["live_db_write"] = True

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persistence_api_envelope_live_write_claim_forbidden",
        ):
            boundary.validate_persistence_api_envelope(envelope)

    def test_handoff_refs_are_limited_to_writing_keyword_card_resource_boundary(self):
        record = boundary.PersistenceBoundaryRecord(
            contract_version=boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
            object_type=boundary.OBJECT_TYPE_KNOWLEDGE_ITEM,
            object_key="ki:bad-ref",
            project_key="demo_proj",
            identity_ref="demo_proj:knowledge_item:ki:bad-ref",
            visibility_scope=contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY,
            lifecycle_state=boundary.LIFECYCLE_STATE_ACTIVE,
            governance={
                "review_state": contracts.REVIEW_STATE_HUMAN_CONFIRMED,
                "visibility_scope": contracts.VISIBILITY_SCOPE_DOWNSTREAM_READY,
                "lifecycle_state": boundary.LIFECYCLE_STATE_ACTIVE,
            },
            writing_handoff_refs=(
                boundary.WritingHandoffRef(
                    contract_version=contracts.WRITING_KNOWLEDGE_HANDOFF_CONTRACT_VERSION,
                    knowledge_item_key="ki:bad-ref",
                    consumer="writing.unknown",
                    card_source_type="resource",
                ),
            ),
        )

        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "writing_handoff_ref_consumer_mismatch",
        ):
            boundary.validate_persistence_boundary_record(record)

    def test_public_api_route_contract_closes_route_gap_without_claiming_live_db(self):
        envelope = boundary.build_public_api_route_contract_envelope(project_key="route_proj")
        boundary.validate_public_api_route_contract_envelope(envelope)

        self.assertEqual(envelope["data"]["contract_version"], boundary.PUBLIC_API_ROUTE_CONTRACT_VERSION)
        self.assertEqual(envelope["data"]["route"]["path"], boundary.PUBLIC_API_ROUTE_PATH)
        self.assertTrue(envelope["meta"]["readiness"]["public_api_route"])
        self.assertTrue(envelope["meta"]["readiness"]["persisted_card_request_response_readback"])
        self.assertFalse(envelope["meta"]["readiness"]["live_db_persistence"])
        self.assertFalse(envelope["meta"]["readiness"]["live_api_closure"])
        self.assertFalse(envelope["meta"]["readiness"]["live_ui_closure"])
        self.assertNotIn(
            "public_typed_knowledge_api_route_not_implemented",
            envelope["meta"]["remaining_live_gaps"],
        )

        records = envelope["data"]["persistence_boundary"]["records"]
        item_record = next(record for record in records if record["object_type"] == "knowledge_item")
        self.assertEqual(item_record["project_key"], "route_proj")
        self.assertEqual(item_record["identity_ref"], "route_proj:knowledge_item:ki:robotics-policy")

        overclaim = copy.deepcopy(envelope)
        overclaim["meta"]["readiness"]["live_db_persistence"] = True
        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "public_api_route_live_completion_overclaim",
        ):
            boundary.validate_public_api_route_contract_envelope(overclaim)

    def test_live_db_backed_route_does_not_promote_expected_shape_to_live_closure(self):
        sample = boundary.build_sample_boundary_envelope(project_key="live_read_proj")
        records = tuple(
            boundary.deserialize_persistence_boundary_record(record)
            for record in sample["data"]["records"]
        )
        repository = _LiveRepositoryStub(records)

        with patch.object(boundary, "SqlAlchemyTypedKnowledgeRepository", return_value=repository):
            live_boundary = boundary.build_live_db_boundary_envelope(
                session=object(),
                project_key="live_read_proj",
                seed_sample=True,
            )
        envelope = boundary.build_public_api_route_contract_envelope(
            project_key="live_read_proj",
            boundary_envelope=live_boundary,
        )

        self.assertEqual(envelope["data"]["route"]["live_db_backed"], True)
        self.assertEqual(envelope["meta"]["readiness"]["live_db_persistence"], True)
        self.assertEqual(envelope["meta"]["readiness"]["live_api_closure"], False)
        self.assertEqual(envelope["meta"]["readiness"]["live_ui_closure"], False)
        self.assertEqual(envelope["meta"]["readiness"]["governance_ui"], False)
        self.assertIn(
            "live_api_request_response_closure_not_verified",
            envelope["meta"]["remaining_live_gaps"],
        )
        self.assertIn(
            "live_browser_ui_readback_not_verified",
            envelope["meta"]["remaining_live_gaps"],
        )

    def test_public_api_route_contract_serializes_non_authoritative_view(self):
        envelope = boundary.build_public_api_route_contract_envelope(project_key="view_proj")

        self.assertEqual(envelope["data"]["authoritative"], False)
        self.assertEqual(envelope["data"]["derived_as"], "view")
        boundary.validate_public_api_route_contract_envelope(envelope)

        overclaim = copy.deepcopy(envelope)
        overclaim["data"]["authoritative"] = True
        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "public_api_route_authority_overclaim",
        ):
            boundary.validate_public_api_route_contract_envelope(overclaim)

    def test_live_writing_context_read_projection_does_not_seed_empty_repository(self):
        repository = _LiveRepositoryStub()

        with (
            patch.object(boundary, "SqlAlchemyTypedKnowledgeRepository", return_value=repository),
            self.assertRaisesRegex(
                boundary.TypedKnowledgePersistenceBoundaryError,
                "persistence_api_envelope_missing_records",
            ),
        ):
            boundary.build_live_writing_context_from_repository(
                session=object(),
                project_key="empty_read_proj",
                seed_sample=True,
            )

        self.assertEqual(repository.upsert_calls, 0)

    def test_persisted_card_request_response_readback_preserves_ui_api_boundary_without_live_claims(self):
        envelope = boundary.build_public_api_route_contract_envelope(project_key="ui_proj")
        readback = envelope["data"]["persisted_card_request_response_readback"]
        boundary.validate_persisted_card_request_response_readback(readback)

        self.assertEqual(
            readback["contract_version"],
            boundary.PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION,
        )
        self.assertEqual(
            readback["typed_knowledge_api_boundary"]["route_path"],
            boundary.PUBLIC_API_ROUTE_PATH,
        )
        self.assertFalse(readback["typed_knowledge_api_boundary"]["live_db_backed"])

        persisted_doc = readback["persisted_document"]
        typed_context = persisted_doc["metadata_json"]["typed_knowledge_context"]
        request_body = readback["keyword_card_request"]["body"]
        response_body = readback["keyword_card_response"]["body"]

        self.assertFalse(persisted_doc["live_db_document"])
        self.assertEqual(typed_context["contract_version"], contracts.WRITING_KNOWLEDGE_CONTEXT_ENVELOPE_VERSION)
        self.assertEqual(request_body["context"]["typed_knowledge_context"], typed_context)
        self.assertIn("resource", request_body["sources"])
        self.assertEqual(response_body["cards"][0]["publisher"], "typed_knowledge")
        self.assertEqual(response_body["cards"][0]["source_type"], "resource")
        self.assertEqual(response_body["cards"][0]["extra"]["knowledge_item_key"], "ki:robotics-policy")
        self.assertTrue(readback["readback"]["request_response_readback"])
        self.assertFalse(readback["meta"]["readiness"]["live_db_persistence"])
        self.assertFalse(readback["meta"]["readiness"]["live_api_closure"])
        self.assertFalse(readback["meta"]["readiness"]["live_ui_closure"])
        self.assertIn(
            "live_api_request_response_closure_not_verified",
            readback["meta"]["remaining_live_gaps"],
        )

    def test_persisted_card_readback_serializes_non_authoritative_simulation(self):
        sample = boundary.build_sample_boundary_envelope(project_key="simulation_proj")

        readback = boundary.build_persisted_card_request_response_readback(
            project_key="simulation_proj",
            boundary_envelope=sample,
            live_db_backed=True,
        )

        self.assertEqual(readback["authoritative"], False)
        self.assertEqual(readback["derived_as"], "simulation")
        self.assertEqual(readback["keyword_card_response"]["authoritative"], False)
        self.assertEqual(readback["keyword_card_response"]["derived_as"], "simulation")
        self.assertEqual(
            readback["keyword_card_response"]["source"],
            "repo_local_simulated_response_shape",
        )
        self.assertEqual(readback["persisted_document"]["source"], "typed_knowledge_local_expected_document")
        self.assertEqual(readback["persisted_document"]["live_db_document"], False)
        self.assertEqual(readback["meta"]["readiness"]["live_db_persistence"], True)
        self.assertEqual(readback["meta"]["readiness"]["live_api_closure"], False)
        self.assertEqual(readback["meta"]["readiness"]["live_ui_closure"], False)
        self.assertEqual(readback["meta"]["readiness"]["governance_ui"], False)

        overclaim = copy.deepcopy(readback)
        overclaim["authoritative"] = True
        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persisted_card_readback_authority_overclaim",
        ):
            boundary.validate_persisted_card_request_response_readback(overclaim)

    def test_persisted_card_simulation_rejects_live_writing_document_overclaim(self):
        sample = boundary.build_sample_boundary_envelope(project_key="document_overclaim_proj")
        readback = boundary.build_persisted_card_request_response_readback(
            project_key="document_overclaim_proj",
            boundary_envelope=sample,
            live_db_backed=True,
        )

        overclaim = copy.deepcopy(readback)
        overclaim["persisted_document"]["source"] = "typed_knowledge_live_db_readback"
        overclaim["persisted_document"]["live_db_document"] = True
        with self.assertRaisesRegex(
            boundary.TypedKnowledgePersistenceBoundaryError,
            "persisted_card_readback_invalid_persisted_document",
        ):
            boundary.validate_persisted_card_request_response_readback(overclaim)

    def test_typed_knowledge_write_project_key_rejects_normalize_to_fallback(self):
        api_module = _load_typed_knowledge_api_module()

        for invalid_project_key in ("!!!", "___", "public"):
            resolved, error = api_module._required_write_project_key(
                invalid_project_key,
                route_path=boundary.PUBLIC_API_ROUTE_PATH,
            )
            self.assertIsNone(resolved)
            self.assertEqual(
                error["message"],
                "project_key must retain an explicit writable identity after normalization",
            )
            self.assertEqual(error["details"]["route_path"], boundary.PUBLIC_API_ROUTE_PATH)

        self.assertEqual(
            api_module._required_write_project_key(
                "default",
                route_path=boundary.PUBLIC_API_ROUTE_PATH,
            ),
            ("default", None),
        )

    def test_durable_repository_readback_contract_keeps_live_boundaries_open(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repository = boundary.JsonlTypedKnowledgeRepository(
                storage_dir=tmp_dir,
                repository_ref="jsonl://unit-test-typed-knowledge-readback",
            )
            check = boundary.check_durable_repository_readback_contract(repository=repository)
            replay = boundary.check_durable_repository_readback_contract(repository=repository)

        self.assertEqual(
            check["contract_version"],
            boundary.DURABLE_REPOSITORY_READBACK_CONTRACT_VERSION,
        )
        self.assertEqual(check["status"], "pass")
        self.assertEqual(replay["status"], "pass")
        self.assertTrue(check["durable_readback"])
        self.assertFalse(check["live_db_write"])
        self.assertFalse(check["live_db_persistence"])
        self.assertTrue(check["public_api_route"])
        self.assertFalse(check["governance_ui"])
        self.assertIn("jsonl_repository_write_readback", check["closed_slice"])
        self.assertIn(
            "live_db_backed_typed_knowledge_readback_not_verified",
            check["remaining_live_gaps"],
        )


if __name__ == "__main__":
    unittest.main()
