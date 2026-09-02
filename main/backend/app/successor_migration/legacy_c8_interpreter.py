"""Legacy interpreter dispatch over the shared C8 Program/Plan.

P4 ahead-of-time family-local scaffold: before dispatch the interpreter
validates the exact shared Program/Plan pair, project scope, canonical
identity and handler closure; each ``ExecutionPlan`` step is then dispatched
by its exact operation contract digest to real legacy donor adapters with
true step-to-step dataflow (typed output becomes the next step's input).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
    parse_writing_knowledge_handoff_payload,
    serialize_writing_knowledge_handoff,
)
from app.successor_migration.legacy_c8_graph import LegacyC8GraphAdapter
from app.successor_migration.legacy_c8_report import LegacyC8ReportAdapter
from app.successor_migration.legacy_c8_typed_knowledge import (
    LegacyC8TypedKnowledgeAdapter,
)
from app.successor_migration.legacy_c8_writing import LegacyC8WritingAdapter
from app.successor_runtime.capabilities.c8_program import payload_body_digest
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.language.program import ProgramSpec

__all__ = [
    "LEGACY_C8_PROGRAM_INTERPRETER_ID",
    "LegacyC8DemandReadDonor",
    "LegacyC8DonorRegistry",
    "LegacyC8GraphDonor",
    "LegacyC8ProgramInterpreter",
    "LegacyC8ReportDonor",
    "LegacyC8StepExecution",
    "LegacyC8WritingComposeDonor",
    "LegacyC8WritingStageDonor",
]

LEGACY_C8_PROGRAM_INTERPRETER_ID = "legacy.c8.shared_program_trace.v1"


@dataclass(frozen=True, slots=True)
class LegacyC8StepExecution:
    step_id: str
    operation_id: str
    operation_digest: str
    order: int
    input_digest: str
    output: dict[str, Any] | None
    failure: dict[str, Any] | None


class LegacyC8DonorRegistry:
    """Exact operation-digest dispatch table for legacy donor adapters."""

    def __init__(self) -> None:
        self._donors: dict[str, Callable[[Any], dict[str, Any]]] = {}

    def register(
        self,
        operation_digest: str,
        donor: Callable[[Any], dict[str, Any]],
    ) -> None:
        self._donors[operation_digest] = donor

    def resolve(self, operation_digest: str) -> Callable[[Any], dict[str, Any]] | None:
        return self._donors.get(operation_digest)


class LegacyC8DemandReadDonor:
    def __init__(
        self,
        *,
        items_by_key: Mapping[str, Any],
        selection_hash: str,
        selection_text: str,
    ) -> None:
        self._items = items_by_key
        self._selection_hash = selection_hash
        self._selection_text = selection_text
        self._adapter = LegacyC8TypedKnowledgeAdapter()

    def run(self, payload: Any) -> dict[str, Any]:
        item = self._items[payload.item_key]
        return self._adapter.build_handoff_payload(
            item,
            selection_hash=self._selection_hash,
            selection_text=self._selection_text,
        )


class LegacyC8WritingComposeDonor:
    def __init__(
        self,
        *,
        items_by_key: Mapping[str, Any],
        selection_hash: str,
        selection_text: str,
    ) -> None:
        self._items = items_by_key
        self._selection_hash = selection_hash
        self._selection_text = selection_text

    def run(self, payload: Any) -> dict[str, Any]:
        item = self._items[payload.knowledge_item_key]
        contract = build_downstream_contract_draft(item)
        handoff = build_writing_knowledge_handoff(
            contract,
            selection_hash=self._selection_hash,
            selection_text=self._selection_text,
        )
        return serialize_writing_knowledge_handoff(handoff)


class LegacyC8WritingStageDonor:
    def __init__(
        self,
        *,
        normalized_query: str,
    ) -> None:
        self._normalized_query = normalized_query
        self._adapter = LegacyC8WritingAdapter()

    def run(self, payload: Any) -> dict[str, Any]:
        handoff = parse_writing_knowledge_handoff_payload(payload)
        return self._adapter.build_card_observation(
            handoff,
            normalized_query=self._normalized_query,
        )


class LegacyC8ReportDonor:
    def __init__(self) -> None:
        self._adapter = LegacyC8ReportAdapter()

    def run(self, payload: Any) -> dict[str, Any]:
        return self._adapter.observe_staging(
            _ReportStub(payload.report_id, payload.payload_digest)
        )


@dataclass(frozen=True, slots=True)
class _ReportStub:
    report_id: str
    artifact_digest: str


class LegacyC8GraphDonor:
    def __init__(self, *, nodes: Mapping[str, Any]) -> None:
        self._nodes = nodes
        self._adapter = LegacyC8GraphAdapter()

    def run(self, payload: Any) -> dict[str, Any]:
        return self._adapter.project(
            self._nodes,
            [],
            payload.node_types,
        )


class LegacyC8ProgramInterpreter:
    """Read-only executor of legacy donors over the shared Program/Plan."""

    interpreter_id = LEGACY_C8_PROGRAM_INTERPRETER_ID

    def __init__(self) -> None:
        self.consumed_calls = 0

    def consume(
        self,
        program: ProgramSpec,
        plan: Any,
        *,
        donors: LegacyC8DonorRegistry,
        seed_inputs: Mapping[str, tuple[Any, str | None]],
    ) -> dict[str, object]:
        self.consumed_calls += 1
        self._validate_pair(program, plan, donors=donors, seed_inputs=seed_inputs)
        executions: list[LegacyC8StepExecution] = []
        last_output: dict[str, Any] | None = None
        last_output_digest = ""
        for order, step in enumerate(plan.ordered_steps, start=1):
            ref = step.operation_contract_ref
            if ref is None:
                executions.append(
                    LegacyC8StepExecution(
                        step_id=step.step_id,
                        operation_id=step.operation_id,
                        operation_digest="",
                        order=order,
                        input_digest="",
                        output=None,
                        failure={"failure_kind": "MISSING_OPERATION_REF"},
                    )
                )
                continue
            donor = donors.resolve(ref.contract_digest)
            if step.step_id in seed_inputs:
                payload, input_digest = seed_inputs[step.step_id]
            else:
                payload = last_output
                input_digest = last_output_digest
            if payload is None:
                executions.append(
                    LegacyC8StepExecution(
                        step_id=step.step_id,
                        operation_id=step.operation_id,
                        operation_digest=ref.contract_digest,
                        order=order,
                        input_digest=input_digest,
                        output=None,
                        failure={"failure_kind": "MISSING_PREVIOUS_STEP_OUTPUT"},
                    )
                )
                continue
            try:
                output = donor(payload)
                failure = None
            except Exception as exc:  # noqa: BLE001 - typed failure record
                output = None
                failure = {"failure_kind": type(exc).__name__, "reason": str(exc)}
            if failure is None:
                last_output = output
                last_output_digest = content_digest(output)
            executions.append(
                LegacyC8StepExecution(
                    step_id=step.step_id,
                    operation_id=step.operation_id,
                    operation_digest=ref.contract_digest,
                    order=order,
                    input_digest=input_digest,
                    output=output,
                    failure=failure,
                )
            )
        step_trace = [
            {
                "step_id": execution.step_id,
                "operation_id": execution.operation_id,
                "operation_digest": execution.operation_digest,
                "order": execution.order,
            }
            for execution in executions
        ]
        return {
            "interpreter_id": self.interpreter_id,
            "consumed_program_digest": program.program_digest,
            "consumed_plan_digest": plan.plan_digest,
            "ordered_step_trace": [execution.operation_id for execution in executions],
            "step_trace": step_trace,
            "step_executions": [
                {
                    "step_id": execution.step_id,
                    "operation_id": execution.operation_id,
                    "operation_digest": execution.operation_digest,
                    "input_digest": execution.input_digest,
                    "output": execution.output,
                    "failure": execution.failure,
                }
                for execution in executions
            ],
            "step_outputs": [execution.output for execution in executions],
            "consumed_operation_digests": [
                execution.operation_digest for execution in executions
            ],
            "consumed_calls": self.consumed_calls,
            "provider_calls": 0,
            "store_writes": 0,
        }

    def _validate_pair(
        self,
        program: ProgramSpec,
        plan: Any,
        *,
        donors: LegacyC8DonorRegistry,
        seed_inputs: Mapping[str, tuple[Any, str | None]],
    ) -> None:
        if program.program_digest != program.digest():
            raise ValueError(
                "tampered ProgramSpec: program_digest does not match canonical bytes"
            )
        if plan.plan_digest != with_plan_digest(plan).plan_digest:
            raise ValueError(
                "tampered ExecutionPlan: plan_digest does not match canonical bytes"
            )
        if program.program_digest != plan.program_digest:
            raise ValueError(
                "mixed Program/Plan pair: program digest does not match plan"
            )
        for seed_payload, expected_digest in seed_inputs.values():
            if getattr(seed_payload, "project_key", program.project_key) != (
                program.project_key
            ):
                raise ValueError("seed input project scope does not match Program")
            actual_digest = payload_body_digest(seed_payload)
            if expected_digest is not None and expected_digest != actual_digest:
                raise ValueError("seed input digest does not match DTO body")
        missing_closure = [
            step.operation_contract_ref.kind
            for step in plan.ordered_steps
            if step.operation_contract_ref is not None
            and donors.resolve(step.operation_contract_ref.contract_digest) is None
        ]
        if missing_closure:
            raise ValueError(
                "handler closure incomplete for operation digests: "
                + ",".join(sorted(set(missing_closure)))
            )
