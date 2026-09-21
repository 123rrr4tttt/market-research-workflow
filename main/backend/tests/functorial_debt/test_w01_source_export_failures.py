"""W01 typed failure outcomes and concentrated public ABI lifts."""

from __future__ import annotations

import pytest
from functorial_kit import Failure

from app.services.llm_report_export import (
    LlmReportExportTokenError,
    _report_export_failure,
    render_markdown_export,
    verify_llm_report_export_token,
)
from app.services.local_index.embedding_provider import (
    RepoLocalHashingEmbeddingProvider,
    _embedding_failure,
)
from app.services.source_library import external_project as external
from app.services.source_library import external_project_registration as registration
from app.services.source_library import external_project_registry as registry
from app.services.source_library import loader
from app.services.source_library import resolver
from app.services.source_library import runner
from app.services.source_library.orchestrators import single_channel
from app.services.source_library.single_source_guard import (
    SourceLibrarySingleSourceGuardError,
    _guard_failure,
    validate_single_source_guard,
)


def test_w01_failure_constructors_use_registered_families() -> None:
    outcomes = [
        external._manifest_failure("external_project_manifest_invalid", "bad", site="test"),
        registration._registration_failure("external_project_evidence_insufficient", "weak", site="test"),
        registry._provider_failure("external_project_execution_mode_unsupported", "bad", site="test"),
        runner._runner_failure("required_params_missing", "missing", site="test"),
        resolver._resolver_failure("url_routing_urls_required", "urls", site="test"),
        loader._loader_failure("yaml_parser_unavailable", "missing yaml", site="test"),
        resolver._parallel_failure(
            "parallel_item_failed",
            "worker failed",
            site="test",
            public_exception="RuntimeError",
        ),
        single_channel._orchestrator_failure("channel_not_found", "missing", site="test"),
        _embedding_failure("embedding_dimension_invalid", "bad dim", site="test"),
        _report_export_failure("unsupported_export_format", "bad format", site="test", public_exception="ValueError"),
        _guard_failure(
            "single_source_guard_blocked",
            "blocked",
            details={"reason_code": "single_source_guard_blocked"},
        ),
    ]
    assert all(isinstance(outcome, Failure) for outcome in outcomes)
    assert {outcome.family for outcome in outcomes} == {
        "source_library.contract_failure",
        "source_library.loader.failure",
        "source_library.resolver.failure",
        "indexer.policy.failure",
        "llm.report.request.failure",
        "source_library.single_source_guard.failure",
    }


def test_w01_external_manifest_abi_still_raises_value_error() -> None:
    with pytest.raises(ValueError, match="contract_version"):
        external.normalize_external_project_manifest({})


def test_w01_single_source_guard_abi_preserves_details() -> None:
    with pytest.raises(SourceLibrarySingleSourceGuardError) as raised:
        validate_single_source_guard({"single_source_guard": {}})
    assert raised.value.details["reason_code"] == "single_source_guard_strict_source_required"


def test_w01_embedding_dimension_abi_still_raises_value_error() -> None:
    with pytest.raises(ValueError, match="embedding_dim must be at least 8"):
        RepoLocalHashingEmbeddingProvider(4)


def test_w01_report_export_token_failure_is_typed_before_abi_lift() -> None:
    with pytest.raises(LlmReportExportTokenError, match="invalid_export_token_format"):
        verify_llm_report_export_token("bad", markdown="# report", token_secret="secret")
    with pytest.raises(ValueError, match="unsupported export format"):
        render_markdown_export("# report", "txt")  # type: ignore[arg-type]


def test_w01_loader_yaml_dependency_failure_is_typed_before_runtime_error_lift(tmp_path, monkeypatch) -> None:
    yaml_path = tmp_path / "library.yaml"
    yaml_path.write_text("items: []", encoding="utf-8")
    original_import = __import__

    def missing_yaml(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("pyyaml missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing_yaml)
    outcome = loader.try_load_single_file(yaml_path)
    assert isinstance(outcome, Failure)
    assert outcome.family == "source_library.loader.failure"
    assert outcome.code == "yaml_parser_unavailable"
    with pytest.raises(RuntimeError, match=f"Cannot parse YAML file {yaml_path}; install pyyaml or use JSON files\\.") as raised:
        loader._load_single_file(yaml_path)
    assert isinstance(raised.value.__cause__, ImportError)

    no_cause = loader._loader_failure(
        "yaml_parser_unavailable",
        "Cannot parse YAML without a captured cause.",
        site="test.no_cause",
    )
    with pytest.raises(RuntimeError, match="Cannot parse YAML without a captured cause\\.") as raised_no_cause:
        loader._raise_loader_failure(no_cause)
    assert raised_no_cause.value.__cause__ is None


def test_w01_resolver_parallel_failures_are_typed_before_legacy_lift() -> None:
    failure = RuntimeError("worker failed")
    outcome = resolver._try_run_tasks_with_concurrency_plan(
        values=["value"],
        worker=lambda _value: (_ for _ in ()).throw(failure),
        max_workers=1,
        timeout_seconds=None,
        fail_fast=True,
        thread_name_prefix="w01-test",
    )
    assert isinstance(outcome, Failure)
    assert outcome.family == "source_library.resolver.failure"
    assert outcome.code == "parallel_item_failed"
    assert outcome.context["cause"] is failure
    with pytest.raises(RuntimeError) as raised:
        resolver._run_tasks_with_concurrency_plan(
            values=["value"],
            worker=lambda _value: (_ for _ in ()).throw(failure),
            max_workers=1,
            timeout_seconds=None,
            fail_fast=True,
            thread_name_prefix="w01-test",
        )
    assert raised.value is failure

    with pytest.raises(TimeoutError, match="w01-timeout timeout after 0.010s"):
        resolver._run_tasks_with_concurrency_plan(
            values=["value"],
            worker=lambda _value: __import__("time").sleep(0.05),
            max_workers=2,
            timeout_seconds=0.01,
            fail_fast=True,
            thread_name_prefix="w01-timeout",
        )


def test_w01_disabled_source_item_is_typed_before_value_error_lift() -> None:
    failure = resolver._resolver_failure(
        "source_item_disabled",
        "source item disabled: disabled.item",
        site="run_item_payload.item_disabled",
        item_key="disabled.item",
    )
    assert failure.family == "source_library.contract_failure"
    assert failure.code == "source_item_disabled"
    with pytest.raises(ValueError, match="source item disabled: disabled.item"):
        resolver.run_item_payload(item={"item_key": "disabled.item", "enabled": False})
