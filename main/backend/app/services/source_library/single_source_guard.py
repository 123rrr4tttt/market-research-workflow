from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Annotated, NoReturn, TypeGuard

from functorial_kit import Failure

from mrw_functorial_kit.core.w06_semantics import source_single_source_guard_failures


GuardObject = dict[str, object]


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, dict)


def _is_guard_object(value: object) -> TypeGuard[GuardObject]:
    return _is_object_mapping(value) and all(isinstance(key, str) for key in value)


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


class SourceLibrarySingleSourceGuardError(ValueError):
    def __init__(self, message: str, *, details: GuardObject) -> None:
        super().__init__(message)
        self.details = details


_FAILURE_WITNESS = "test:test_w01_source_export_failures"


def _guard_failure(
    code: str,
    message: str,
    *,
    details: GuardObject,
) -> Failure:
    context = {
        "boundary_class": "PURE_CONTRACT_FAILURE",
        "failure_family": source_single_source_guard_failures.name,
        "operation": "source_library.single_source_guard",
        "owner": "source_library.single_source_guard",
        "public_exception": "SourceLibrarySingleSourceGuardError",
        "public_message": message,
        "site": "validate_single_source_guard",
        "witness": _FAILURE_WITNESS,
        "details": details,
    }
    return source_single_source_guard_failures.fail(code, message, context)


def _raise_guard_failure(failure: Failure, *, details: GuardObject) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_single_source_guard_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_single_source_guard_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "SourceLibrarySingleSourceGuardError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source.single-source-guard.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_source_export_failures
        raise TypeError("single-source guard failure lift context is incomplete or inconsistent")
    # kit:boundary owner=source.single-source-guard.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source.single-source-guard.failure witness=test:test_w01_source_export_failures
    raise SourceLibrarySingleSourceGuardError(failure.message, details=details)


def build_single_source_guard_error_details(
    *,
    reason_code: str,
    guard: object,
    expected: object,
    actual: object,
) -> Annotated[
    GuardObject,
    "kit:non-authoritative derived_as=view fact_source=source_library.single_source_guard witness=test:test_w01_meta",
]:
    return {
        "reason_code": reason_code,
        "field": "override_params.single_source_guard",
        "single_source_guard": deepcopy(guard) if _is_guard_object(guard) else guard,
        "expected": expected,
        "actual": actual,
    }


def build_single_source_execution_fact(
    guard: Mapping[str, object],
    *,
    item_key: str | None = None,
    project_key: str | None = None,
    reason_code: str = "single_source_guard_passed",
) -> Annotated[
    GuardObject,
    "kit:non-authoritative derived_as=view fact_source=source_library.single_source_guard witness=test:test_w01_meta",
]:
    source_ref_value = guard.get("source_ref")
    source_ref = dict(source_ref_value) if _is_guard_object(source_ref_value) else {}
    report_source_ref = str(guard.get("report_source_ref") or "").strip()
    allowed_urls_value = guard.get("allowed_urls")
    allowed_url = (
        allowed_urls_value[0]
        if _is_object_list(allowed_urls_value) and allowed_urls_value
        else None
    )
    return {
        "contract_version": "source_library.execution_fact.v1",
        "reason_code": reason_code,
        "item_key": item_key,
        "project_key": project_key,
        "guard_status": "passed" if guard.get("guarantee") is True else "blocked",
        "guard_reason_code": guard.get("reason_code") or guard.get("blocked_reason"),
        "source_refs": [
            {
                "kind": "resource_pool.site_entry",
                "report_source_ref": report_source_ref,
                "site_entry_url": allowed_url,
                "source_ref": source_ref,
            }
        ],
        "source_ref": source_ref,
        "report_source_ref": report_source_ref,
        "single_source_guard": deepcopy(dict(guard)),
    }


def _raise_guard_error(
    message: str,
    *,
    reason_code: str,
    guard: object,
    expected: object,
    actual: object,
) -> NoReturn:
    details = build_single_source_guard_error_details(
        reason_code=reason_code,
        guard=guard,
        expected=expected,
        actual=actual,
    )
    _raise_guard_failure(
        _guard_failure(reason_code, message, details=details),
        details=details,
    )


def validate_single_source_guard(
    override_params: object,
) -> GuardObject | None:
    if not _is_guard_object(override_params) or "single_source_guard" not in override_params:
        return None

    guard = override_params.get("single_source_guard")
    site_entries = override_params.get("site_entries")
    if not _is_guard_object(guard):
        _raise_guard_error(
            "override_params.single_source_guard must be an object.",
            reason_code="single_source_guard_invalid_shape",
            guard=guard,
            expected={"single_source_guard": "object"},
            actual={"single_source_guard": type(guard).__name__},
        )

    allowed_urls = guard.get("allowed_urls")
    allowed_count = guard.get("allowed_count")
    strict_source = guard.get("strict_source")
    guarantee = guard.get("guarantee")
    blocked_reason = guard.get("blocked_reason")

    if strict_source is not True:
        _raise_guard_error(
            "override_params.single_source_guard.strict_source must be true.",
            reason_code="single_source_guard_strict_source_required",
            guard=guard,
            expected={"strict_source": True},
            actual={"strict_source": strict_source},
        )
    if guarantee is not True or blocked_reason:
        _raise_guard_error(
            "override_params.single_source_guard is blocked and cannot dispatch.",
            reason_code="single_source_guard_blocked",
            guard=guard,
            expected={"guarantee": True, "blocked_reason": None},
            actual={"guarantee": guarantee, "blocked_reason": blocked_reason},
        )
    if not _is_object_list(allowed_urls) or allowed_count != 1 or len(allowed_urls) != 1:
        _raise_guard_error(
            "override_params.single_source_guard.allowed_urls must contain exactly one URL.",
            reason_code="single_source_guard_allowed_urls_invalid",
            guard=guard,
            expected={"allowed_count": 1, "allowed_urls_length": 1},
            actual={
                "allowed_count": allowed_count,
                "allowed_urls": allowed_urls,
                "allowed_urls_length": len(allowed_urls) if _is_object_list(allowed_urls) else None,
            },
        )
    if not _is_object_list(site_entries) or site_entries != allowed_urls:
        _raise_guard_error(
            "override_params.site_entries must exactly match single_source_guard.allowed_urls.",
            reason_code="single_source_guard_site_entries_mismatch",
            guard=guard,
            expected={"site_entries": allowed_urls, "allowed_urls": allowed_urls},
            actual={"site_entries": site_entries, "allowed_urls": allowed_urls},
        )
    return deepcopy(guard)


__all__ = [
    "SourceLibrarySingleSourceGuardError",
    "build_single_source_guard_error_details",
    "build_single_source_execution_fact",
    "validate_single_source_guard",
]
