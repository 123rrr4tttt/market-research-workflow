"""Successor-native deterministic interpreters for the acquisition batch family.

The interpreters are deterministic rewrites of the legacy
``collect_runtime`` pure plan rules and ordered result fold.  They perform no
network, database, provider or credential work, and they never import legacy
service packages.  The legacy path is exercised only by the sibling
``successor_migration.legacy_collect_runtime`` adapter.

Ordered traversal is realized in-process from the frozen batch plan until the
shared compiler supports ``TraverseOrdered``; every binding check refuses to
claim a compiled traversal.  Parallel execution reconstructs results by input
index; no commutativity of effect traces is inferred.
"""

from __future__ import annotations
import dataclasses
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeAlias, TypeVar, runtime_checkable
from functorial_kit import Failure
from app.successor_runtime.capabilities import acquisition_batch as acquisition
from app.successor_runtime.capabilities import acquisition_batch_program as cp
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest, sha256_hex
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.compile import TRAVERSAL_MATERIALIZER_TRANSFORM, TRAVERSAL_MATERIALIZER_VERSION
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.research.codec import is_sha256_hex

__all__ = [
    "COLLECT_EXECUTE_BATCH_ELEMENT_LEGACY_INTERPRETER_ID",
    "COLLECT_EXECUTE_BATCH_ELEMENT_INTERPRETER_ID",
    "COLLECT_FOLD_ORDERED_RESULTS_LEGACY_INTERPRETER_ID",
    "COLLECT_FOLD_ORDERED_RESULTS_INTERPRETER_ID",
    "CollectBindingMismatch",
    "CollectFoldSuccessorInterpreter",
    "CollectTraversalSuccessorInterpreter",
    "ComposedCollectSuccessorInterpreter",
    "ElementPayloadView",
    "ElementRunner",
    "FoldPayloadView",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterSuccess",
    "ProjectScopeView",
    "RequestRefView",
    "ExactBindingResult",
    "authority_requirement_digest",
    "deterministic_composed_element_runner",
    "legacy_execute_element_interpreter_profile_digest",
    "legacy_fold_ordered_results_interpreter_profile_digest",
    "require_exact_collect_binding",
    "require_exact_composed_binding",
    "require_exact_traversal_binding",
    "run_ordered_traversal",
    "successor_execute_element_interpreter_profile_digest",
    "successor_fold_ordered_results_interpreter_profile_digest",
    "try_exact_collect_binding",
    "try_exact_composed_binding",
    "try_exact_traversal_binding",
]
COLLECT_EXECUTE_BATCH_ELEMENT_LEGACY_INTERPRETER_ID = "legacy.collect_runtime.batch_traverse.v1"
COLLECT_EXECUTE_BATCH_ELEMENT_INTERPRETER_ID = "mrw.acquisition.batch.execute_element.interpreter.v2"
COLLECT_FOLD_ORDERED_RESULTS_LEGACY_INTERPRETER_ID = "legacy.collect_runtime.result_fold.v1"
COLLECT_FOLD_ORDERED_RESULTS_INTERPRETER_ID = "mrw.acquisition.batch.fold_ordered_results.interpreter.v2"
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    value: T
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    code: str
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


InterpreterOutcome: TypeAlias = InterpreterSuccess[T] | InterpreterFailure
ExactBindingResult: TypeAlias = "Any | Failure"


@runtime_checkable
class ProjectScopeView(Protocol):
    project_key: str
    registry_revision: int
    scope_digest: str


@runtime_checkable
class RequestRefView(Protocol):
    request_id: str
    project_key: str
    channel: str
    request_digest: str


@runtime_checkable
class ElementPayloadView(Protocol):
    schema_version: str
    operation_kind: str
    parent_request_ref: RequestRefView
    request_snapshot: Any
    element: Any
    resource_policy: Any
    authority_scope_ref: str
    payload_digest: str


@runtime_checkable
class FoldPayloadView(Protocol):
    schema_version: str
    operation_kind: str
    parent_request_ref: RequestRefView
    ordered_outcomes: Any
    aggregation_policy_ref: str
    observation_profile_ref: str
    payload_digest: str


