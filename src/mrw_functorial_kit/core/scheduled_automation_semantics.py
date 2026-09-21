"""Registration projection for scheduled automation checker evidence.

The checker in ``scripts/check_scheduled_automation_artifacts.py`` remains the
source of its constants and report shape.  This module registers a read-only
wire projection for an existing report; it does not execute a scheduled run or
manufacture evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, get_args

from functorial_kit import define_codec, define_failure_family, define_vocabulary


ScheduledAutomationStatus = Literal["passed", "blocked"]
ScheduledAutomationClassification = Literal[
    "scheduled_run_evidence",
    "scheduled_run_blocked",
    "manual_dry_run",
    "missing",
]
ScheduledAutomationBlockerClassification = Literal[
    "scheduler_not_observed",
    "scheduler_configured_pending_run",
    "scheduler_ran_no_artifact",
    "artifact_wrong_path",
    "artifact_present_checker_mismatch",
    "scheduled_run_blocked",
]
MatrixValidStatus = Literal["passed", "partial"]
IdentityWarningSeverity = Literal["warning"]
ScheduleSourceKey = Literal[
    "trigger",
    "run_trigger",
    "source",
    "run_source",
    "execution_source",
    "invocation_source",
    "origin",
    "created_by",
]
ScheduleSourceValue = Literal[
    "scheduled",
    "scheduler",
    "cron",
    "codex_app",
    "codex_app_scheduler",
    "codex_app_cron",
    "scheduled_run",
    "scheduled_run_evidence",
]
ScheduledAutomationFailureCode = Literal[
    "report_not_object",
    "report_status_invalid",
    "checker_contract_invalid",
]

scheduled_automation_statuses = define_vocabulary(
    "scheduled.automation.evidence.status", get_args(ScheduledAutomationStatus)
)
scheduled_automation_classifications = define_vocabulary(
    "scheduled.automation.evidence.classification",
    get_args(ScheduledAutomationClassification),
)
scheduled_automation_blocker_classifications = define_vocabulary(
    "scheduled.automation.evidence.blocker_classification",
    get_args(ScheduledAutomationBlockerClassification),
)
matrix_valid_statuses = define_vocabulary(
    "scheduled.automation.evidence.matrix_valid_status", get_args(MatrixValidStatus)
)
identity_warning_severities = define_vocabulary(
    "scheduled.automation.evidence.identity_warning_severity",
    get_args(IdentityWarningSeverity),
)
schedule_source_keys = define_vocabulary(
    "scheduled.automation.evidence.schedule_source_key", get_args(ScheduleSourceKey)
)
schedule_source_values = define_vocabulary(
    "scheduled.automation.evidence.schedule_source_value",
    get_args(ScheduleSourceValue),
)
scheduled_automation_failures = define_failure_family(
    "scheduled.automation.evidence.failure",
    get_args(ScheduledAutomationFailureCode),
)


def _parse_report(value: Mapping[str, Any]) -> Mapping[str, Any]:
    status = value.get("status")
    if status not in scheduled_automation_statuses.members:
        return scheduled_automation_failures.fail(
            "report_status_invalid",
            "report status is outside the closed checker vocabulary",
            {"status": status},
        )
    return value


scheduled_automation_report_codec = define_codec(
    name="scheduled.automation.evidence.report",
    discriminant="scheduled_automation_artifact_evidence.v1",
    discriminant_key="schema_version",
    keys=(
        "schema_version",
        "status",
        "observed_at",
        "classifications",
        "blocker_classifications",
        "summary",
        "recommended_command",
        "lanes",
    ),
    parse=_parse_report,
    to_wire=lambda report: report,
)


__all__ = [
    "identity_warning_severities",
    "matrix_valid_statuses",
    "schedule_source_keys",
    "schedule_source_values",
    "scheduled_automation_blocker_classifications",
    "scheduled_automation_classifications",
    "scheduled_automation_failures",
    "scheduled_automation_report_codec",
    "scheduled_automation_statuses",
]
