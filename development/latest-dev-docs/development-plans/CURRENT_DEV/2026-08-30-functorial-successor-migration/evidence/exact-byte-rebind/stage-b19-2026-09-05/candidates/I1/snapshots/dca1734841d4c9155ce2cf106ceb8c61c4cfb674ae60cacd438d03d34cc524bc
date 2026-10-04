"""Sibling legacy adapter for the four C2.2 source-mode orchestrators.

This is the only file allowed to call the four orchestrator wrappers in
``app.services.source_library.orchestrators``.  Every effect callback is
replaced with a deterministic fixture/receipt callback, so the replay
executes zero real provider, credential, network, filesystem or database
effects.  The adapter records every fixture call for shadow/parity evidence.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

from app.services.source_library.item_resolver import (
    ExecutionRequest,
    execution_request_to_dict,
)
from app.services.source_library.orchestrators.protocol_search import (
    run_protocol_search_orchestrator,
)
from app.services.source_library.orchestrators.provider_harvest import (
    run_provider_harvest_orchestrator,
)
from app.services.source_library.orchestrators.single_channel import (
    run_single_channel_orchestrator,
)
from app.services.source_library.orchestrators.site_search import (
    run_site_search_orchestrator,
)
from app.services.source_library.orchestrators.url_execution import (
    run_url_execution_orchestrator,
)
from app.services.source_library.resolver import (
    _deep_merge,
    _protocol_to_dict,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    SourceExecutionRequest,
)

__all__ = [
    "LegacyFourModeTrace",
    "LegacySourceLibraryC2_2Adapter",
    "canonical_request_to_legacy_request",
]


LEGACY_C2_2_INTERPRETER_ID = "legacy.source_library.c2_2.four_modes.v1"
_RECEIPT_SCHEMA = "source_library.provider_handoff.v1"


def canonical_request_to_legacy_request(
    request: SourceExecutionRequest,
) -> ExecutionRequest:
    """Project the successor request into the legacy execution shape."""

    protocol = request.protocol
    from app.services.source_library.types import (
        FrontDoorExecutionProtocol as LegacyProtocol,
    )

    search_stage = protocol.concurrency_plan.search
    url_stage = protocol.concurrency_plan.url
    concurrency = {
        "batch_size": protocol.concurrency_plan.batch_size,
        "shared_budget": protocol.concurrency_plan.shared_budget,
        "search": {
            "stage": search_stage.stage,
            "tasks_total": search_stage.tasks_total,
            "requested_parallelism": search_stage.requested_parallelism,
            "parallelism": search_stage.parallelism,
            "budget": search_stage.budget,
            "fail_fast": search_stage.fail_fast,
            "timeout_seconds": search_stage.timeout_seconds,
        },
        "url": {
            "stage": url_stage.stage,
            "tasks_total": url_stage.tasks_total,
            "requested_parallelism": url_stage.requested_parallelism,
            "parallelism": url_stage.parallelism,
            "budget": url_stage.budget,
            "fail_fast": url_stage.fail_fast,
            "timeout_seconds": url_stage.timeout_seconds,
        },
    }
    legacy_protocol = LegacyProtocol(
        item_key=protocol.item_key,
        item_channel_key=protocol.item_channel_key,
        project_key=protocol.project_key,
        front_door_owner=protocol.front_door_owner,
        execution_mode=protocol.execution_mode,
        write_mode=protocol.write_mode,
        route_decision=protocol.route_decision,
        query_terms=list(protocol.query_terms),
        site_entries=list(protocol.site_entries),
        candidate_urls=list(protocol.candidate_urls),
        expected_entry_type=protocol.expected_entry_type,
        write_to_pool=protocol.write_to_pool,
        auto_ingest=protocol.auto_ingest,
        ingest_limit=protocol.ingest_limit,
        force_url_routing_flow=protocol.force_url_routing_flow,
        prefer_crawler_first=protocol.prefer_crawler_first,
        search_parallelism=protocol.search_parallelism,
        routing_parallelism=protocol.routing_parallelism,
        concurrency_plan=concurrency,
        source_tier=protocol.source_tier,
        onboarding_priority=protocol.onboarding_priority,
    )
    return ExecutionRequest(
        source_mode=request.source_mode.mode,
        item_key=request.item_key,
        item_channel_key=request.item_channel_key,
        project_key=request.project_key,
        params=request.params.to_dict(),
        protocol=legacy_protocol,
        warnings=[warning.code for warning in request.warnings],
        taxonomy=request.taxonomy.to_plain(),
    )


@dataclass(frozen=True, slots=True)
class LegacyFourModeTrace:
    trace_id: str
    mode: str
    payload: dict[str, Any]
    provider_calls: tuple[str, ...]
    receipt: dict[str, Any]
    trace_digest: str = ""

    def __post_init__(self) -> None:
        if self.trace_digest == "":
            object.__setattr__(
                self,
                "trace_digest",
                content_digest(
                    {
                        "schema": "mrw.successor.source-library.c2-2.legacy-trace.v1",
                        "trace_id": self.trace_id,
                        "mode": self.mode,
                        "payload": self.payload,
                        "provider_calls": list(self.provider_calls),
                        "receipt": self.receipt,
                    }
                ),
            )


class LegacySourceLibraryC2_2Adapter:
    """Deterministic fixture replay of the four legacy orchestrators."""

    interpreter_id = LEGACY_C2_2_INTERPRETER_ID

    def __init__(self) -> None:
        self.provider_calls: list[str] = []
        self.traces: list[LegacyFourModeTrace] = []

    def _fixture_run_channel(
        self,
        *,
        channel: dict[str, Any],
        params: dict[str, Any],
        project_key: str | None,
        item_key: str | None,
    ) -> dict[str, Any]:
        channel_key = str(channel.get("channel_key") or "").strip()
        self.provider_calls.append(channel_key or "unknown")
        return {
            "records": [],
            "candidates": [],
            "errors": [],
            "retryable": False,
            "provider": str(
                channel.get("provider") or channel.get("provider_type") or "fixture"
            ),
            "provider_job_id": None,
            "provider_status": "FIXTURE_RECEIPT",
            "handoff": {
                "contract_version": _RECEIPT_SCHEMA,
                "provider": str(channel.get("provider") or "fixture"),
                "provider_job_id": None,
                "provider_status": "FIXTURE_RECEIPT",
                "receipt_digest": content_digest(
                    {"channel_key": channel_key, "item_key": item_key}
                ),
            },
        }

    def _fixture_handler_cluster(
        self,
        *,
        item: dict[str, Any],
        params: dict[str, Any],
        project_key: str | None,
        channel_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        site_entries = params.get("site_entries") or params.get("site_entry_urls") or []
        return {
            "result": {
                "records": [],
                "candidates": list(site_entries),
                "by_url": [],
                "errors": [],
                "retryable": False,
                "routing_result": {
                    "channel_key": "handler.cluster",
                    "forced": True,
                },
            }
        }

    def _fixture_url_routing(
        self,
        *,
        item: dict[str, Any],
        params: dict[str, Any],
        project_key: str | None,
        channel_map: dict[str, dict[str, Any]],
        execution_layer: str,
    ) -> dict[str, Any]:
        urls = params.get("urls") or params.get("candidate_urls") or []
        by_url = [
            {
                "url": str(url),
                "channel_key": None,
                "status": "fixture_receipt",
                "error": None,
            }
            for url in urls
        ]
        return {
            "records": [],
            "candidates": list(urls),
            "by_url": by_url,
            "errors": [],
            "retryable": False,
            "execution_layer": execution_layer,
        }

    def replay(
        self,
        *,
        request: SourceExecutionRequest,
        item: dict[str, Any],
        channel_map: dict[str, dict[str, Any]],
        trace_id: str = "legacy.c2_2.four_modes",
    ) -> tuple[dict[str, LegacyFourModeTrace], list[str]]:
        """Replay all four orchestrators with fixture callbacks only."""

        legacy_request = canonical_request_to_legacy_request(request)
        traces: dict[str, LegacyFourModeTrace] = {}
        run_single = run_single_channel_orchestrator

        traces["protocol_search"] = self._replay_protocol_search(
            item=item,
            request=legacy_request,
            channel_map=channel_map,
            run_single=run_single,
            trace_id=f"{trace_id}:protocol_search",
        )
        traces["provider_harvest"] = self._replay_provider_harvest(
            item=item,
            request=legacy_request,
            channel_map=channel_map,
            run_single=run_single,
            trace_id=f"{trace_id}:provider_harvest",
        )
        traces["site_search"] = self._replay_site_search(
            item=item,
            request=legacy_request,
            channel_map=channel_map,
            trace_id=f"{trace_id}:site_search",
        )
        traces["url_execution"] = self._replay_url_execution(
            item=item,
            request=legacy_request,
            channel_map=channel_map,
            trace_id=f"{trace_id}:url_execution",
        )
        return traces, list(self.provider_calls)

    def _replay_protocol_search(
        self,
        *,
        item: dict[str, Any],
        request: ExecutionRequest,
        channel_map: dict[str, dict[str, Any]],
        run_single: Any,
        trace_id: str,
    ) -> LegacyFourModeTrace:
        payload = run_protocol_search_orchestrator(
            item=item,
            request=request,
            channel_map=channel_map,
            run_single_channel_orchestrator=run_single,
            deep_merge=_deep_merge,
            bind_project=lambda _: nullcontext(),
            run_channel=self._fixture_run_channel,
            execution_request_to_dict=execution_request_to_dict,
        )
        receipt = dict(payload.get("result") or {}).get("handoff") or {}
        trace = LegacyFourModeTrace(
            trace_id=trace_id,
            mode="protocol_search",
            payload=payload,
            provider_calls=tuple(self.provider_calls),
            receipt=receipt,
        )
        self.traces.append(trace)
        return trace

    def _replay_provider_harvest(
        self,
        *,
        item: dict[str, Any],
        request: ExecutionRequest,
        channel_map: dict[str, dict[str, Any]],
        run_single: Any,
        trace_id: str,
    ) -> LegacyFourModeTrace:
        payload = run_provider_harvest_orchestrator(
            item=item,
            request=request,
            channel_map=channel_map,
            run_single_channel_orchestrator=run_single,
            deep_merge=_deep_merge,
            bind_project=lambda _: nullcontext(),
            run_channel=self._fixture_run_channel,
            execution_request_to_dict=execution_request_to_dict,
        )
        receipt = dict(payload.get("result") or {}).get("handoff") or {}
        trace = LegacyFourModeTrace(
            trace_id=trace_id,
            mode="provider_harvest",
            payload=payload,
            provider_calls=tuple(self.provider_calls),
            receipt=receipt,
        )
        self.traces.append(trace)
        return trace

    def _replay_site_search(
        self,
        *,
        item: dict[str, Any],
        request: ExecutionRequest,
        channel_map: dict[str, dict[str, Any]],
        trace_id: str,
    ) -> LegacyFourModeTrace:
        payload = run_site_search_orchestrator(
            item=item,
            request=request,
            channel_map=channel_map,
            run_handler_cluster_item=self._fixture_handler_cluster,
            execution_request_to_dict=execution_request_to_dict,
        )
        receipt = dict(payload.get("result") or {}).get("routing_result") or {}
        trace = LegacyFourModeTrace(
            trace_id=trace_id,
            mode="site_search",
            payload=payload,
            provider_calls=tuple(self.provider_calls),
            receipt=receipt,
        )
        self.traces.append(trace)
        return trace

    def _replay_url_execution(
        self,
        *,
        item: dict[str, Any],
        request: ExecutionRequest,
        channel_map: dict[str, dict[str, Any]],
        trace_id: str,
    ) -> LegacyFourModeTrace:
        payload = run_url_execution_orchestrator(
            item=item,
            request=request,
            channel_map=channel_map,
            run_item_with_url_routing=self._fixture_url_routing,
            protocol_to_dict=_protocol_to_dict,
            execution_request_to_dict=execution_request_to_dict,
        )
        result = payload.get("result") or {}
        receipt = {"by_url": result.get("by_url") or []}
        trace = LegacyFourModeTrace(
            trace_id=trace_id,
            mode="url_execution",
            payload=payload,
            provider_calls=tuple(self.provider_calls),
            receipt=receipt,
        )
        self.traces.append(trace)
        return trace