@runtime_checkable
class ElementRunner(Protocol):
    def run(self, element: acquisition.CollectBatchElement) -> acquisition.CollectElementOutcome:
        """Run one bounded element and return its typed outcome."""


class CollectBindingMismatch(ValueError):
    """Raised when Program/Plan/payload/project/catalog/binding drift."""


def _exact_binding_failure(*, message: str, site: str) -> Failure:
    return acquisition.collect_contract_failure(
        code="ASSIGNMENT_BINDING_MISMATCH",
        reason_code="program_binding_invalid",
        message=message,
        operation="collect.require_exact_binding",
        site=site,
        domain_outcome="INVALID_INPUT",
        public_exception="CollectBindingMismatch",
    )


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def try_exact_collect_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: Any,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> ExactBindingResult:
    """Return the exact acquisition closure or one canonical binding failure."""
    failures: list[str] = []
    expected_kind = payload.operation_kind
    if expected_kind not in {
        acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND,
        acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND,
    }:
        failures.append("payload operation_kind")
    if program.project_key != project_scope.project_key:
        failures.append("program/project key")
    if program.project_registry_revision != project_scope.registry_revision:
        failures.append("program/registry revision")
    if program.project_scope_digest != project_scope.scope_digest:
        failures.append("program/scope digest")
    if payload.parent_request_ref.project_key != project_scope.project_key:
        failures.append("payload/scope project key")
    program_metadata = dict(program.metadata)
    if program_metadata.get("operation_kind") != expected_kind:
        failures.append("program metadata/operation kind")
    if program_metadata.get("catalog_digest") != catalog.catalog_digest:
        failures.append("program metadata/catalog digest")
    if program_metadata.get("request_id") != payload.parent_request_ref.request_id:
        failures.append("program metadata/request id")
    if program_metadata.get("request_digest") != payload.parent_request_ref.request_digest:
        failures.append("program metadata/request digest")
    if (
        expected_kind == acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND
        and program_metadata.get("compiled_traversal") is not False
    ):
        failures.append("compiled traversal claim without compiler binding")
    if program_metadata.get("payload_content_digest") != payload_ref.content_digest:
        failures.append("program metadata/payload content digest")
    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id:
        failures.append("plan/program id")
    if plan.program_digest != program.program_digest:
        failures.append("plan/program digest")
    if not _is_hex64(plan.plan_digest):
        failures.append("plan digest")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        failures.append("plan digest forged")
    payload_type = (
        acquisition.COLLECT_BATCH_ELEMENT_PAYLOAD_TYPE
        if expected_kind == acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND
        else acquisition.COLLECT_FOLD_PAYLOAD_TYPE
    )
    result_type = (
        acquisition.COLLECT_ELEMENT_OUTCOME_TYPE
        if expected_kind == acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND
        else acquisition.COLLECT_FOLD_RESULT_TYPE
    )
    if getattr(plan.input_type, "type_id", None) != payload_type.type_id:
        failures.append("plan input type")
    if getattr(plan.output_type, "type_id", None) != result_type.type_id:
        failures.append("plan output type")
    effect_steps = tuple(
        (step for step in plan.ordered_steps if step.step_kind == "EFFECT" and step.operation_contract_ref is not None)
    )
    if len(effect_steps) != 1:
        failures.append("plan effect steps")
    else:
        step_ref = effect_steps[0].operation_contract_ref
        if (
            step_ref.kind != contract_ref.kind
            or step_ref.contract_version != contract_ref.contract_version
            or step_ref.contract_digest != contract_ref.contract_digest
        ):
            failures.append("plan/contract ref")
    if any((step.step_kind == "ADMISSION" for step in plan.ordered_steps)):
        failures.append("plan admission step")
    if contract_ref.kind != expected_kind:
        failures.append("contract kind")
    if not _is_hex64(contract_ref.contract_digest):
        failures.append("contract digest")
    catalog_ref = catalog.lookup(contract_ref)
    if catalog_ref is None or catalog_ref.contract_digest != contract_ref.contract_digest:
        failures.append("catalog/contract ref")
    plain = dataclasses.asdict(payload)
    expected_content_digest = sha256_hex(canonical_json(plain).encode("utf-8"))
    if payload_ref.content_digest != expected_content_digest:
        failures.append("payload ref content digest")
    if payload_ref.project_key != project_scope.project_key:
        failures.append("payload ref project key")
    if getattr(payload_ref.object_type, "type_id", None) != payload_type.type_id:
        failures.append("payload ref object type")
    if not _is_hex64(payload_ref.provenance_digest):
        failures.append("payload ref provenance digest")
    if not _is_hex64(binding.binding_digest):
        failures.append("binding digest")
    if getattr(binding, "operation_contract_digest", None) != contract_ref.contract_digest:
        failures.append("binding/contract digest")
    if getattr(binding, "project_scope_digest", None) != project_scope.scope_digest:
        failures.append("binding/scope digest")
    if not _is_hex64(deployment_catalog_digest):
        failures.append("deployment catalog digest")
    if getattr(binding, "deployment_catalog_digest", None) != deployment_catalog_digest:
        failures.append("binding/deployment catalog digest")
    if (
        expected_interpreter_profile_digest is not None
        and getattr(binding, "interpreter_profile_digest", None) != expected_interpreter_profile_digest
    ):
        failures.append("binding/interpreter profile")
    if failures:
        return _exact_binding_failure(
            message="C3 collect binding drift: " + ", ".join(sorted(set(failures))), site="try_exact_collect_binding"
        )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "contract_digest": contract_ref.contract_digest,
        "payload_content_digest": payload_ref.content_digest,
        "binding_digest": binding.binding_digest,
    }


