"""Law observations for the frozen P0-A Program/ExecutionPlan core."""

from __future__ import annotations

from dataclasses import dataclass

from .compile import compose_plans, map_plan_output
from .plan import ExecutionPlan, identity_plan, normalized_plan_structure
from .transforms import TransformRef


@dataclass(frozen=True, slots=True)
class LawResult:
    law: str
    holds: bool
    left: object
    right: object
    counterexample: str | None = None


def left_identity(plan: ExecutionPlan) -> LawResult:
    left = normalized_plan_structure(compose_plans(identity_plan(plan.input_type), plan))
    right = normalized_plan_structure(plan)
    return LawResult("left_identity", left == right, left, right)


def right_identity(plan: ExecutionPlan) -> LawResult:
    left = normalized_plan_structure(compose_plans(plan, identity_plan(plan.output_type)))
    right = normalized_plan_structure(plan)
    return LawResult("right_identity", left == right, left, right)


def normalization_associativity(
    first: ExecutionPlan, second: ExecutionPlan, third: ExecutionPlan
) -> LawResult:
    left = normalized_plan_structure(compose_plans(compose_plans(first, second), third))
    right = normalized_plan_structure(compose_plans(first, compose_plans(second, third)))
    return LawResult("normalization_associativity", left == right, left, right)


def map_output_preservation(
    compiled_map: ExecutionPlan,
    source: ExecutionPlan,
    transform: TransformRef,
) -> LawResult:
    mapped = map_plan_output(source, transform, compiled_map.output_type)
    left = normalized_plan_structure(compiled_map)
    right = normalized_plan_structure(mapped)
    return LawResult("map_output_preservation", left == right, left, right)


def zip_ordered_noncommutativity(
    left_then_right: ExecutionPlan,
    right_then_left: ExecutionPlan,
    *,
    specimen: str,
) -> LawResult:
    left = normalized_plan_structure(left_then_right)
    right = normalized_plan_structure(right_then_left)
    return LawResult(
        "zip_ordered_noncommutativity",
        left != right,
        left,
        right,
        None if left != right else specimen,
    )

def failure_return_barrier_preservation(
    source: ExecutionPlan, downstream: ExecutionPlan
) -> LawResult:
    composed = compose_plans(source, downstream)
    downstream_ids = {step.step_id for step in downstream.ordered_steps if not step.dependencies}
    required = set(source.return_policy.exported_barrier_step_ids)
    observed = {
        dependency
        for step in composed.ordered_steps
        if step.step_id in downstream_ids
        for dependency in step.dependencies
    }
    return LawResult(
        "failure_return_barrier_preservation",
        required <= observed,
        tuple(sorted(required)),
        tuple(sorted(observed)),
        None if required <= observed else "downstream escaped the source semantic return barrier",
    )
