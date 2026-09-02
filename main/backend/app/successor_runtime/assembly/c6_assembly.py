"""C6 family assembly: deterministic LOCAL_ONLY fixture closure.

The C6 cells install ``AgentCoreC6StoreRehydratedHandler`` only when their
run-bound fixture dimensions are complete.  All fixtures are deterministic
in-memory ports: a scripted model-step source, a pure C2.1 tool specimen, a
receipt-only provider port and an ephemeral raw observation.  No provider,
network, database or canonical write is performed by assembly construction.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from app.successor_runtime.assembly.base import (
    C6AssemblyOptions,
    CellBinding,
    FamilyAssembly,
    RollbackBindingDeclaration,
    successor_binding,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_1 as c6_1,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_1_interpreters as c6_1i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2 as c6_2,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2_interpreters as c6_2i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_2_live_model_port as c6_2_live,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3 as c6_3,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_3_interpreters as c6_3i,
)
from app.successor_runtime.capabilities import (
    agent_core_c6_common as c6_common,
)
from app.successor_runtime.capabilities.agent_core_c6_common import (
    AgentModelStep,
    AgentModelStepOutcome,
    AgentToolCall,
    AgentToolResult,
    freeze_c6_json_object,
)
from app.successor_runtime.substrate.postgres.agent_core_c6_handler import (
    AgentCoreC6StoreRehydratedHandler,
)

__all__ = [
    "build_c6_assembly",
    "build_deterministic_fixtures",
    "build_openai_live_fixture_options",
]

_C6_FRAGMENT = (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments/C6.json"
)
_LEGACY_AGENT_CORE = "main/backend/app/successor_migration/legacy_agent_core.py"

_CELLS = (
    {
        "cell_id": "C6.1",
        "operation_contract_ref": "agent_core.episode_interpret.v1",
        "recovery_ref": "mrw.successor.agent-core.c6-1.recovery.v1",
        "required_wiring": ("episode handler installation", "worker store wiring"),
        "fixtures": (
            "uow_factory",
            "model_step_source",
            "tool_specimens",
            "permission_policy",
            "redactor",
        ),
        "base_note": "episode handler requires the full deterministic loop closure",
    },
    {
        "cell_id": "C6.2",
        "operation_contract_ref": "agent.model_step.v1",
        "recovery_ref": "mrw.successor.agent-core.c6-2.recovery.v1",
        "required_wiring": (
            "provider handler installation",
            "生产 provider port（live 维度未冻结）",
        ),
        "fixtures": ("uow_factory", "provider_port"),
        "base_note": (
            "LIVE_PROVIDER_DIMENSION_UNRESOLVED: production provider wiring "
            "semantics are not frozen"
        ),
    },
    {
        "cell_id": "C6.3",
        "operation_contract_ref": "observability.redact_evidence.v1",
        "recovery_ref": "mrw.successor.agent-core.c6-3.recovery.v1",
        "required_wiring": (
            "redaction handler installation",
            "redaction persistence wiring",
        ),
        "fixtures": ("uow_factory", "raw_observation"),
        "base_note": "redaction handler requires an ephemeral raw observation",
    },
)


class _DeterministicModelStepSource:
    """Scripted deterministic source; exhaustion always yields final_answer."""

    def __init__(self) -> None:
        tool_call = AgentToolCall(
            call_id="call-i1-c6-1",
            tool_name="c2_1_pure",
            arguments=freeze_c6_json_object({}),
        )
        self._steps = [
            AgentModelStep(
                schema_version="mrw.successor.agent-core.c6.model-step.v1",
                step_type="tool_calls",
                tool_calls=(tool_call,),
            ),
            AgentModelStep(
                schema_version="mrw.successor.agent-core.c6.model-step.v1",
                step_type="final_answer",
                content="i1 c6 local fixture answer",
            ),
        ]

    def next_step(
        self,
        *,
        request: c6_1.AgentTurnRequest,
        tool_names: tuple[str, ...],
        transcript: list[dict[str, Any]],
        remaining_budget: dict[str, Any],
    ) -> AgentModelStepOutcome:
        if self._steps:
            return self._steps.pop(0)
        return AgentModelStep(
            schema_version="mrw.successor.agent-core.c6.model-step.v1",
            step_type="final_answer",
            content="exhausted",
        )


class _DeterministicPureToolSpecimen:
    """Minimal successor-native pure tool specimen for the C6.1 loop."""

    tool_name = "c2_1_pure"

    def validate(self, tool_call: AgentToolCall) -> AgentToolResult | None:
        return None

    def execute(
        self,
        tool_call: AgentToolCall,
        request: c6_1.AgentTurnRequest,
    ) -> AgentToolResult:
        return AgentToolResult(
            call_id=tool_call.call_id,
            tool_name=tool_call.tool_name,
            status="completed",
            model_summary="c2_1_pure deterministic fixture result",
            structured_content=freeze_c6_json_object(
                {"fixture": True, "trace_id": "i1-c6-1-local"}
            ),
        )


def build_deterministic_fixtures() -> dict[str, Any]:
    """Return the exact LOCAL_ONLY C6 fixture dimensions as one options dict."""

    return {
        "model_step_source": _DeterministicModelStepSource(),
        "tool_specimens": (_DeterministicPureToolSpecimen(),),
        "permission_policy": c6_1.StaticPermissionPolicy(),
        "redactor": c6_1.CanonicalJsonEventRedactor(),
        "provider_port": c6_2.ReceiptOnlyProviderPort(),
        "raw_observation": {"fixture": True, "trace_id": "i1-c6-3-local"},
    }


def _is_live_provider_port(port: Any) -> bool:
    """Recognize the live OpenAI provider port without importing it by name."""

    if port is None:
        return False
    return bool(getattr(port, "live_provider", False)) or str(
        getattr(port, "interpreter_id", "")
    ).startswith("live.")


def build_openai_live_fixture_options(
    *,
    api_key_provider: Callable[[], str | None] | None = None,
    transport: Any | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float = 30.0,
) -> C6AssemblyOptions | None:
    """Return the full deterministic C6 closure with a live OpenAI port.

    Assembly construction never calls the provider.  Missing ``OPENAI_API_KEY``
    keeps the caller on the deterministic receipt-only fixture closure.
    """

    port = c6_2_live.build_openai_live_provider_port(
        api_key_provider=api_key_provider,
        transport=transport,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if port is None:
        return None
    fixtures = build_deterministic_fixtures()
    fixtures["provider_port"] = port
    return C6AssemblyOptions(
        **fixtures,
        note=(
            "LIVE_PROVIDER_DIMENSION_RESOLVED_OPENAI deterministic fixture "
            "closure with the env-backed live provider port; no provider "
            "invocation occurs during assembly construction"
        ),
    )


def _missing_fixtures(
    cell: dict[str, object],
    options: C6AssemblyOptions,
    uow_factory_provided: bool,
) -> tuple[str, ...]:
    """Return the run-bound fixture dimensions absent from the closure."""

    provided: set[str] = set()
    if uow_factory_provided:
        provided.add("uow_factory")
    if options.model_step_source is not None:
        provided.add("model_step_source")
    if options.tool_specimens:
        provided.add("tool_specimens")
    if options.permission_policy is not None:
        provided.add("permission_policy")
    if options.redactor is not None:
        provided.add("redactor")
    if options.provider_port is not None:
        provided.add("provider_port")
    if options.raw_observation is not None:
        provided.add("raw_observation")
    required = set(cell["fixtures"])  # type: ignore[arg-type]
    return tuple(sorted(required - provided))


def _rollback_bindings() -> tuple[RollbackBindingDeclaration, ...]:
    return tuple(
        RollbackBindingDeclaration(
            cell_id=str(cell["cell_id"]),
            status="PRESENT",
            binding_refs=(_C6_FRAGMENT, _LEGACY_AGENT_CORE),
        )
        for cell in _CELLS
    )


def _c6_contract_digest(cell_key: str) -> str:
    if cell_key == "c6_1":
        bundle = c6_1.build_agent_core_c6_1_bundle()
        catalog = c6_1.build_agent_core_c6_1_catalog(bundle)
        kind = c6_1.AGENT_CORE_C6_1_KIND
    elif cell_key == "c6_2":
        bundle = c6_2.build_agent_core_c6_2_bundle()
        catalog = c6_2.build_agent_core_c6_2_catalog(bundle)
        kind = c6_2.AGENT_CORE_C6_2_KIND
    else:
        bundle = c6_3.build_agent_core_c6_3_bundle()
        catalog = c6_3.build_agent_core_c6_3_catalog(bundle)
        kind = c6_3.AGENT_CORE_C6_3_KIND
    ref = catalog.lookup(kind)
    if ref is None:
        raise KeyError(f"C6 operation contract not found: {kind}")
    return ref.contract_digest


def _c6_binding(
    cell_key: str,
    project_scope_digest: str,
    operation_contract_digest: str,
) -> Any:
    if cell_key == "c6_1":
        interpreter_profile_digest = c6_1i.successor_interpreter_profile_digest()
        authority_requirement = c6_1i.authority_requirement_digest()
    elif cell_key == "c6_2":
        interpreter_profile_digest = c6_2i.successor_interpreter_profile_digest()
        authority_requirement = c6_2i.authority_requirement_digest()
    else:
        interpreter_profile_digest = c6_3i.successor_interpreter_profile_digest()
        authority_requirement = c6_3i.authority_requirement_digest()
    return successor_binding(
        operation_contract_digest=operation_contract_digest,
        interpreter_profile_digest=interpreter_profile_digest,
        deployment_catalog_digest=c6_common.c6_deployment_catalog_digest(),
        project_scope_digest=project_scope_digest,
        authority_requirement_digest=authority_requirement,
        resource_policy_epoch=1,
        runtime_protocol_version="1",
    )


def build_c6_assembly(
    *,
    uow_factory: Callable[[], object],
    project_scope_digest: str,
    options: C6AssemblyOptions | None = None,
) -> FamilyAssembly:
    """Install each C6 store handler when its fixture closure is complete."""

    opts = options or C6AssemblyOptions()
    if opts.provider_port is None:
        live_port = c6_2_live.build_openai_live_provider_port()
        if live_port is not None:
            opts = dataclasses.replace(
                opts,
                provider_port=live_port,
                note=(
                    "LIVE_PROVIDER_DIMENSION_RESOLVED_OPENAI env-backed "
                    "provider port; no provider invocation occurs during "
                    "assembly construction"
                ),
            )
    cells: list[CellBinding] = []
    handlers: list[Any] = []
    for spec in _CELLS:
        cell_id = str(spec["cell_id"])
        cell_key = cell_id.lower().replace(".", "_")
        missing = _missing_fixtures(spec, opts, uow_factory is not None)
        if missing:
            cells.append(
                CellBinding(
                    cell_id=cell_id,
                    family_id="C6",
                    status="FIXTURE_CLOSURE_REQUIRED",
                    operation_contract_refs=(str(spec["operation_contract_ref"]),),
                    recovery_binding_ref=str(spec["recovery_ref"]),
                    required_wiring=tuple(spec["required_wiring"]),  # type: ignore[arg-type]
                    note=(
                        "FIXTURE_CLOSURE_REQUIRED: "
                        + str(spec["base_note"])
                        + "; missing "
                        + ", ".join(missing)
                    ),
                )
            )
            continue

        contract_digest = _c6_contract_digest(cell_key)
        binding = _c6_binding(cell_key, project_scope_digest, contract_digest)
        if cell_key == "c6_1":
            handler = AgentCoreC6StoreRehydratedHandler(
                uow_factory=uow_factory,
                cell=cell_key,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                operation_contract_digest=binding.operation_contract_digest,
                deployment_catalog_digest=binding.deployment_catalog_digest,
                model_step_source=opts.model_step_source,
                tool_specimens=opts.tool_specimens,
                permission_policy=opts.permission_policy,
                redactor=opts.redactor,
            )
            note = (
                "LOCAL_OFFLINE deterministic no-provider fixture closure; "
                "AgentCoreC6StoreRehydratedHandler installed with scripted "
                "model source and pure tool specimen"
            )
        elif cell_key == "c6_2":
            handler = AgentCoreC6StoreRehydratedHandler(
                uow_factory=uow_factory,
                cell=cell_key,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                operation_contract_digest=binding.operation_contract_digest,
                deployment_catalog_digest=binding.deployment_catalog_digest,
                provider_port=opts.provider_port,
            )
            if _is_live_provider_port(opts.provider_port):
                note = (
                    "LIVE_PROVIDER_DIMENSION_RESOLVED_OPENAI: "
                    "AgentCoreC6StoreRehydratedHandler uses the env-backed "
                    "live OpenAI provider port; no provider invocation "
                    "occurs during assembly construction and receipts stay "
                    "redacted"
                )
            else:
                note = (
                    "LOCAL_OFFLINE deterministic fixture closure; "
                    "LIVE_PROVIDER_DIMENSION_UNRESOLVED: fixture provider port "
                    "is not a production provider"
                )
        else:
            handler = AgentCoreC6StoreRehydratedHandler(
                uow_factory=uow_factory,
                cell=cell_key,
                handler_binding_digest=binding.binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                operation_contract_digest=binding.operation_contract_digest,
                deployment_catalog_digest=binding.deployment_catalog_digest,
                raw_observation=opts.raw_observation,
            )
            note = (
                "LOCAL_OFFLINE deterministic redaction closure; ephemeral "
                "raw observation never persisted"
            )
        handlers.append(handler)
        cells.append(
            CellBinding(
                cell_id=cell_id,
                family_id="C6",
                status="INSTALLED",
                operation_contract_refs=(str(spec["operation_contract_ref"]),),
                handler_binding_digest=handler.handler_binding_digest,
                recovery_binding_ref=str(spec["recovery_ref"]),
                required_wiring=tuple(spec["required_wiring"]),  # type: ignore[arg-type]
                note=note,
            )
        )

    return FamilyAssembly(
        family_id="C6",
        cells=tuple(cells),
        handlers=tuple(handlers),
        rollback_bindings=_rollback_bindings(),
    )