def require_exact_collect_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: Any,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    """Preserve the legacy exception ABI for exact acquisition binding checks."""
    result = try_exact_collect_binding(
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=project_scope,
        catalog=catalog,
        deployment_catalog_digest=deployment_catalog_digest,
        binding=binding,
        expected_interpreter_profile_digest=expected_interpreter_profile_digest,
    )
    if isinstance(result, Failure):
        acquisition.raise_collect_contract_failure(result, CollectBindingMismatch)
    return result


def try_exact_traversal_binding(
    *, program: Any, plan: Any, catalog: OperationContractCatalogSnapshot
) -> ExactBindingResult:
    """Return the exact traversal binding or one canonical failure."""
    failures: list[str] = []
    program_metadata = dict(program.metadata)
    if program_metadata.get("operation_kind") != acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND:
        failures.append("program metadata/operation kind")
    if program_metadata.get("compiled_traversal") is not True:
        failures.append("compiled traversal claim without compiler binding")
    traversal_policy = program_metadata.get("traversal_policy")
    if traversal_policy not in {"STATIC_SHAPE", "MATERIALIZED_SHAPE"}:
        failures.append("program metadata/traversal policy")
    if program_metadata.get("catalog_digest") != catalog.catalog_digest:
        failures.append("program metadata/catalog digest")
    if program_metadata.get("program_id") != program.program_id:
        failures.append("program metadata/program id")
    shape_digest = program_metadata.get("traversal_shape_digest")
    element_count = program_metadata.get("traversal_element_count")
    if traversal_policy == "STATIC_SHAPE":
        if not isinstance(shape_digest, str) or not _is_hex64(shape_digest):
            failures.append("static traversal shape digest")
        if not isinstance(element_count, int) or isinstance(element_count, bool) or element_count < 0:
            failures.append("static traversal element count")
    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id:
        failures.append("plan/program id")
    if plan.program_digest != program.program_digest:
        failures.append("plan/program digest")
    if not _is_hex64(plan.plan_digest):
        failures.append("plan digest")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        failures.append("plan digest forged")
    transform_steps = tuple(
        (step for step in plan.ordered_steps if step.step_kind == "TRANSFORM" and step.transform_ref is not None)
    )
    if len(transform_steps) != 1:
        failures.append("plan traversal transform steps")
    else:
        transform = transform_steps[0].transform_ref
        if transform.name != TRAVERSAL_MATERIALIZER_TRANSFORM or transform.version != TRAVERSAL_MATERIALIZER_VERSION:
            failures.append("plan traversal transform ref")
        if not _is_hex64(transform.digest):
            failures.append("plan traversal binding digest")
    attributes = dict(plan.control_root.attributes)
    if (
        transform_steps
        and transform_steps[0].transform_ref is not None
        and (transform_steps[0].transform_ref.digest != attributes.get("binding_digest"))
    ):
        failures.append("plan traversal/control binding digest")
    if attributes.get("realization") != "SUCCESSOR_PROGRAM_EPOCH":
        failures.append("plan traversal realization")
    if attributes.get("output_order") != "INPUT_INDEX":
        failures.append("plan traversal output order")
    if failures:
        return _exact_binding_failure(
            message="C3 traversal binding drift: " + ", ".join(sorted(set(failures))),
            site="try_exact_traversal_binding",
        )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "traversal_binding_digest": str(transform_steps[0].transform_ref.digest),
        "element_program_digest": str(program_metadata.get("element_program_digest")),
        "traversal_element_count": int(element_count if element_count is not None else 0),
    }


