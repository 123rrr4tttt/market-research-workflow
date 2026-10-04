"""Sibling legacy adapter for the C4 agent-batch plan/retry atoms.

This is the only file allowed to call the legacy pure agent-batch helpers
``_augment_tasks_with_source_library``, ``_expand_tasks_with_limited_branching``,
``validate_retry_action_payload`` and ``_apply_retry_action``.  It deliberately
never calls the loop's submitter, ``_discover_source_library_item_keys`` or any
other effectful discovery path: source candidates are supplied explicitly so
the replay stays deterministic and read-only.

The adapter projects legacy dict observations into the frozen successor DTO
vocabulary and exposes distinct legacy/successor interpreter bindings.  No code
in this module claims both bindings for one logical run, and the C4 successor
surface never rewrites or selects ``source_mode``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from app.services.agent_batch.agent_loop import (
    _apply_retry_action as _legacy_apply_retry_action,
)
from app.services.agent_batch.agent_loop import (
    _build_search_brief as _legacy_build_search_brief,
)
from app.services.agent_batch.agent_loop import (
    _expand_tasks_with_limited_branching as _legacy_expand_tasks_with_limited_branching,
)
from app.services.agent_batch.task_contract import (
    normalize_agent_batch_task as _legacy_normalize_agent_batch_task,
)
from app.services.agent_batch.task_contract import (
    validate_retry_action_payload as _legacy_validate_retry_action_payload,
)
from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.agent_batch_c4_interpreters import (
    AGENT_BATCH_C4_LEGACY_PLAN_INTERPRETER_ID,
    AGENT_BATCH_C4_LEGACY_RETRY_INTERPRETER_ID,
    InterpreterFailure,
    InterpreterSuccess,
    authority_requirement_digest,
    legacy_plan_interpreter_profile_digest,
    legacy_retry_interpreter_profile_digest,
    require_exact_batch_plan_binding,
    require_exact_retry_binding,
    successor_plan_interpreter_profile_digest,
    successor_retry_interpreter_profile_digest,
    successor_submission_interpreter_profile_digest,
)
from app.successor_runtime.runtime.assignments import InterpreterBinding

__all__ = [
    "LegacyAgentBatchPlanAdapter",
    "LegacyAgentBatchRetryAdapter",
    "build_legacy_agent_batch_c4_plan_binding",
    "build_legacy_agent_batch_c4_retry_binding",
    "build_successor_agent_batch_c4_plan_binding",
    "build_successor_agent_batch_c4_retry_binding",
    "build_successor_agent_batch_c4_submission_binding",
]


def _task_to_plain(task: c4.AgentBatchTask) -> dict[str, Any]:
    plain = dataclasses.asdict(task)
    for name in ("query_terms", "urls", "platforms"):
        value = plain.get(name)
        if isinstance(value, tuple):
            plain[name] = list(value)
    return plain


def _plain_tasks(tasks: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task in tasks or ():
        if isinstance(task, c4.AgentBatchTask):
            out.append(_task_to_plain(task))
        elif isinstance(task, dict):
            out.append(dict(task))
    return out


def _to_typed_tasks(
    plain_tasks: list[dict[str, Any]],
    *,
    default_language: str,
) -> tuple[c4.AgentBatchTask, ...]:
    return c4.normalize_batch_tasks(plain_tasks, default_language=default_language)


class LegacyAgentBatchPlanAdapter:
    """Deterministic legacy replay of the C4.1 ordered plan slice."""

    interpreter_id = AGENT_BATCH_C4_LEGACY_PLAN_INTERPRETER_ID

    def __init__(self) -> None:
        self.plan_calls = 0

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: c4.BatchPlanPayload,
        project_scope: Any,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> Any:
        """Same-Program/Plan legacy interpreter for the C4.1 batch-plan atom.

        The exact shared Program/Plan/payload closure is revalidated with the
        distinct legacy interpreter profile before the legacy pure slice runs.
        """

        try:
            require_exact_batch_plan_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    legacy_plan_interpreter_profile_digest()
                ),
            )
        except Exception as exc:  # noqa: BLE001 - exact binding fail-closed
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        try:
            result = self.build_plan(
                payload,
                candidate_item_keys=tuple(
                    item.item_key for item in payload.candidates.source_items
                ),
            )
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="INVALID_PLAN",
                message=str(exc),
                retryable=False,
            )
        return InterpreterSuccess(result)

    def build_plan(
        self,
        payload: c4.BatchPlanPayload,
        *,
        candidate_item_keys: tuple[str, ...] | list[str],
    ) -> c4.BatchPlanResult:
        """Run the legacy pure plan helpers with explicitly supplied candidates."""

        default_language = payload.language or "zh"
        plain = [
            _legacy_normalize_agent_batch_task(
                _task_to_plain(task),
                idx=idx,
                default_language=default_language,
            )
            for idx, task in enumerate(payload.tasks, start=1)
        ]
        source_keys = [str(key) for key in candidate_item_keys if str(key).strip()][
            : max(0, payload.max_source_tasks)
        ]
        already_planned = any(
            str(task.get("channel") or "").strip().lower() == "source_library"
            for task in plain
        )
        can_supplement = (
            source_keys
            and payload.retrieval_mode != c4.RETRIEVAL_MODE_WEB_ONLY
            and not (
                already_planned
                and payload.retrieval_mode != c4.RETRIEVAL_MODE_SOURCE_ONLY
            )
            and (bool(plain) or payload.retrieval_mode == c4.RETRIEVAL_MODE_SOURCE_ONLY)
        )
        if can_supplement:
            # The legacy helper performs ambient discovery; the adapter replaces
            # that effectful slice with the exact supplied C2 snapshot keys and
            # mirrors the legacy merge/append ordering.
            limits = [
                int(task.get("max_items") or 0)
                for task in plain
                if str(task.get("channel") or "").strip().lower()
                in {"search.market", "source_library"}
            ]
            source_collect_limit = max(1, min(100, max(limits or [20])))
            query_terms: list[str] = []
            for task in plain:
                if str(task.get("channel") or "").strip().lower() != "search.market":
                    continue
                for term in list(task.get("query_terms") or []):
                    text = str(term or "").strip()
                    if text and text not in query_terms:
                        query_terms.append(text)
            appended = [
                {
                    "task_id": f"source_{idx}",
                    "channel": "source_library",
                    "query_terms": list(query_terms),
                    "max_items": source_collect_limit,
                    "provider": "auto",
                    "language": "zh",
                    "days_back": None,
                    "item_key": item_key,
                    "override_params": {
                        "autonomous_strategy": "mode_driven_source_library",
                        "autonomous_reason": "fixed_source_mode",
                    },
                }
                for idx, item_key in enumerate(source_keys, start=1)
            ]
            if payload.retrieval_mode == c4.RETRIEVAL_MODE_SOURCE_ONLY:
                preserved = [
                    task
                    for task in plain
                    if str(task.get("channel") or "").strip().lower()
                    == "source_library"
                ]
                tasks = preserved + appended
            else:
                tasks = plain + appended
            autonomy_meta = {
                "enabled": True,
                "item_keys": list(source_keys),
                "selection_mode": "goal_relevance",
            }
        else:
            tasks = plain
            autonomy_meta = {
                "enabled": False,
                "reason": (
                    "web_only_mode"
                    if payload.retrieval_mode == c4.RETRIEVAL_MODE_WEB_ONLY
                    else "source_library_already_planned"
                    if already_planned
                    and payload.retrieval_mode != c4.RETRIEVAL_MODE_SOURCE_ONLY
                    else "no_source_library_match"
                ),
            }
        self.plan_calls += 1
        supplementation = c4.SupplementationDecision(
            enabled=bool(autonomy_meta.get("enabled")),
            item_keys=tuple(
                str(key)
                for key in (autonomy_meta.get("item_keys") or candidate_item_keys)
                if str(key).strip()
            )[: payload.max_source_tasks],
            selection_mode=str(autonomy_meta.get("selection_mode") or None) or None,
            reason=None
            if autonomy_meta.get("enabled")
            else str(autonomy_meta.get("reason") or ""),
        )
        brief = _legacy_build_search_brief(
            command=payload.command,
            intent=payload.command,
            tasks=tasks,
            retrieval_mode=payload.retrieval_mode,
            autonomy_meta=autonomy_meta,
        )
        expanded, branching = _legacy_expand_tasks_with_limited_branching(
            tasks=tasks,
            search_brief=brief,
            retrieval_mode=payload.retrieval_mode,
            enable_limited_branching=payload.limited_branching_enabled,
            command=payload.command,
        )
        final_tasks = _to_typed_tasks(expanded, default_language=default_language)
        search_brief = c4.build_search_brief(
            command=payload.command,
            intent=payload.command,
            tasks=final_tasks,
            retrieval_mode=payload.retrieval_mode,
            candidate_keys=supplementation.item_keys,
            supplementation_enabled=supplementation.enabled,
        )
        return c4.BatchPlanResult(
            schema_version="mrw.successor.agent-batch.c4-1.result.v1",
            tasks=final_tasks,
            supplementation=supplementation,
            branching=c4.BranchingDecision(
                enabled=bool(branching.get("enabled")),
                branch_count=int(branching.get("branch_count") or 1),
                reason=str(branching.get("reason") or "disabled"),
                strategy_labels=tuple(
                    str(label) for label in branching.get("strategy_labels") or ()
                ),
            ),
            search_brief=search_brief,
        )


class LegacyAgentBatchRetryAdapter:
    """Legacy retry rewrite replay without the submit effect."""

    interpreter_id = AGENT_BATCH_C4_LEGACY_RETRY_INTERPRETER_ID

    def __init__(self) -> None:
        self.reduce_calls = 0
        self.source_mode_rewrites_seen = 0

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: Any,
        payload_ref: Any,
        payload: c4.RetryReducerInput,
        project_scope: Any,
        catalog: Any,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> Any:
        """Same-Program/Plan legacy interpreter for the C4.2 retry reducer."""

        try:
            require_exact_retry_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    legacy_retry_interpreter_profile_digest()
                ),
            )
        except Exception as exc:  # noqa: BLE001 - exact binding fail-closed
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        try:
            transition = self.reduce(payload)
        except (TypeError, ValueError) as exc:
            return InterpreterFailure(
                code="RETRY_ACTION_INVALID",
                message=str(exc),
                retryable=False,
            )
        return InterpreterSuccess(transition)

    def reduce(
        self,
        payload: c4.RetryReducerInput,
    ) -> c4.RetryTransition:
        """Validate and rewrite through the legacy pure helpers.

        The submitter is never invoked.  ``source_mode`` rewrites are counted
        but never projected into the C4 successor output.
        """

        default_language = payload.command and c4._detect_language(payload.command)
        default_language = default_language or "zh"
        plain = [
            _legacy_normalize_agent_batch_task(
                _task_to_plain(task),
                idx=idx,
                default_language=default_language,
            )
            for idx, task in enumerate(payload.tasks, start=1)
        ]
        if "source_mode" in (payload.retry_action.rewrite or {}):
            self.source_mode_rewrites_seen += 1
        legacy_action: dict[str, Any] = {
            "action": payload.retry_action.action,
            "reason": payload.retry_action.reason,
            "channel": payload.retry_action.channel,
            "rewrite": dict(payload.retry_action.rewrite),
            "target_items": list(payload.retry_action.target_items),
        }
        normalized, reason_code, details = _legacy_validate_retry_action_payload(
            legacy_action,
            default_channel=str(payload.retry_action.channel or ""),
        )
        if normalized is None:
            self.reduce_calls += 1
            return c4.RetryTransition(
                kind="RETRY_REJECTED",
                tasks=payload.tasks,
                observations={
                    "validation_failure": reason_code or "retry_action_invalid",
                    "validation_details": dict(details),
                },
            )
        normalized["rewrite"].pop("source_mode", None)
        retried = _legacy_apply_retry_action(
            tasks=plain,
            retry_action=normalized,
            command=payload.command,
        )
        self.reduce_calls += 1
        typed = _to_typed_tasks(retried, default_language=default_language)
        if typed == payload.tasks:
            return c4.RetryTransition(
                kind="RETRY_SKIPPED",
                tasks=typed,
                observations={"skip_reason": "retry_action_no_effect"},
            )
        round_index = payload.budget.used + 1
        intent = c4.RetryAttemptIntent(
            attempt_id=f"attempt:{payload.project_key}:{payload.prior_attempt_ref}:retry:{round_index}",
            round_index=round_index,
            prior_attempt_ref=payload.prior_attempt_ref,
            idempotency_key=c4._build_retry_idempotency_key(
                prior_attempt_ref=payload.prior_attempt_ref,
                round_index=round_index,
            ),
        )
        return c4.RetryTransition(
            kind="RETRY_SCHEDULED",
            tasks=typed,
            observations={
                "scheduled": True,
                "used": payload.budget.used + 1,
                "budget_remaining": payload.budget.remaining - 1,
                "round": round_index,
                "reason": normalized.get("reason") or payload.retry_action.reason,
                "task_count": len(typed),
            },
            attempt_intent=intent,
        )


def build_legacy_agent_batch_c4_plan_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=legacy_plan_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_agent_batch_c4_plan_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_plan_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_legacy_agent_batch_c4_retry_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=legacy_retry_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_agent_batch_c4_retry_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_retry_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_agent_batch_c4_submission_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> InterpreterBinding:
    return InterpreterBinding.from_content(
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_submission_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )
