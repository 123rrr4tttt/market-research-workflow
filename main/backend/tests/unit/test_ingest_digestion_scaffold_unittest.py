import importlib.util
import pathlib
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


contracts = _load_module("ingest_digestion_contracts", "app/contracts/ingest_digestion.py")
scaffold = _load_module("ingest_digestion_scaffold", "app/services/ingest/digestion_scaffold.py")


class IngestDigestionScaffoldTests(unittest.TestCase):
    def test_classify_input_kind_for_derived_and_raw_import(self):
        kind_report = scaffold.classify_input_kind(artifact_source="llm_report")
        kind_raw = scaffold.classify_input_kind(entrypoint="ingest.raw_import")
        self.assertEqual(kind_report.value, contracts.IngestInputKind.DERIVED_LLM_REPORT.value)
        self.assertEqual(kind_raw.value, contracts.IngestInputKind.RAW_IMPORT.value)

    def test_select_digestion_decision_prefers_extract_for_structured_json(self):
        decision = scaffold.select_digestion_decision(
            input_kind=contracts.IngestInputKind.URL_DRIVEN_EXTERNAL,
            content_format=contracts.ContentFormat.STRUCTURED_JSON,
            content_length=200,
        )
        self.assertEqual(decision.stage.value, contracts.DigestionStage.EXTRACT_FIRST.value)
        self.assertTrue(decision.extract_required)
        self.assertFalse(decision.chunking_required)

    def test_select_digestion_decision_prefers_chunk_for_long_report(self):
        decision = scaffold.select_digestion_decision(
            input_kind=contracts.IngestInputKind.REPORT_SHAPED,
            content_format=contracts.ContentFormat.MARKDOWN,
            content_length=12000,
        )
        self.assertEqual(decision.stage.value, contracts.DigestionStage.CHUNK_FIRST.value)
        self.assertTrue(decision.chunking_required)

    def test_build_time_semantics_derives_window_bounds(self):
        semantics = scaffold.build_time_semantics(
            processed_time="2026-03-08T10:00:00Z",
            task_window="30d",
        )
        self.assertEqual(semantics.task_window_start, date(2026, 2, 7))
        self.assertEqual(semantics.task_window_end, date(2026, 3, 8))

    def test_build_normalized_ingest_envelope_sets_defaults(self):
        envelope = scaffold.build_normalized_ingest_envelope(
            project_key="demo_proj",
            entrypoint="ingest.single_url",
            source_locator="https://example.com/report.html",
            text_sample="<html><body>demo</body></html>",
            processed_time="2026-03-08T11:00:00Z",
        )
        self.assertEqual(envelope.input_kind.value, contracts.IngestInputKind.URL_DRIVEN_EXTERNAL.value)
        self.assertEqual(envelope.content_format.value, contracts.ContentFormat.HTML.value)
        self.assertEqual(
            envelope.requested_downstream_targets,
            ["resource_pool", "report_generation", "writing"],
        )


if __name__ == "__main__":
    unittest.main()