def require_exact_traversal_binding(
    *, program: Any, plan: Any, catalog: OperationContractCatalogSnapshot
) -> dict[str, str | int]:
    """Preserve the legacy exception ABI for traversal binding checks."""
    result = try_exact_traversal_binding(program=program, plan=plan, catalog=catalog)
    if isinstance(result, Failure):
        acquisition.raise_collect_contract_failure(result, CollectBindingMismatch)
    return result


def _failed_outcome(element: acquisition.CollectBatchElement, exc: Exception) -> acquisition.CollectElementFailed:
    error = acquisition.CollectElementError(
        code="auto_batch_execution_failed",
        message=str(exc) or exc.__class__.__name__,
        query_terms=element.query_terms,
        exception_type=exc.__class__.__name__,
        error_digest="",
    )
    return acquisition.CollectElementFailed(
        schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
        element_id=element.element_id,
        input_index=element.input_index,
        error=error,
        counts=acquisition.CollectCounts(),
        links=(),
        receipt=None,
        legacy_observation_ref="legacy:" + error.error_digest,
        outcome_digest="",
    )


def _cancellation_receipt(
    cause: acquisition.CollectElementError, *, trigger_input_index: int, observed: str
) -> acquisition.CollectCancellationReceipt:
    return acquisition.CollectCancellationReceipt(
        schema_version=acquisition.COLLECT_CANCELLATION_RECEIPT_SCHEMA_REF,
        code="FAIL_FAST_CANCELLED",
        message=cause.message,
        trigger_input_index=trigger_input_index,
        observed=observed,
        receipt_digest="",
    )


