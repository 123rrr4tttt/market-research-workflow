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


def _valid_scheduler_kwargs():
    return {
        "task_goal": "Digest weekly report inputs",
        "project_key": "demo_proj",
        "entrypoint": "ingest.raw_import",
        "source_locator": "file:///tmp/weekly-report.md",
        "content_format": "markdown",
        "content_length": 8000,
        "processed_time": "2026-03-08T11:00:00Z",
        "candidate_windows": ["7d", "30d"],
        "selected_window": "7d",
        "cadence": "weekly",
        "scheduler_ref": "contract.scheduler.ingest-long-cycle",
        "persistent_ref": "fake-db://long_cycle_persistent_tasks",
        "event_time": "2026-03-08T11:00:00Z",
        "run_at": "2026-03-08T11:02:00Z",
    }


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
        self.assertEqual(semantics.effective_time.isoformat(), "2026-03-08T10:00:00+00:00")
        self.assertEqual(semantics.time_provenance, "processed_time_fallback")
        self.assertEqual(semantics.task_window_start, date(2026, 2, 7))
        self.assertEqual(semantics.task_window_end, date(2026, 3, 8))

    def test_build_time_semantics_prefers_source_time_and_anchors_window(self):
        semantics = scaffold.build_time_semantics(
            source_time="2026-03-01T08:00:00Z",
            processed_time="2026-03-10T10:00:00Z",
            task_window="7d",
        )
        self.assertEqual(semantics.effective_time.isoformat(), "2026-03-01T08:00:00+00:00")
        self.assertEqual(semantics.time_provenance, "source_time")
        self.assertEqual(semantics.task_window_start, date(2026, 2, 23))
        self.assertEqual(semantics.task_window_end, date(2026, 3, 1))

    def test_build_time_semantics_rejects_far_future_source_time(self):
        semantics = scaffold.build_time_semantics(
            source_time="2026-03-20T08:00:00Z",
            processed_time="2026-03-10T10:00:00Z",
            task_window="7d",
        )
        self.assertEqual(semantics.effective_time.isoformat(), "2026-03-10T10:00:00+00:00")
        self.assertEqual(semantics.time_provenance, "source_time_future_rejected")
        self.assertEqual(semantics.task_window_start, date(2026, 3, 4))
        self.assertEqual(semantics.task_window_end, date(2026, 3, 10))

    def test_build_normalized_ingest_envelope_sets_defaults(self):
        envelope = scaffold.build_normalized_ingest_envelope(
            project_key="demo_proj",
            entrypoint="ingest.url.single",
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

    def test_build_long_cycle_task_object_freezes_template_and_snapshot(self):
        task = scaffold.build_long_cycle_task_object(
            task_goal="Refresh report-shaped source bundle",
            input_selector={"project_key": "demo_proj", "source_locator": "https://example.com/report.pdf"},
            candidate_windows=["30d", "7d", "30d"],
            cadence="weekly",
            selected_window="30d",
            status="ready",
            updated_at="2026-03-08T11:00:00Z",
        )
        self.assertEqual(task.task_goal, "Refresh report-shaped source bundle")
        self.assertEqual(task.candidate_windows, ["30d", "7d"])
        self.assertEqual(task.last_run_snapshot.status.value, contracts.LongCycleTaskStatus.READY.value)
        self.assertEqual(task.last_run_snapshot.selected_window, "30d")

    def test_long_cycle_status_checker_marks_ready_for_valid_report_path(self):
        status = scaffold.check_long_cycle_automation_status(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
        )
        self.assertEqual(status["contract_version"], "ingest.long_cycle_automation_status.v1")
        self.assertEqual(status["status"], contracts.LongCycleTaskStatus.READY.value)
        self.assertEqual(status["blockers"], [])
        self.assertEqual(status["task"]["candidate_windows"], ["7d", "30d"])
        self.assertEqual(status["digestion_decision"]["stage"], contracts.DigestionStage.CHUNK_FIRST.value)

    def test_long_cycle_status_checker_blocks_invalid_window_and_missing_scope(self):
        status = scaffold.check_long_cycle_automation_status(
            task_goal="Digest",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["weekly"],
            selected_window="7d",
        )
        self.assertEqual(status["status"], contracts.LongCycleTaskStatus.BLOCKED.value)
        self.assertIn("invalid_candidate_windows:weekly", status["blockers"])
        self.assertIn("selected_window_not_in_candidate_windows", status["blockers"])
        self.assertIn("missing_input_scope", status["blockers"])

    def test_long_cycle_lifecycle_contract_builds_stable_persistent_record(self):
        first = scaffold.check_long_cycle_lifecycle_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
            event_time="2026-03-08T11:00:00Z",
        )
        second = scaffold.check_long_cycle_lifecycle_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["30d", "7d"],
            selected_window="7d",
            cadence="weekly",
            event_time="2026-03-09T11:00:00Z",
        )
        self.assertEqual(first["status"], "pass")
        self.assertEqual(first["persistent_task"]["status"], contracts.LongCycleTaskStatus.READY.value)
        self.assertTrue(first["persistent_task"]["task_key"].startswith("ingest-lc-"))
        self.assertEqual(first["persistent_task"]["task_key"], second["persistent_task"]["task_key"])
        self.assertIn("persistent_task_record_shape", first["closed_slice"])
        self.assertEqual(
            first["remaining_runtime_gaps"],
            [
                "live_scheduler_dispatch_not_executed",
                "persistent_task_table_write_not_executed",
                "end_to_end_automation_run_not_executed",
            ],
        )

    def test_long_cycle_lifecycle_contract_requires_selected_window_for_dispatch(self):
        status = scaffold.check_long_cycle_lifecycle_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            cadence="weekly",
        )
        self.assertEqual(status["status"], "fail")
        self.assertIn("missing_selected_window_for_lifecycle_dispatch", status["blockers"])
        self.assertEqual(status["persistent_task"]["status"], contracts.LongCycleTaskStatus.BLOCKED.value)

    def test_long_cycle_persistent_task_record_transitions_through_dry_run_lifecycle(self):
        status = scaffold.check_long_cycle_lifecycle_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
        )
        running = scaffold.transition_long_cycle_persistent_task_record(
            status["persistent_task"],
            transition="dispatch",
            dispatch_ref="dry-run-dispatch-001",
            event_time="2026-03-08T11:02:00Z",
            reason="dispatch accepted",
        )
        completed = scaffold.transition_long_cycle_persistent_task_record(
            running,
            transition="succeed",
            output_ref="dry-run://digestion/status/demo_proj/2026-03-08",
            event_time="2026-03-08T11:05:00Z",
            reason="digestion status snapshot written",
        )
        self.assertEqual(running.status.value, contracts.LongCycleTaskStatus.RUNNING.value)
        self.assertEqual(completed.status.value, contracts.LongCycleTaskStatus.SUCCEEDED.value)
        self.assertEqual(completed.attempt_count, 1)
        self.assertEqual([event.transition.value for event in completed.lifecycle_events], ["mark_ready", "dispatch", "succeed"])
        self.assertEqual(completed.task.last_run_snapshot.output_ref, "dry-run://digestion/status/demo_proj/2026-03-08")

    def test_long_cycle_persistent_task_record_rejects_invalid_transitions(self):
        status = scaffold.check_long_cycle_lifecycle_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
        )
        with self.assertRaisesRegex(ValueError, "dispatch_ref is required"):
            scaffold.transition_long_cycle_persistent_task_record(
                status["persistent_task"],
                transition="dispatch",
            )
        with self.assertRaisesRegex(ValueError, "invalid long-cycle transition"):
            scaffold.transition_long_cycle_persistent_task_record(
                status["persistent_task"],
                transition="succeed",
                output_ref="dry-run://already-complete",
            )

    def test_long_cycle_scheduler_e2e_contract_records_dispatch_intent_and_fake_db_writes(self):
        check = scaffold.check_long_cycle_scheduler_e2e_contract(
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["7d", "30d"],
            selected_window="7d",
            cadence="weekly",
            scheduler_ref="contract.scheduler.ingest-long-cycle",
            persistent_ref="fake-db://long_cycle_persistent_tasks",
            event_time="2026-03-08T11:00:00Z",
            run_at="2026-03-08T11:02:00Z",
        )
        self.assertEqual(check["contract_version"], "ingest.long_cycle_scheduler_e2e_contract_check.v1")
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["dispatch_intent"]["task_key"], check["persistent_task"]["task_key"])
        self.assertEqual(check["dispatch_intent"]["selected_window"], "7d")
        self.assertFalse(check["dispatch_intent"]["live_dispatch"])
        self.assertEqual(check["completed_record"]["status"], contracts.LongCycleTaskStatus.SUCCEEDED.value)
        self.assertEqual(
            [write["status_after"] for write in check["persistence_writes"]],
            [
                contracts.LongCycleTaskStatus.READY.value,
                contracts.LongCycleTaskStatus.RUNNING.value,
                contracts.LongCycleTaskStatus.SUCCEEDED.value,
            ],
        )
        self.assertTrue(all(write["live_db_write"] is False for write in check["persistence_writes"]))
        self.assertIn("scheduler_dispatch_intent", check["closed_slice"])
        self.assertIn("fake_repository_db_table_write_abstraction", check["closed_slice"])
        self.assertEqual(
            check["remaining_runtime_gaps"],
            [
                "live_scheduler_dispatch_not_executed",
                "live_persistent_task_table_write_not_executed",
                "production_worker_task_not_executed",
                "end_to_end_automation_run_not_executed",
            ],
        )

    def test_long_cycle_scheduler_e2e_contract_persists_to_fake_repository_for_readback(self):
        repository = scaffold.InMemoryLongCycleTaskRepository(
            repository_ref="fake-db://unit-test-long-cycle",
            logical_table="long_cycle_persistent_tasks",
        )
        check = scaffold.check_long_cycle_scheduler_e2e_contract(
            repository=repository,
            task_goal="Digest weekly report inputs",
            project_key="demo_proj",
            entrypoint="ingest.raw_import",
            source_locator="file:///tmp/weekly-report.md",
            content_format="markdown",
            content_length=8000,
            processed_time="2026-03-08T11:00:00Z",
            candidate_windows=["30d", "7d"],
            selected_window="7d",
            cadence="weekly",
            scheduler_ref="contract.scheduler.ingest-long-cycle",
            persistent_ref="fake-db://long_cycle_persistent_tasks",
            event_time="2026-03-08T11:00:00Z",
            run_at="2026-03-08T11:02:00Z",
        )
        stored = repository.get_task_record(check["persistent_task"]["task_key"])
        self.assertIsNotNone(stored)
        self.assertEqual(stored.status.value, contracts.LongCycleTaskStatus.SUCCEEDED.value)
        self.assertEqual(
            [write.status_after.value for write in repository.list_writes()],
            [
                contracts.LongCycleTaskStatus.READY.value,
                contracts.LongCycleTaskStatus.RUNNING.value,
                contracts.LongCycleTaskStatus.SUCCEEDED.value,
            ],
        )
        self.assertIsNone(check["persistence_writes"][0]["status_before"])
        self.assertEqual(check["persistence_writes"][1]["status_before"], contracts.LongCycleTaskStatus.READY.value)
        self.assertEqual(check["persistence_writes"][2]["status_before"], contracts.LongCycleTaskStatus.RUNNING.value)

    def test_long_cycle_scheduler_readiness_marks_local_ready_without_live_closure(self):
        check = scaffold.check_long_cycle_scheduler_readiness_contract(**_valid_scheduler_kwargs())

        self.assertEqual(check["contract_version"], "ingest.long_cycle_scheduler_readiness_check.v1")
        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["readiness_state"], "local_deterministic_dry_run_ready")
        self.assertTrue(check["local_deterministic_readiness"])
        self.assertTrue(check["dry_run_dispatch_ready"])
        self.assertFalse(check["live_scheduler_closure_validated"])
        self.assertFalse(check["closure_claim"])
        self.assertEqual(check["scheduler_e2e_contract"]["status"], "pass")
        stages = {stage["name"]: stage for stage in check["stages"]}
        self.assertEqual(stages["deterministic_scheduler_e2e_contract"]["status"], "passed")
        self.assertEqual(stages["scheduler_dry_run_dispatch_plan"]["status"], "ready")
        self.assertEqual(stages["live_scheduler_closure"]["status"], "not_configured")
        self.assertIn("configure and start the scheduler runtime", " ".join(check["remaining_runtime_gaps"]))

    def test_long_cycle_scheduler_readiness_blocks_incomplete_live_evidence(self):
        check = scaffold.check_long_cycle_scheduler_readiness_contract(
            **_valid_scheduler_kwargs(),
            scheduler_runtime_configured=True,
            live_scheduler_evidence={"live_scheduler_dispatch_executed": True},
        )

        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["readiness_state"], "local_deterministic_dry_run_ready")
        self.assertFalse(check["closure_claim"])
        stages = {stage["name"]: stage for stage in check["stages"]}
        self.assertEqual(stages["live_scheduler_closure"]["status"], "failed_evidence")
        self.assertIn("production_worker_task_executed", stages["live_scheduler_closure"]["detail"])
        self.assertIn("do not claim long-cycle live scheduler closure", " ".join(check["remaining_runtime_gaps"]))

    def test_long_cycle_scheduler_readiness_can_record_complete_live_scheduler_evidence(self):
        check = scaffold.check_long_cycle_scheduler_readiness_contract(
            **_valid_scheduler_kwargs(),
            scheduler_runtime_configured=True,
            live_scheduler_evidence={
                "live_scheduler_dispatch_executed": True,
                "recurring_schedule_registered": True,
                "production_worker_task_executed": True,
                "live_persistent_task_table_write": True,
                "digestion_output_readback": True,
                "downstream_handoff_observed": True,
            },
        )

        self.assertEqual(check["status"], "pass")
        self.assertEqual(check["readiness_state"], "live_scheduler_closure_validated")
        self.assertTrue(check["live_scheduler_closure_validated"])
        self.assertTrue(check["closure_claim"])
        self.assertEqual(check["remaining_runtime_gaps"], [])


if __name__ == "__main__":
    unittest.main()
