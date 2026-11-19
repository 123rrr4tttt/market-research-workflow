from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from collections.abc import Mapping
from typing import Callable, NoReturn

from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import source_library_contract_failures

from ..item_resolver import ExecutionPayload, ExecutionRequest, channel_default_params, item_mapping_fields, terminal_output_params
from ..types import SourceChannelExecutor

_FAILURE_WITNESS = "test:test_source_configuration_and_report_export_failures"


def _orchestrator_failure(code: str, message: str, *, site: str) -> Failure:
    return source_library_contract_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": source_library_contract_failures.name,
            "operation": "source_library.single_channel_orchestrator",
            "owner": "source_library.single_channel_orchestrator",
            "public_exception": "ValueError",
            "public_message": message,
            "site": site,
            "witness": _FAILURE_WITNESS,
        },
    )


def _raise_orchestrator_failure(failure: Failure) -> NoReturn:
    context = failure.context or {}
    required = {"boundary_class", "failure_family", "operation", "owner", "public_exception", "public_message", "site", "witness"}
    if (
        not source_library_contract_failures.matches(failure)
        or required - set(context)
        or context.get("failure_family") != source_library_contract_failures.name
        or context.get("boundary_class") != "PURE_CONTRACT_FAILURE"
        or context.get("public_exception") != "ValueError"
        or context.get("public_message") != failure.message
    ):
        # kit:boundary owner=source_library.single_channel_orchestrator.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_source_configuration_and_report_export_failures
        raise TypeError("single-channel failure lift context is incomplete or inconsistent")
    # kit:boundary owner=source_library.single_channel_orchestrator.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=source_library.contract_failure witness=test:test_source_configuration_and_report_export_failures
    raise ValueError(str(context["public_message"]))


def run_single_channel_orchestrator(
    *,
    item: dict[str, object],
    request: ExecutionRequest,
    channel_map: dict[str, dict[str, object]],
    deep_merge: Callable[[Mapping[object, object], Mapping[object, object]], dict[object, object]],
    bind_project: Callable[[str], AbstractContextManager[object]],
    run_channel: SourceChannelExecutor,
) -> ExecutionPayload:
    channel_key = str(item.get("channel_key") or "").strip()
    channel = channel_map.get(channel_key)
    if channel is None:
        _raise_orchestrator_failure(
            _orchestrator_failure(
                "channel_not_found",
                f"channel not found for item {request.item_key}: {channel_key}",
                site="run_single_channel_orchestrator.channel",
            )
        )
    if not channel.get("enabled", True):
        _raise_orchestrator_failure(
            _orchestrator_failure(
                "channel_disabled",
                f"channel disabled for item {request.item_key}: {channel_key}",
                site="run_single_channel_orchestrator.channel_enabled",
            )
        )

    params = deep_merge(channel_default_params(channel.get("default_params") or {}), request.params)
    params = terminal_output_params(params)
    params["_source_library_item"] = {
        "item_key": request.item_key,
        "channel_key": channel_key,
        "name": item.get("name"),
        "extra": item_mapping_fields(item.get("extra")),
    }
    if channel_key == "handler.cluster":
        params.setdefault("_item_key", request.item_key)

    with (bind_project(request.project_key) if request.project_key else nullcontext()):
        result = run_channel(
            channel=channel,
            params=params,
            project_key=request.project_key,
            item_key=request.item_key,
        )
    return request.complete(result, channel_key=channel_key, params=params)