def run_ordered_traversal(
    plan: acquisition.CollectBatchPlan, runner: ElementRunner
) -> acquisition.CollectTraversalResult:
    """Deterministic ordered traversal over a frozen finite batch plan."""
    if plan.disposition == "BYPASSED":
        return acquisition.CollectTraversalBypassed(
            schema_version=acquisition.COLLECT_TRAVERSAL_RESULT_SCHEMA_REF, request_ref=plan.request_ref
        )
    elements = list(plan.elements)

    def run_one(element: acquisition.CollectBatchElement) -> acquisition.CollectElementOutcome:
        try:
            return runner.run(element)
        except Exception as exc:
            return _failed_outcome(element, exc)

    indexed: list[tuple[int, acquisition.CollectElementOutcome]] = []
    if plan.effective_parallelism <= 1 or len(elements) <= 1:
        for element in elements:
            outcome = run_one(element)
            if (
                isinstance(outcome, acquisition.CollectElementFailed)
                and plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION"
            ):
                executed = sorted(indexed + [(outcome.input_index, outcome)], key=lambda item: item[0])
                return acquisition.OrderedTraversalAborted(
                    schema_version=acquisition.COLLECT_TRAVERSAL_RESULT_SCHEMA_REF,
                    partial_outcomes=tuple((item for _index, item in executed)),
                    cause=outcome.error,
                    cancellation_receipt=_cancellation_receipt(
                        outcome.error, trigger_input_index=outcome.input_index, observed="SERIAL_EXECUTION"
                    ),
                    cancellation_observed=True,
                    request_ref=plan.request_ref,
                )
            indexed.append((outcome.input_index, outcome))
    else:
        with ThreadPoolExecutor(
            max_workers=plan.effective_parallelism, thread_name_prefix="acquisition-batch"
        ) as executor:
            future_map = {executor.submit(copy_context().run, run_one, element): element for element in elements}
            for future in as_completed(future_map):
                outcome = future.result()
                indexed.append((outcome.input_index, outcome))
        ordered = [outcome for _index, outcome in sorted(indexed)]
        if plan.failure_policy == "FAIL_FAST_WITH_PARTIAL_OBSERVATION":
            failed = next(
                (outcome for outcome in ordered if isinstance(outcome, acquisition.CollectElementFailed)), None
            )
            if failed is not None:
                return acquisition.OrderedTraversalAborted(
                    schema_version=acquisition.COLLECT_TRAVERSAL_RESULT_SCHEMA_REF,
                    partial_outcomes=tuple(ordered),
                    cause=failed.error,
                    cancellation_receipt=_cancellation_receipt(
                        failed.error, trigger_input_index=failed.input_index, observed="PARALLEL_COMPLETION"
                    ),
                    cancellation_observed=True,
                    request_ref=plan.request_ref,
                )
    ordered_outcomes = tuple((outcome for _index, outcome in sorted(indexed)))
    observation = acquisition.CollectTraversalObservation(
        schema_version=acquisition.COLLECT_TRAVERSAL_OBSERVATION_SCHEMA_REF,
        observation_profile=acquisition.COLLECT_TRAVERSAL_OBSERVATION_PROFILE,
        request_ref=plan.request_ref,
        traversal_policy=plan.traversal_policy,
        failure_policy=plan.failure_policy,
        ordered_outcomes=ordered_outcomes,
        requested_parallelism=plan.requested_parallelism,
        effective_parallelism=plan.effective_parallelism,
        cancellation_observed=False,
        observation_digest="",
    )
    if len(ordered_outcomes) == 1:
        return acquisition.CollectTraversalSingleton(
            schema_version=acquisition.COLLECT_TRAVERSAL_RESULT_SCHEMA_REF, observation=observation
        )
    return acquisition.OrderedTraversalCompleted(
        schema_version=acquisition.COLLECT_TRAVERSAL_RESULT_SCHEMA_REF, observation=observation
    )


def _find_control_node(node: Any, step_id: str) -> Any | None:
    if step_id in node.step_ids:
        return node
    for child in node.children:
        found = _find_control_node(child, step_id)
        if found is not None:
            return found
    return None


