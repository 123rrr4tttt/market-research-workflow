"""Native project-bound task rule for the canonical raw Material import."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Protocol, cast, runtime_checkable

from functorial_kit import Failure
from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    NativeContribution,
    ProjectedContributionSpec,
)

from app.contracts.raw_material_import import RawImportRequest
from app.services.ingest.raw_import import RawObject, run_raw_import_materials
from app.services.projects import bind_project

RAW_MATERIAL_IMPORT_TASK_NAME = "app.services.tasks.task_raw_import_materials"
RAW_MATERIAL_IMPORT_TASK_OWNER = "app.services.ingest.raw_import"
RAW_MATERIAL_IMPORT_TASK_RULE_ID = "mrw.project-bound-material-import-task.v1"

RawMaterialImportKernel = Callable[[RawObject, str], RawObject]
RawMaterialImportTaskRun = Callable[[RawObject, str | None], RawObject]


class RawMaterialImportAsyncResult(Protocol):
    id: str


@runtime_checkable
class RawMaterialImportRegisteredTask(Protocol):
    name: str
    run: RawMaterialImportTaskRun

    def delay(
        self,
        payload: RawObject,
        project_key: str,
    ) -> RawMaterialImportAsyncResult: ...


RawMaterialImportTaskRegistrar = Callable[
    [str, RawMaterialImportTaskRun],
    object,
]
RawMaterialImportTaskResolver = Callable[[str], object | None]


@dataclass(frozen=True, slots=True)
class RawMaterialImportTaskDefinition:
    """One authored task identity, request type, and original domain kernel."""

    task_name: str
    request_type: type[RawImportRequest]
    kernel: RawMaterialImportKernel

    @property
    def contribution_id(self) -> str:
        return f"mrw.project-bound-task:{self.task_name}"

    def payload(self, request: RawImportRequest) -> RawObject:
        if not isinstance(request, self.request_type):
            raise TypeError("raw Material import request type differs from the native definition")
        return {
            str(key): value
            for key, value in request.model_dump(mode="json").items()
        }

    def run_request(self, request: RawImportRequest, project_key: str) -> RawObject:
        return run_raw_material_import_payload(
            self,
            self.payload(request),
            project_key,
        )


@runtime_checkable
class RawMaterialImportTaskRunner(Protocol):
    definition: RawMaterialImportTaskDefinition

    def __call__(
        self,
        payload: RawObject,
        project_key: str | None = None,
    ) -> RawObject: ...


def _derive_raw_material_import_task_runner(
    definition: RawMaterialImportTaskDefinition,
) -> RawMaterialImportTaskRunner:
    """Derive the one named Celery runner and retain its definition witness."""

    def run(
        payload: RawObject,
        project_key: str | None = None,
    ) -> RawObject:
        context = bind_project(project_key) if project_key else nullcontext()
        with context:
            return definition.kernel(payload or {}, project_key or "")

    setattr(run, "definition", definition)
    return cast(RawMaterialImportTaskRunner, run)


@dataclass(frozen=True, slots=True)
class RawMaterialImportTaskAssemblyContext:
    """The existing Celery registry; assembly grants no additional authority."""

    register_task: RawMaterialImportTaskRegistrar
    resolve_task: RawMaterialImportTaskResolver
    registry_owner: str = "app.celery_app.celery_app.tasks"


@dataclass(frozen=True, slots=True)
class RawMaterialImportTaskBinding:
    """Typed API handle and exact Celery registration derived from one definition."""

    definition: RawMaterialImportTaskDefinition
    task: RawMaterialImportRegisteredTask
    run: RawMaterialImportTaskRun
    registry_owner: str

    def delay(
        self,
        request: RawImportRequest,
        project_key: str,
    ) -> RawMaterialImportAsyncResult:
        return self.task.delay(self.definition.payload(request), project_key)


def _qualified_name(value: object) -> str:
    value_type = value if isinstance(value, type) else type(value)
    module = getattr(value, "__module__", value_type.__module__)
    name = getattr(value, "__qualname__", value_type.__qualname__)
    return f"{module}.{name}"


def _invalid(*issues: tuple[str, str]) -> Failure:
    return contribution_failures.fail(
        "CONTRIBUTION_INVALID",
        "raw Material import task contribution is invalid",
        {
            "issues": tuple(
                {
                    "code": "invalid_spec",
                    "path": path,
                    "message": message,
                }
                for path, message in issues
            )
        },
    )


def lower_raw_material_import_task(
    source: RawMaterialImportTaskDefinition,
) -> RawMaterialImportTaskDefinition | Failure:
    issues: list[tuple[str, str]] = []
    if not source.task_name.strip():
        issues.append(("$.source.task_name", "nonempty Celery task identity required"))
    return _invalid(*issues) if issues else source


def project_raw_material_import_task(
    definition: RawMaterialImportTaskDefinition,
) -> ProjectedContributionSpec:
    request_id = (
        f"{definition.contribution_id}:request:"
        f"{_qualified_name(definition.request_type)}"
    )
    kernel_id = (
        f"{definition.contribution_id}:kernel:"
        f"{_qualified_name(definition.kernel)}"
    )
    scope_id = (
        f"{definition.contribution_id}:scope:"
        "app.services.projects.bind_project"
    )
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=RAW_MATERIAL_IMPORT_TASK_OWNER,
        objects=(
            ContributionObject(
                request_id,
                "RawMaterialImportRequest",
                RAW_MATERIAL_IMPORT_TASK_OWNER,
            ),
            ContributionObject(
                kernel_id,
                "RawMaterialImportKernel",
                RAW_MATERIAL_IMPORT_TASK_OWNER,
            ),
            ContributionObject(
                scope_id,
                "ProjectBinding",
                RAW_MATERIAL_IMPORT_TASK_OWNER,
            ),
            ContributionObject(
                definition.contribution_id,
                "ProjectBoundCeleryTask",
                RAW_MATERIAL_IMPORT_TASK_OWNER,
                (request_id, kernel_id, scope_id),
            ),
        ),
    )


def run_raw_material_import_payload(
    definition: RawMaterialImportTaskDefinition,
    payload: RawObject,
    project_key: str,
) -> RawObject:
    with bind_project(project_key):
        return definition.kernel(payload, project_key)


def assemble_raw_material_import_task(
    definition: RawMaterialImportTaskDefinition,
    context: RawMaterialImportTaskAssemblyContext,
) -> RawMaterialImportTaskBinding | Failure:
    if context.registry_owner != "app.celery_app.celery_app.tasks":
        return _invalid((
            "$.context.registry_owner",
            "raw Material import task must use the existing Celery registry",
        ))

    run = _derive_raw_material_import_task_runner(definition)

    registered = context.register_task(definition.task_name, run)
    resolved = context.resolve_task(definition.task_name)
    if (
        not isinstance(resolved, RawMaterialImportRegisteredTask)
        or resolved.name != definition.task_name
        or resolved.run is not run
        or registered != resolved
    ):
        return _invalid((
            "$.context.registry",
            "Celery registry did not retain the exact derived task identity and runner",
        ))
    return RawMaterialImportTaskBinding(
        definition=definition,
        task=resolved,
        run=run,
        registry_owner=context.registry_owner,
    )


def validate_raw_material_import_task_binding(
    definition: RawMaterialImportTaskDefinition,
    candidate: object,
) -> BindingAccepted[RawMaterialImportTaskBinding] | BindingRejected:
    if (
        isinstance(candidate, RawMaterialImportTaskBinding)
        and candidate.definition is definition
        and candidate.task.name == definition.task_name
        and isinstance(candidate.run, RawMaterialImportTaskRunner)
        and candidate.run.definition is definition
        and candidate.task.run is candidate.run
        and candidate.registry_owner == "app.celery_app.celery_app.tasks"
    ):
        return BindingAccepted(candidate)
    return BindingRejected((
        NativeBindingIssue(
            "$.binding",
            "task registry identity, runner, or native definition mismatch",
        ),
    ))


class _VerificationTask:
    def __init__(self, name: str, run: RawMaterialImportTaskRun) -> None:
        self.name = name
        self.run = run

    def delay(
        self,
        payload: RawObject,
        project_key: str,
    ) -> RawMaterialImportAsyncResult:
        raise AssertionError("verification assembly must not enqueue the task")


def _verification_for_raw_material_import_task(
    definition: RawMaterialImportTaskDefinition,
    native: NativeContribution[
        RawMaterialImportTaskDefinition,
        RawMaterialImportTaskAssemblyContext,
        RawMaterialImportTaskBinding,
    ],
) -> ContributionVerification | Failure:
    def verify_assembly_correspondence() -> object:
        registry: dict[str, _VerificationTask] = {}

        def register(name: str, run: RawMaterialImportTaskRun) -> _VerificationTask:
            task = _VerificationTask(name, run)
            registry[name] = task
            return task

        binding = native.assemble(
            RawMaterialImportTaskAssemblyContext(
                register_task=register,
                resolve_task=registry.get,
            )
        )
        if isinstance(binding, Failure):
            raise AssertionError(binding)
        if binding.definition is not definition:
            raise AssertionError("assembly did not preserve the native definition")
        if binding.task is not registry.get(definition.task_name):
            raise AssertionError("assembly did not preserve the exact registry task")
        return binding

    witness = define_law_witness(
        f"{definition.contribution_id}:assembly-correspondence",
        verify_assembly_correspondence,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=RAW_MATERIAL_IMPORT_TASK_RULE_ID,
        inputs=(
            "main/backend/app/composition/raw_material_import_task.py",
            "main/backend/app/contracts/raw_material_import.py",
            "main/backend/app/services/ingest/raw_import.py",
        ),
        checks=(VerificationCheck(witness),),
        complete=False,
    )


RAW_MATERIAL_IMPORT_TASK_NATIVE_RULE = NativeContributionRule[
    RawMaterialImportTaskDefinition,
    RawMaterialImportTaskDefinition,
    RawMaterialImportTaskAssemblyContext,
    RawMaterialImportTaskBinding,
](
    lower=lower_raw_material_import_task,
    project=project_raw_material_import_task,
    assemble=assemble_raw_material_import_task,
    validate_binding=validate_raw_material_import_task_binding,
    verification=_verification_for_raw_material_import_task,
)


def compile_raw_material_import_task(
    source: RawMaterialImportTaskDefinition,
) -> NativeContribution[
    RawMaterialImportTaskDefinition,
    RawMaterialImportTaskAssemblyContext,
    RawMaterialImportTaskBinding,
] | Failure:
    return compile_native_contribution(
        source,
        RAW_MATERIAL_IMPORT_TASK_NATIVE_RULE,
    )


RAW_MATERIAL_IMPORT_TASK_DEFINITION = RawMaterialImportTaskDefinition(
    task_name=RAW_MATERIAL_IMPORT_TASK_NAME,
    request_type=RawImportRequest,
    kernel=run_raw_import_materials,
)


def _require_raw_material_import_task_native(
    definition: RawMaterialImportTaskDefinition,
) -> NativeContribution[
    RawMaterialImportTaskDefinition,
    RawMaterialImportTaskAssemblyContext,
    RawMaterialImportTaskBinding,
]:
    compiled = compile_raw_material_import_task(definition)
    if isinstance(compiled, Failure):
        raise RuntimeError(
            "invalid raw Material import task definition: "
            f"{compiled.message}"
        )
    return compiled


raw_material_import_task_native = _require_raw_material_import_task_native(
    RAW_MATERIAL_IMPORT_TASK_DEFINITION,
)

raw_material_import_task_native_catalog = (
    raw_material_import_task_native,
)

raw_material_import_task_contribution_catalog = tuple(
    native.projection
    for native in raw_material_import_task_native_catalog
)


__all__ = [
    "RAW_MATERIAL_IMPORT_TASK_DEFINITION",
    "RAW_MATERIAL_IMPORT_TASK_NAME",
    "RAW_MATERIAL_IMPORT_TASK_NATIVE_RULE",
    "RawMaterialImportAsyncResult",
    "RawMaterialImportRegisteredTask",
    "RawMaterialImportTaskAssemblyContext",
    "RawMaterialImportTaskBinding",
    "RawMaterialImportTaskDefinition",
    "RawMaterialImportTaskRunner",
    "compile_raw_material_import_task",
    "raw_material_import_task_contribution_catalog",
    "raw_material_import_task_native",
    "raw_material_import_task_native_catalog",
]
