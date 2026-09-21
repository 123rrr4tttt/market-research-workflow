"""W01 request-failure family and legacy ABI witnesses."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from functorial_kit import Failure
from functorial_kit.arch.gates import scan_project

from app.services import keyword_memory, report, task_readback_metadata
from app.services.llm_report_export_token_state import (
    _request_failure as token_request_failure,
    _validate_retention_days,
)
from app.services.llm_report_generator import _request_failure as report_request_failure
from app.services.llm_report_generator import build_structured_report
from app.services.stats import prompt_time_density
from mrw_functorial_kit.core.application_failure_semantics import (
    keyword_memory_contract_failures,
    llm_report_request_failures,
    prompt_time_density_request_failures,
    report_query_contract_failures,
    task_readback_contract_failures,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED_FILES = {
    "main/backend/app/services/keyword_memory.py",
    "main/backend/app/services/report.py",
    "main/backend/app/services/task_readback_metadata.py",
    "main/backend/app/services/stats/prompt_time_density.py",
    "main/backend/app/services/llm_report_export_token_state.py",
    "main/backend/app/services/llm_report_generator.py",
}


def test_w01_request_failure_families_are_closed() -> None:
    specimens = [
        keyword_memory._keyword_failure("keyword is required", operation="test"),
        report._report_query_failure("start must be YYYY-MM-DD", operation="test", field="start"),
        task_readback_metadata._task_readback_failure("line_key is required", operation="test"),
        prompt_time_density._request_failure("bucket_invalid", "bad bucket", operation="test"),
        token_request_failure("retention_days_invalid", "retention_days must be >= 1", operation="test"),
        report_request_failure("topic_required", "topic cannot be empty", operation="test"),
    ]
    families = {
        keyword_memory_contract_failures,
        report_query_contract_failures,
        task_readback_contract_failures,
        prompt_time_density_request_failures,
        llm_report_request_failures,
    }
    assert all(type(value) is Failure for value in specimens)
    assert all(any(family.matches(value) for family in families) for value in specimens)


def test_w01_request_failure_public_abi_is_preserved() -> None:
    with pytest.raises(ValueError, match="^keyword is required$"):
        keyword_memory.upsert_keyword_prior(keyword="   ")
    with pytest.raises(ValueError, match="^start must be YYYY-MM-DD$"):
        report.generate_html_report([], "bad", None)
    with pytest.raises(ValueError, match="^line_key is required for runtime readback metadata$"):
        task_readback_metadata.build_runtime_readback_payload(line_key="   ")
    with pytest.raises(ValueError, match="^bucket must be one of: day, week, month$"):
        prompt_time_density.query_prompt_time_density(
            start=date(2024, 1, 1), end=date(2024, 1, 2), bucket="quarter"
        )
    with pytest.raises(ValueError, match="^retention_days must be >= 1$"):
        from app.services.llm_report_export_token_state import prune_llm_report_export_token_states

        prune_llm_report_export_token_states(0)
    with pytest.raises(ValueError, match="^topic cannot be empty$"):
        build_structured_report("   ", [])


def test_w01_request_failures() -> None:
    """Boundary metadata witness for the retained request-service ABI lifts."""

    test_w01_request_failure_public_abi_is_preserved()


def test_w01_request_failure_core_outcomes_are_total() -> None:
    assert isinstance(prompt_time_density._bucket_outcome(date(2024, 1, 1), "quarter"), Failure)
    assert isinstance(prompt_time_density._window_days_outcome("bad"), Failure)
    assert isinstance(prompt_time_density._smoothing_outcome([1.0, 2.0, 3.0], "bad"), Failure)
    assert isinstance(_validate_retention_days("bad"), Failure)
    assert isinstance(report._parse_date_outcome("bad", field="start"), Failure)


def test_w01_request_failure_no_throw_scan_is_clear() -> None:
    scan = scan_project(REPO_ROOT)
    assert {
        violation.file
        for violation in scan.violations
        if violation.gate == "no-throw-in-core"
        and violation.severity == "fail"
        and violation.file in OWNED_FILES
    } == set()


def test_w01_request_failure_lifts_reject_wrong_family() -> None:
    with pytest.raises(TypeError, match="failure lift context is incomplete"):
        keyword_memory._raise_keyword_failure(
            Failure("other.family", "keyword_required", "bad")
        )