def try_exact_composed_binding(
    *, program: Any, plan: Any, catalog: OperationContractCatalogSnapshot, assignment: Any | None = None
) -> ExactBindingResult:
    """Return the exact composed closure or one canonical failure."""
    failures: list[str] = []
    metadata = dict(program.metadata)
    payload_closure_fields = (
        "payload_value_id",
        "payload_storage_ref",
        "payload_content_digest",
        "payload_provenance_digest",
        "payload_object_type",
        "payload_codec_id",
        "payload_byte_size",
        "payload_element_count",
        "payload_element_digests",
        "payload_incarnation",
    )
    missing_closure = [name for name in payload_closure_fields if name not in metadata]
    if missing_closure:
        failures.append("program metadata/payload closure: " + ", ".join(missing_closure))
    if metadata.get("operation_kind") != acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND:
        failures.append("program metadata/operation kind")
    if metadata.get("fold_atom_kind") != acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND:
        failures.append("program metadata/fold atom kind")
    if metadata.get("compiled_traversal") is not True:
        failures.append("compiled traversal claim without compiler binding")
    if metadata.get("catalog_digest") != catalog.catalog_digest:
        failures.append("program metadata/catalog digest")
    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id or plan.program_digest != program.program_digest:
        failures.append("plan/program binding")
    if plan.plan_digest != with_plan_digest(plan).plan_digest:
        failures.append("plan digest forged")
    transform_steps = tuple(
        (step for step in plan.ordered_steps if step.step_kind == "TRANSFORM" and step.transform_ref is not None)
    )
    traverse_steps = tuple(
        (step for step in transform_steps if step.transform_ref.name == TRAVERSAL_MATERIALIZER_TRANSFORM)
    )
    fold_map_steps = tuple(
        (
            step
            for step in transform_steps
            if step.transform_ref.name == cp.COLLECT_SEQUENCE_TO_FOLD_PAYLOAD_TRANSFORM_NAME
        )
    )
    if len(traverse_steps) != 1 or len(fold_map_steps) != 1:
        failures.append("composed plan transform steps")
    else:
        traverse_step = traverse_steps[0]
        control = _find_control_node(plan.control_root, traverse_step.step_id)
        attributes = {} if control is None else dict(control.attributes)
        if attributes.get("realization") != "SUCCESSOR_PROGRAM_EPOCH":
            failures.append("traversal materialization epoch")
        if attributes.get("output_order") != "INPUT_INDEX":
            failures.append("traversal output order")
    effect_steps = tuple(
        (step for step in plan.ordered_steps if step.step_kind == "EFFECT" and step.operation_contract_ref is not None)
    )
    if len(effect_steps) != 1:
        failures.append("composed plan effect steps")
    elif effect_steps[0].operation_contract_ref.kind != acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND:
        failures.append("composed fold atom contract")
    if getattr(plan.output_type, "type_id", None) != acquisition.COLLECT_FOLD_RESULT_TYPE.type_id:
        failures.append("composed plan output type")
    if any((step.step_kind == "ADMISSION" for step in plan.ordered_steps)):
        failures.append("composed plan admission step")
    if metadata.get("payload_element_count") != metadata.get("element_payload_count"):
        failures.append("program metadata/payload count drift")
    element_digests = metadata.get("payload_element_digests")
    if (
        not isinstance(element_digests, tuple)
        or len(element_digests) != metadata.get("payload_element_count")
        or any((not isinstance(value, str) or len(value) != 64 for value in element_digests))
    ):
        failures.append("program metadata/payload element digests")
    incarnation = metadata.get("payload_incarnation")
    if not isinstance(incarnation, str) or not incarnation.startswith("payload-inc:"):
        failures.append("program metadata/payload incarnation")
    if assignment is not None:
        expected_storage_ref = metadata.get("payload_storage_ref")
        if assignment.payload_ref != expected_storage_ref:
            failures.append("assignment/payload ref")
        if assignment.payload_digest != metadata.get("payload_content_digest"):
            failures.append("assignment/payload digest")
        if assignment.input_refs != (expected_storage_ref,):
            failures.append("assignment/input refs")
        expected_input_closure = sha256_hex(canonical_json({"input_refs": (expected_storage_ref,)}).encode("utf-8"))
        if assignment.input_closure_digest != expected_input_closure:
            failures.append("assignment/input closure digest")
    if failures:
        return _exact_binding_failure(
            message="C3 composed binding drift: " + ", ".join(sorted(set(failures))), site="try_exact_composed_binding"
        )
    return {
        "composed_program_digest": program.program_digest,
        "composed_plan_digest": plan.plan_digest,
        "traversal_binding_digest": traverse_steps[0].transform_ref.digest,
        "fold_binding_digest": effect_steps[0].operation_contract_ref.contract_digest,
        "payload_value_id": str(metadata["payload_value_id"]),
        "payload_content_digest": str(metadata["payload_content_digest"]),
        "payload_element_count": str(metadata["payload_element_count"]),
        "payload_incarnation": str(metadata["payload_incarnation"]),
    }


def require_exact_composed_binding(
    *, program: Any, plan: Any, catalog: OperationContractCatalogSnapshot, assignment: Any | None = None
) -> dict[str, str]:
    """Preserve the legacy exception ABI for composed binding checks."""
    result = try_exact_composed_binding(program=program, plan=plan, catalog=catalog, assignment=assignment)
    if isinstance(result, Failure):
        acquisition.raise_collect_contract_failure(result, CollectBindingMismatch)
    return result


def deterministic_composed_element_runner(
    receipts: tuple[acquisition.CollectAttemptReceipt | None, ...] = (),
) -> ElementRunner:
    """Captured fixture runner: no provider, optional per-index receipts."""

    def run(element: acquisition.CollectBatchElement) -> acquisition.CollectElementOutcome:
        receipt = receipts[element.input_index] if element.input_index < len(receipts) else None
        return acquisition.CollectElementSucceeded(
            schema_version=acquisition.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
            element_id=element.element_id,
            input_index=element.input_index,
            counts=acquisition.CollectCounts(inserted=len(element.query_terms)),
            links=tuple((f"https://shadow.example/{term}" for term in element.query_terms)),
            receipt=receipt,
            legacy_observation_ref="legacy:"
            + content_digest(
                {
                    "schema": "mrw.acquisition.batch.shadow-element.v2",
                    "element_id": element.element_id,
                    "input_index": element.input_index,
                }
            ),
            outcome_digest="",
        )

    return ElementRunnerType(run)


class ElementRunnerType:
    def __init__(self, func: Any) -> None:
        self.func = func

    def run(self, element: acquisition.CollectBatchElement) -> acquisition.CollectElementOutcome:
        return self.func(element)


class CollectTraversalSuccessorInterpreter:
    """Bound interpreter for one acquisition batch element atom."""

    interpreter_id = COLLECT_EXECUTE_BATCH_ELEMENT_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: ElementPayloadView,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
        runner: ElementRunner,
    ) -> InterpreterOutcome[acquisition.CollectElementOutcome]:
        try:
            require_exact_collect_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=successor_execute_element_interpreter_profile_digest(),
            )
        except CollectBindingMismatch as exc:
            return InterpreterFailure(code="ASSIGNMENT_BINDING_MISMATCH", message=str(exc), retryable=False)
        try:
            return InterpreterSuccess(runner.run(payload.element))
        except Exception as exc:
            return InterpreterSuccess(_failed_outcome(payload.element, exc))


class CollectFoldSuccessorInterpreter:
    """Bound interpreter for the ordered result fold."""

    interpreter_id = COLLECT_FOLD_ORDERED_RESULTS_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: FoldPayloadView,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> InterpreterOutcome[acquisition.CollectAggregateOutcome]:
        try:
            require_exact_collect_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=successor_fold_ordered_results_interpreter_profile_digest(),
            )
        except CollectBindingMismatch as exc:
            return InterpreterFailure(code="ASSIGNMENT_BINDING_MISMATCH", message=str(exc), retryable=False)
        return InterpreterSuccess(
            acquisition.fold_ordered_results(
                payload.ordered_outcomes,
                aggregation_policy_ref=payload.aggregation_policy_ref,
                observation_profile_ref=payload.observation_profile_ref,
            )
        )


class ComposedCollectSuccessorInterpreter:
    """Successor composed TraverseOrdered->MapOutput->Fold interpreter.

    Consumes the same exact composed Program/Plan as the legacy shadow and
    captured element fixtures/receipts, never dispatching a provider.
    """

    interpreter_id = "mrw.acquisition.batch.traverse-fold.interpreter.v2"

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        catalog: OperationContractCatalogSnapshot,
        binding: Any,
        element_payloads: tuple[acquisition.CollectBatchElementPayload, ...],
        receipts: tuple[acquisition.CollectAttemptReceipt | None, ...] = (),
        assignment: Any | None = None,
    ) -> InterpreterOutcome[acquisition.CollectAggregateOutcome]:
        if not _is_hex64(binding.binding_digest):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message="successor composed binding digest is not canonical",
                retryable=False,
            )
        if binding.interpreter_profile_digest != successor_fold_ordered_results_interpreter_profile_digest():
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message="composed binding is not the ordered-result fold profile",
                retryable=False,
            )
        binding_result = try_exact_composed_binding(program=program, plan=plan, catalog=catalog, assignment=assignment)
        if isinstance(binding_result, Failure):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH", message=str(binding_result.message), retryable=False
            )
        if not element_payloads:
            return InterpreterFailure(
                code="INVALID_INPUT", message="composed shadow requires element payloads", retryable=False
            )
        first_payload = element_payloads[0]
        family_plan = acquisition.build_collect_batch_plan(
            request_ref=first_payload.parent_request_ref,
            snapshot=first_payload.request_snapshot,
            plan_id=f"shadow:{program.program_id}",
            resource_policy=first_payload.resource_policy,
            authority_scope_ref=first_payload.authority_scope_ref,
        )
        traversal = run_ordered_traversal(family_plan, deterministic_composed_element_runner(receipts))
        observation = getattr(traversal, "observation", None)
        if observation is None:
            return InterpreterFailure(
                code="ORDERED_TRAVERSAL_ABORTED", message="composed shadow traversal aborted", retryable=False
            )
        sequence = acquisition.OrderedCollectElementOutcomeSequence(
            schema_version=acquisition.ORDERED_OUTCOME_SEQUENCE_SCHEMA_REF,
            parent_request_ref=first_payload.parent_request_ref,
            outcomes=observation.ordered_outcomes,
            sequence_digest="",
        )
        aggregate = acquisition.fold_ordered_results(
            sequence,
            aggregation_policy_ref=acquisition.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
            observation_profile_ref=acquisition.COLLECT_FOLD_OBSERVATION_PROFILE,
        )
        if isinstance(aggregate, acquisition.CollectFoldContractFailure):
            return InterpreterFailure(code="FOLD_CONTRACT_FAILURE", message=aggregate.reason, retryable=False)
        return InterpreterSuccess(aggregate)


def legacy_execute_element_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": COLLECT_EXECUTE_BATCH_ELEMENT_LEGACY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "collect_runtime._should_auto_batch+_split_query_terms+_execute_auto_batch",
        }
    )


def successor_execute_element_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": COLLECT_EXECUTE_BATCH_ELEMENT_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "acquisition batch element ordered traversal algebra",
        }
    )


def legacy_fold_ordered_results_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": COLLECT_FOLD_ORDERED_RESULTS_LEGACY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "collect_runtime._merge_collect_results",
        }
    )


def successor_fold_ordered_results_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": COLLECT_FOLD_ORDERED_RESULTS_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "acquisition ordered result fold algebra",
        }
    )


def authority_requirement_digest(operation_kind: str | None = None) -> str:
    if operation_kind is None:
        return content_digest(
            {
                "schema": "mrw.successor.collect.c3.authority.v1",
                "canonical_owner": "collect.c3.v1",
                "authority": "execute bounded collect elements and fold observed receipts; never admits documents, qualifies evidence or completes queued acks",
                "grant_scope": "project",
            }
        )
    if operation_kind == acquisition.COLLECT_EXECUTE_BATCH_ELEMENT_KIND:
        schema = "mrw.acquisition.batch.execute_element.authority.v2"
        owner = acquisition.ACQUISITION_BATCH_EXECUTE_ELEMENT_OWNER
    elif operation_kind == acquisition.COLLECT_FOLD_ORDERED_RESULTS_KIND:
        schema = "mrw.acquisition.batch.fold_ordered_results.authority.v2"
        owner = acquisition.ACQUISITION_BATCH_FOLD_ORDERED_RESULTS_OWNER
    else:
        failure = acquisition.collect_contract_failure(
            code="INVALID_INPUT",
            reason_code="authority_operation_unsupported",
            message=f"unsupported acquisition authority operation {operation_kind!r}",
            operation="acquisition.authority_requirement_digest",
            site="authority_requirement_digest",
            domain_outcome="INVALID_INPUT",
        )
        acquisition.raise_collect_contract_failure(failure, ValueError)
    return content_digest(
        {
            "schema": schema,
            "canonical_owner": owner,
            "authority": "execute bounded collect elements and fold observed receipts; never admits documents, qualifies evidence or completes queued acks",
            "grant_scope": "project",
        }
    )
